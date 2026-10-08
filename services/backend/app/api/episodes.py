"""The capture boundary: upload an Episode, then read its status and result.

These are the three endpoints the Android client uses for the golden path, and
their response bodies are the contract's `episodeCreated`, `processingStatus`,
and `episodeResult` — no more fields than the contract defines, because the
contract sets additionalProperties false and a client validating against it would
reject the extra.

Two things the contract leaves open and this boundary decides:

* `actor_id`, `recording_consent_id`, and `idempotency_key` are optional in the
  schema. A real upload requires all three, and says so with REQUEST_INVALID
  rather than accepting a capture that cannot be attributed, authorized, or
  replayed safely.
* Reading an Episode requires an actor but no consent. Consent guards the act of
  capturing; an Episode that already exists stays readable, which is what makes a
  failed processing run survivable. What "readable" is scoped to is the Actor: an
  Episode is readable by the Actor that captured it and by nobody else, and
  another Actor's Episode is answered exactly as one that does not exist, so the
  API cannot be used to discover that another Actor's recording is there.

`job_id` appears nowhere in a response. Work is addressed by `episode_id`, and the
contract's test asserts the job id never leaks.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..contracts import EpisodeCreated, EpisodeResult, MemoryItem, ProcessingStatus
from ..config import Settings
from ..db import get_session
from ..chinese_text import simplified_transcript
from ..errors import (
    AudioInvalid,
    AudioTooLarge,
    EpisodeNotReady,
    IdempotencyConflict,
    RequestInvalid,
    StorageUnavailable,
)
from ..logging_config import trace_id_var
from ..models import (
    Actor,
    CaptureSource,
    CalibrationRun,
    ConsentScope,
    Episode,
    EpisodeStatus,
    as_utc,
    JobState,
    JobStage,
    utcnow,
)
from ..repositories.consents import ConsentRepository
from ..repositories.episodes import (
    EpisodeRepository,
    audio_object_key,
    new_episode_id,
)
from ..repositories.jobs import JobRepository
from ..repositories.jobs import STAGE_STATUS
from ..repositories.memory import MemoryRepository
from ..repositories.subjects import SubjectRepository
from ..security import current_actor
from ..storage.base import ObjectStore, checksum_of

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/episodes", tags=["episode"])


class TranscriptReview(BaseModel):
    state: Literal["transcribing", "reviewing", "submitted", "not_required"]
    transcript: str | None = None
    stt_model_version: str | None = None


class ConfirmTranscript(BaseModel):
    transcript: str = Field(min_length=1, max_length=100_000)

# Read the upload in bounded pieces so a body larger than the limit is refused
# while it is being read rather than after it is all in memory.
_CHUNK_BYTES = 1024 * 1024

# The one type prefix this boundary accepts. A client that cannot name its own
# audio type would have to send application/octet-stream, and accepting that
# would mean giving up the ability to tell a mis-declared upload from a real one.
_AUDIO_PREFIX = "audio/"


def _object_store(request: Request) -> ObjectStore:
    return request.app.state.object_store


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _read_upload(upload: UploadFile, *, limit_bytes: int) -> bytes:
    """Read the file part, refusing anything over the limit."""
    if upload.size is not None and upload.size > limit_bytes:
        raise AudioTooLarge(
            f"The upload is {upload.size} bytes; the limit is {limit_bytes}"
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = upload.file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit_bytes:
            raise AudioTooLarge(f"The upload exceeds the {limit_bytes} byte limit")
        chunks.append(chunk)

    data = b"".join(chunks)
    if not data:
        raise AudioInvalid("The upload is empty")
    return data


def _validated_recorded_at(value: datetime) -> datetime:
    """Require an explicit offset, and store UTC.

    A naive timestamp from a phone is local time with no record of which local
    time, so accepting one would put an unresolvable instant into the record. The
    contract types this field as a date-time; requiring the offset is this
    boundary's reading of that.
    """
    if value.tzinfo is None:
        raise RequestInvalid("recorded_at must carry a UTC offset, e.g. 2026-09-21T09:00:00Z")
    return value.astimezone(timezone.utc)


def _parse_metadata(raw: str | None) -> dict | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        parsed = json.loads(raw)
    except ValueError as error:
        raise RequestInvalid(f"metadata must be a JSON object: {error}") from error
    if not isinstance(parsed, dict):
        raise RequestInvalid("metadata must be a JSON object")
    return parsed


def _discard_orphaned_audio(store: ObjectStore, key: str, episode_id: str) -> None:
    """Remove audio written by a request whose Episode never committed.

    The bytes are stored before the Episode is committed, so a request that fails
    to commit leaves an object behind that no record refers to. Removing it is the
    compensation for that ordering, and it is safe for the reason the ordering is
    acceptable at all: the key is derived from an episode id this request
    generated, so nothing else can be pointing at it.

    This is not the cleanup-on-failure ADR-0001 D11 rejects. That would delete the
    audio of a *committed* Episode because a later stage failed, destroying the
    subject's recording to tidy up a processing error; this deletes an object that
    belongs to no Episode at all.

    Best-effort: the request has already failed, and a second failure here must
    not replace an error the client can act on with one it cannot. An object that
    survives is a leak, not an inconsistency, and it is logged as one.
    """
    try:
        store.delete(key)
    except Exception as error:  # noqa: BLE001 - compensation must not mask the cause
        logger.warning(
            "upload.orphan_not_removed",
            extra={
                "extra_fields": {
                    "episode_id": episode_id,
                    "object_key": key,
                    "error": str(error),
                }
            },
        )


class CaptureEpisodeForm(BaseModel):
    """The multipart body of a capture, mirroring the contract's captureEpisode.

    One model rather than separate Form(...) parameters, so that an unknown field
    is refused here exactly as it is on the JSON endpoints. The audio is a field
    of the model because that is what the request body is: a multipart form with
    a file part in it.

    `metadata` is typed as a string: multipart carries no nested objects, so the
    client sends JSON and this boundary parses it.
    """

    model_config = ConfigDict(extra="forbid")

    file: UploadFile = Field(description="The raw audio")
    subject_id: str = Field(min_length=1, description="Who this recording is about")
    source: CaptureSource = Field(description="Where the recording came from")
    recorded_at: datetime = Field(description="When it was recorded, with an offset")
    audio_ref: str = Field(min_length=1, description="What the client called this recording")
    idempotency_key: str = Field(
        min_length=1, description="Stable across retries of the same capture"
    )
    recording_consent_id: str = Field(
        min_length=1, description="An active RECORDING consent"
    )
    # Accepted because the contract's captureEpisode defines it, and required to
    # name the caller when it is sent. A capture is attributed to the credential,
    # and this is the one way a client can try to say otherwise, so it is checked
    # rather than ignored.
    actor_id: str | None = Field(
        None, description="Optional; must name the caller if sent"
    )
    duration_ms: int | None = Field(None, ge=0)
    metadata: str | None = Field(None, description="Arbitrary capture metadata, as JSON")


@router.post("", response_model=EpisodeCreated, status_code=status.HTTP_201_CREATED)
def create_episode(
    response: Response,
    form: Annotated[CaptureEpisodeForm, Form(media_type="multipart/form-data")],
    actor: Actor = Depends(current_actor),
    store: ObjectStore = Depends(_object_store),
    settings: Settings = Depends(_settings),
    session: Session = Depends(get_session),
) -> EpisodeCreated:
    """Store one recording and queue its processing.

    Replaying a capture returns the Episode the first request created, with 200
    instead of 201. The same key with different audio is a conflict rather than a
    replay: answering with the stored Episode would attach the wrong recording to
    the key.

    The consent that authorizes this is the caller's own. Asking for a `RECORDING`
    consent is not enough on its own — it has to be one this Actor granted, or the
    upload would be authorized by somebody else's grant (ADR-0001 D7).
    """
    if form.actor_id is not None and form.actor_id != actor.actor_id:
        raise RequestInvalid(
            "actor_id must name the actor the request is authenticated as, or be omitted"
        )

    recorded = _validated_recorded_at(form.recorded_at)
    capture_metadata = _parse_metadata(form.metadata)

    subjects = SubjectRepository(session)
    subjects.require(form.subject_id)
    ConsentRepository(session).require_active(
        form.recording_consent_id,
        subject_id=form.subject_id,
        scope=ConsentScope.RECORDING,
        actor_id=actor.actor_id,
    )

    content_type = (form.file.content_type or "").lower()
    if not content_type.startswith(_AUDIO_PREFIX):
        raise AudioInvalid(
            f"The upload is typed {content_type or 'with no content type'}; "
            f"an {_AUDIO_PREFIX}* type is required"
        )

    data = _read_upload(form.file, limit_bytes=settings.max_upload_bytes)
    checksum = checksum_of(data)

    episodes = EpisodeRepository(session)
    existing = episodes.find_by_idempotency(
        subject_id=form.subject_id,
        actor_id=actor.actor_id,
        idempotency_key=form.idempotency_key,
    )
    if existing is not None:
        if existing.audio_checksum != checksum:
            raise IdempotencyConflict(
                f"idempotency_key {form.idempotency_key} was already used for different audio "
                f"(episode {existing.episode_id})"
            )
        response.status_code = status.HTTP_200_OK
        return EpisodeCreated(
            episode_id=existing.episode_id, upload_status="uploaded"
        )

    # A prior RECORDING grant did not authorize exporting raw audio. Bind this
    # capture to the displayed relay policy; never accept a client-made receipt.
    capture_metadata = dict(capture_metadata or {})
    capture_metadata.pop('cloud_asr_receipt', None)
    if settings.stt_backend in {'relay', 'groq'}:
        from ..cloud_asr import cloud_policy, configured
        if not configured(settings):
            raise RequestInvalid('云端转写连接配置未完成，请先保留本机原音，配置完成后再上传。')
        policy = cloud_policy(settings)
        if capture_metadata.get('cloud_asr_policy') != policy:
            raise RequestInvalid('请刷新转写配置，并明确同意把本段原音发送到云端转写；尚未外发音频。')
        from ..models import utcnow
        capture_metadata['cloud_asr_receipt'] = {
            'policy': policy, 'actor_id': actor.actor_id, 'confirmed_at': utcnow().isoformat()}

    calibration = None
    calibration_id = (capture_metadata or {}).get("calibration_id")
    if calibration_id is not None:
        if not isinstance(calibration_id, str) or form.source not in {CaptureSource.IOS_MIC, CaptureSource.IMPORT, CaptureSource.ANDROID_MIC}:
            raise RequestInvalid("calibration_id requires a reviewed recording")
        calibration = session.scalar(select(CalibrationRun).where(
            CalibrationRun.calibration_id == calibration_id,
            CalibrationRun.subject_id == form.subject_id,
            CalibrationRun.actor_id == actor.actor_id))
        if (calibration is None or calibration.status != "awaiting_human"
                or calibration.human_episode_id is not None):
            raise RequestInvalid("calibration_id is not awaiting this Actor's answer")
        from .calibration import _check_source
        if not _check_source(session, calibration):
            session.commit()
            raise RequestInvalid("calibration source has changed")

    episode = Episode(
        episode_id=new_episode_id(),
        subject_id=form.subject_id,
        actor_id=actor.actor_id,
        recording_consent_id=form.recording_consent_id,
        idempotency_key=form.idempotency_key,
        source=str(form.source),
        recorded_at=recorded,
        duration_ms=form.duration_ms,
        capture_metadata=capture_metadata,
        # Filled in by attach_audio before the commit; the columns are not
        # nullable so that an Episode can never exist without its audio recorded.
        audio_ref=form.audio_ref,
        audio_object_key="",
        audio_size_bytes=0,
        audio_content_type=content_type,
        audio_checksum="",
        status=str(EpisodeStatus.UPLOADED),
        trace_id=trace_id_var.get() or "",
    )
    episodes.add(episode)
    JobRepository(session).enqueue(episode.episode_id)

    key = audio_object_key(form.subject_id, episode.episode_id)
    try:
        # Written before the commit, so a storage failure rolls the Episode back
        # instead of leaving a record whose audio never arrived.
        stored = store.put(key, data, content_type)
    except Exception as error:  # noqa: BLE001 - any storage failure is one code
        session.rollback()
        logger.warning(
            "upload.storage_failed",
            extra={"extra_fields": {"episode_id": episode.episode_id, "error": str(error)}},
        )
        raise StorageUnavailable(f"Object storage refused the upload: {error}") from error

    # Everything from here to the commit has an object behind it that no Episode
    # refers to yet, so all of it is inside the compensation.
    try:
        episodes.attach_audio(episode, stored, audio_ref=form.audio_ref)
        session.flush()
        if calibration is not None:
            calibration.human_episode_id = episode.episode_id
        session.commit()
    except IntegrityError:
        # Two uploads with the same key raced. The unique index chose one; this
        # request reports the winner rather than a duplicate.
        session.rollback()
        _discard_orphaned_audio(store, key, episode.episode_id)
        existing = episodes.find_by_idempotency(
            subject_id=form.subject_id,
            actor_id=actor.actor_id,
            idempotency_key=form.idempotency_key,
        )
        if existing is None:
            raise
        if existing.audio_checksum != checksum:
            raise IdempotencyConflict(
                f"idempotency_key {form.idempotency_key} was already used for different audio "
                f"(episode {existing.episode_id})"
            ) from None
        logger.info(
            "upload.idempotent_race",
            extra={"extra_fields": {"episode_id": existing.episode_id}},
        )
        response.status_code = status.HTTP_200_OK
        return EpisodeCreated(episode_id=existing.episode_id, upload_status="uploaded")
    except Exception:
        # The Episode did not commit, so the object written for it belongs to no
        # record. Without this the bytes would outlive the request that made them
        # and nothing would ever refer to them again.
        session.rollback()
        _discard_orphaned_audio(store, key, episode.episode_id)
        raise

    return EpisodeCreated(episode_id=episode.episode_id, upload_status="uploaded")


@router.get("/{episode_id}", response_model=ProcessingStatus, response_model_exclude_none=True)
def read_status(
    episode_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> ProcessingStatus:
    """Where the Episode is in processing.

    Optional fields are omitted rather than sent as null: the contract types them
    as strings, so an explicit null is not a valid processingStatus. `progress` is
    deliberately absent for a second reason — a number derived from the status
    would only restate it, and a client that read it as real progress would be
    misled.

    Scoped to the Actor that captured the Episode: another Actor's Episode is
    EPISODE_NOT_FOUND, exactly as an id nobody holds would be.
    """
    episode = EpisodeRepository(session).require_for(episode_id, actor_id=actor.actor_id)
    return ProcessingStatus(
        episode_id=episode.episode_id,
        status=EpisodeStatus(episode.status),
        trace_id=episode.trace_id or None,
        error_code=episode.error_code,
        error_message=episode.error_message,
    )


@router.get("/{episode_id}/transcript-review", response_model=TranscriptReview)
def read_transcript_review(
    episode_id: str,
    response: Response,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> TranscriptReview:
    """Expose STT text only to the capturing Actor while their iOS job waits."""
    response.headers["Cache-Control"] = "private, no-store"
    episode = EpisodeRepository(session).require_for(episode_id, actor_id=actor.actor_id)
    job = JobRepository(session).for_episode(episode_id)
    if episode.source not in {str(CaptureSource.IOS_MIC), str(CaptureSource.IMPORT), str(CaptureSource.ANDROID_MIC)}:
        state = "not_required"
    elif job is not None and job.state == str(JobState.WAITING):
        state = "reviewing"
    elif episode.transcript_reviewed_at is not None:
        state = "submitted"
    elif episode.status == str(EpisodeStatus.READY):
        state = "not_required"
    else:
        state = "transcribing"
    return TranscriptReview(
        state=state,
        transcript=simplified_transcript(episode.transcript)
            if state == "reviewing" and episode.transcript is not None else None,
        stt_model_version=episode.stt_model_version,
    )


@router.patch("/{episode_id}/transcript-review", response_model=ProcessingStatus,
              response_model_exclude_none=True)
def confirm_transcript(
    episode_id: str,
    payload: ConfirmTranscript,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> ProcessingStatus:
    """Commit the subject's text before the extract job can reach DeepSeek."""
    episode = EpisodeRepository(session).require_for(episode_id, actor_id=actor.actor_id)
    text = payload.transcript.strip()
    if not text:
        raise RequestInvalid("The confirmed transcript cannot be blank")
    if episode.source not in {str(CaptureSource.IOS_MIC), str(CaptureSource.IMPORT), str(CaptureSource.ANDROID_MIC)}:
        raise RequestInvalid("Transcript review requires iOS or imported capture")
    if episode.transcript_reviewed_at is not None:
        if episode.transcript == text:
            return ProcessingStatus(episode_id=episode_id, status=EpisodeStatus(episode.status),
                                    trace_id=episode.trace_id or None)
        raise RequestInvalid("This Episode's transcript was already confirmed")

    job = JobRepository(session).for_episode(episode_id)
    if (job is None or job.state != str(JobState.WAITING)
            or job.stage != str(JobStage.EXTRACT) or not episode.transcript
            or not episode.stt_transcript):
        raise RequestInvalid("The transcript is not ready for review")
    now = utcnow()
    claimed = session.execute(
        update(type(job)).where(type(job).job_id == job.job_id,
                               type(job).state == str(JobState.WAITING))
        .values(state=str(JobState.QUEUED), available_at=now, updated_at=now)
    )
    if claimed.rowcount != 1:
        raise RequestInvalid("The transcript was already confirmed")
    episode.transcript = text
    episode.transcript_reviewed_at = now
    episode.transcript_reviewed_by = actor.actor_id
    episode.status = str(EpisodeStatus.EXTRACTING)
    session.commit()
    return ProcessingStatus(episode_id=episode_id, status=EpisodeStatus.EXTRACTING,
                            trace_id=episode.trace_id or None)


@router.get(
    "/{episode_id}/result", response_model=EpisodeResult, response_model_exclude_none=True
)
def read_result(
    episode_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> EpisodeResult:
    """The memories an Episode produced.

    Reading before processing finishes is EPISODE_NOT_READY rather than an empty
    result, so a client polling can tell "not yet" from "nothing was found" — and
    like the status, it is readable only by the Actor that captured the Episode.
    """
    episode = EpisodeRepository(session).require_for(episode_id, actor_id=actor.actor_id)
    if episode.status != str(EpisodeStatus.READY) or episode.model_version is None:
        raise EpisodeNotReady(
            f"Episode {episode_id} is {episode.status}, not ready"
        )

    items = MemoryRepository(session).items_for(episode_id)
    return EpisodeResult(
        episode_id=episode.episode_id,
        status="ready",
        memory_items=[
            MemoryItem(
                memory_type=item.memory_type,
                content=item.content,
                source_type=item.source_type,
                evidence_ids=list(item.evidence_ids),
                confidence=item.confidence,
                model_version=item.model_version,
                prompt_version=item.prompt_version,
                schema_version=item.schema_version,
                effective_at=None
                if item.effective_at is None
                else as_utc(item.effective_at),
                metadata=item.item_metadata,
            )
            for item in items
        ],
        model_version=episode.model_version,
        trace_id=episode.trace_id or None,
    )


@router.get("/{episode_id}/audio")
def read_audio(episode_id: str, actor: Actor = Depends(current_actor),
               store: ObjectStore = Depends(_object_store),
               session: Session = Depends(get_session)) -> Response:
    episode = EpisodeRepository(session).require_for(episode_id, actor_id=actor.actor_id)
    return Response(content=store.get(episode.audio_object_key),
                    media_type=episode.audio_content_type,
                    headers={"Cache-Control": "private, no-store"})


@router.post("/{episode_id}/retry", response_model=ProcessingStatus, response_model_exclude_none=True)
def retry_processing(episode_id: str, actor: Actor = Depends(current_actor),
                     session: Session = Depends(get_session)) -> ProcessingStatus:
    episode = EpisodeRepository(session).require_for(episode_id, actor_id=actor.actor_id)
    job = JobRepository(session).for_episode(episode_id)
    if episode.status != str(EpisodeStatus.FAILED) or job is None or job.state != str(JobState.FAILED):
        raise RequestInvalid("Only a failed Episode can be retried")
    job.state = str(JobState.QUEUED)
    job.attempts = 0
    job.available_at = utcnow()
    job.lease_owner = None
    job.lease_expires_at = None
    episode.status = str(STAGE_STATUS[JobStage(job.stage)])
    episode.error_code = None
    episode.error_message = None
    session.commit()
    return ProcessingStatus(episode_id=episode_id, status=EpisodeStatus(episode.status),
                            trace_id=episode.trace_id or None)


@router.post('/{episode_id}/reextract-empty', response_model=ProcessingStatus, response_model_exclude_none=True)
def reextract_empty(episode_id: str, request: Request, actor: Actor = Depends(current_actor),
                    session: Session = Depends(get_session)) -> ProcessingStatus:
    """Explicit recovery for a valid but empty extraction; never revive deletions."""
    from ..models import MemoryItem as MemoryRow
    from ..access import publication_lock
    from ..retrieval import invalidate_answers
    publication_lock(session, '')
    episode = EpisodeRepository(session).require_for(episode_id, actor_id=actor.actor_id)
    job = JobRepository(session).for_episode(episode_id)
    any_memory = session.scalar(select(MemoryRow.memory_item_id).where(MemoryRow.episode_id == episode_id).limit(1))
    if (episode.status != 'ready' or not episode.transcript_reviewed_at or not episode.transcript
            or job is None or any_memory is not None):
        raise RequestInvalid('仅可重新整理已核对且从未产生记忆的空结果；已删除内容不会恢复。')
    job.stage, job.state, job.attempts = str(JobStage.EXTRACT), str(JobState.QUEUED), 0
    job.available_at = job.updated_at = utcnow()
    job.lease_owner = job.lease_expires_at = None
    episode.status = str(EpisodeStatus.EXTRACTING)
    episode.error_code = episode.error_message = None
    invalidate_answers(session, request.app.state.object_store, episode.subject_id)
    session.commit()
    return ProcessingStatus(episode_id=episode_id, status=EpisodeStatus.EXTRACTING, trace_id=episode.trace_id or None)

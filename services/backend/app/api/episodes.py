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
  failed processing run survivable. Phase 1 has no roles, so any authenticated
  actor can read any Episode; see the README's note on what is not here yet.

`job_id` appears nowhere in a response. Work is addressed by `episode_id`, and the
contract's test asserts the job id never leaks.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..contracts import EpisodeCreated, EpisodeResult, MemoryItem, ProcessingStatus
from ..config import Settings
from ..db import get_session
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
    ConsentScope,
    Episode,
    EpisodeStatus,
    as_utc,
)
from ..repositories.consents import ConsentRepository
from ..repositories.episodes import (
    EpisodeRepository,
    audio_object_key,
    new_episode_id,
)
from ..repositories.jobs import JobRepository
from ..repositories.memory import MemoryRepository
from ..repositories.subjects import SubjectRepository
from ..security import current_actor
from ..storage.base import ObjectStore, checksum_of

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/episodes", tags=["episode"])

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
        form.recording_consent_id, subject_id=form.subject_id, scope=ConsentScope.RECORDING
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
    episodes.attach_audio(episode, stored, audio_ref=form.audio_ref)

    try:
        session.commit()
    except IntegrityError:
        # Two uploads with the same key raced. The unique index chose one; this
        # request reports the winner rather than a duplicate.
        session.rollback()
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

    return EpisodeCreated(episode_id=episode.episode_id, upload_status="uploaded")


@router.get("/{episode_id}", response_model=ProcessingStatus, response_model_exclude_none=True)
def read_status(
    episode_id: str,
    _actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> ProcessingStatus:
    """Where the Episode is in processing.

    Optional fields are omitted rather than sent as null: the contract types them
    as strings, so an explicit null is not a valid processingStatus. `progress` is
    deliberately absent for a second reason — a number derived from the status
    would only restate it, and a client that read it as real progress would be
    misled.
    """
    episode = EpisodeRepository(session).require(episode_id)
    return ProcessingStatus(
        episode_id=episode.episode_id,
        status=EpisodeStatus(episode.status),
        trace_id=episode.trace_id or None,
        error_code=episode.error_code,
        error_message=episode.error_message,
    )


@router.get(
    "/{episode_id}/result", response_model=EpisodeResult, response_model_exclude_none=True
)
def read_result(
    episode_id: str,
    _actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> EpisodeResult:
    """The memories an Episode produced.

    Reading before processing finishes is EPISODE_NOT_READY rather than an empty
    result, so a client polling can tell "not yet" from "nothing was found".
    """
    episode = EpisodeRepository(session).require(episode_id)
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
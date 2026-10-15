"""Optional post-ASR model pass; preserves the machine transcript and review gate."""
import hashlib
import asyncio
from time import perf_counter
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from .models import CaptureSource, ConsentScope, Episode, utcnow
from .repositories.consents import ConsentRepository

POLICY_VERSION = "asr-proofread-v1"
SOURCES = {str(x) for x in (CaptureSource.ANDROID_MIC, CaptureSource.IOS_MIC,
                           CaptureSource.IMPORT, CaptureSource.WORK_3200)}


def correction_policy(settings):
    if not settings.transcript_correction_enabled or settings.ai_backend != "http":
        return None
    digest = hashlib.sha256((POLICY_VERSION + "|" + settings.ai_core_url.rstrip("/")).encode()).hexdigest()[:24]
    return f"{POLICY_VERSION}:{digest}"


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: str = Field(min_length=1, max_length=120)
    after: str = Field(max_length=120)
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    category: Literal["word", "punctuation", "name", "number", "meaning"]
    action: Literal["auto", "review"]
    reason: str = Field(min_length=1, max_length=180)


class CorrectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: str = Field(min_length=1, max_length=20_000)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_version: str = Field(min_length=1, max_length=200)
    prompt_version: Literal["asr-proofread-v1"]
    edits: list[Change] = Field(max_length=64)


def validate_result(text, value):
    result = CorrectionResult.model_validate(value)
    if result.input_sha256 != hashlib.sha256(text.encode()).hexdigest():
        raise ValueError("Correction source changed")
    edits = sorted(result.edits, key=lambda e: e.start)
    end = 0
    for edit in edits:
        if edit.start < end or text[edit.start:edit.end] != edit.before:
            raise ValueError("Invalid correction location")
        if edit.action == "auto" and edit.category not in {"word", "punctuation"}:
            raise ValueError("Uncertain correction cannot be applied automatically")
        end = edit.end
    rebuilt = text
    for edit in reversed(edits):
        if edit.action == "auto":
            rebuilt = rebuilt[:edit.start] + edit.after + rebuilt[edit.end:]
    if rebuilt != result.draft or not rebuilt.strip():
        raise ValueError("Untracked transcript change")
    return result.model_dump()


class HttpTranscriptCorrector:
    def __init__(self, settings):
        self.policy_id = correction_policy(settings)
        self.url = settings.ai_core_url.rstrip("/") + "/transcripts/correct"
        self.timeout = settings.transcript_correction_timeout_seconds

    def correct(self, text):
        # Bound this optional pass. Provider failure must not cause another ASR job.
        async def request():
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                    async with client.stream("POST", self.url, json={"transcript":text}) as response:
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > 262_144:
                                raise ValueError("Correction response too large")
                            body.extend(chunk)
                return CorrectionResult.model_validate_json(body).model_dump()
        return asyncio.run(request())


def apply_automatic_correction(database, episode, corrector):
    metadata = episode.capture_metadata or {}
    receipt = metadata.get("transcript_correction_receipt")
    if not corrector or not isinstance(receipt, dict) or episode.source not in SOURCES:
        return
    text = episode.transcript
    started = perf_counter()

    def authorized():
        with database.session() as session:
            fresh = session.get(Episode, episode.episode_id)
            grant = (fresh.capture_metadata or {}).get("transcript_correction_receipt", {}) if fresh else {}
            if (not fresh or fresh.transcript_reviewed_at is not None
                    or grant.get("actor_id") != fresh.actor_id or grant.get("policy") != corrector.policy_id):
                return False
            ConsentRepository(session).require_active(fresh.recording_consent_id,
                subject_id=fresh.subject_id, actor_id=fresh.actor_id, scope=ConsentScope.RECORDING)
            return True

    try:
        if not authorized():
            report = {"status":"unavailable"}
        elif not text or len(text) > 12_000:
            report = {"status":"too_long"}
        else:
            result = validate_result(text, corrector.correct(text))
            try:
                allowed = authorized()
            except Exception:
                allowed = False
            if allowed:
                episode.transcript = result["draft"]
                report = {"status":"completed", **result}
            else:
                report = {"status":"unavailable"}
    except Exception:
        # Neither upstream prose nor transcripts belong in ordinary failure logs.
        report = {"status":"failed"}
    report.update(completed_at=utcnow().isoformat(), elapsed_ms=round((perf_counter()-started)*1000))
    episode.capture_metadata = {**metadata, "automatic_correction":report}

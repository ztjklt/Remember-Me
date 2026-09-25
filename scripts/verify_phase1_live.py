"""Verify one real-audio Phase 1 service path against a running local stack.

Run from services/backend with ``uv run --locked python
../../scripts/verify_phase1_live.py``. See the integration runbook for the
required PHASE1_* environment variables. This does not replace Android device
acceptance.
"""

from __future__ import annotations

import hashlib
import math
import mimetypes
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

# Scripts live outside the Backend package and are runnable from its uv project.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/backend"))

import httpx
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts import EpisodeCreated, EpisodeResult, ProcessingStatus
from app.models import Episode, Evidence, MemoryItem, as_utc


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} before running the live check")
    return value


def audio_input() -> tuple[Path, str, str, int]:
    path = Path(required("PHASE1_AUDIO_PATH")).expanduser().resolve()
    if not path.is_file():
        raise ValueError("PHASE1_AUDIO_PATH must point to an existing audio file")
    content_type = {".m4a": "audio/mp4", ".wav": "audio/wav"}.get(
        path.suffix.lower(), mimetypes.guess_type(path.name)[0]
    )
    if content_type is None or not content_type.startswith("audio/"):
        raise ValueError("PHASE1_AUDIO_PATH needs a recognized audio extension")
    checksum = hashlib.sha256()
    size = 0
    with path.open("rb") as audio:
        for chunk in iter(lambda: audio.read(1024 * 1024), b""):
            checksum.update(chunk)
            size += len(chunk)
    if size == 0:
        raise ValueError("PHASE1_AUDIO_PATH is empty")
    return path, content_type, checksum.hexdigest(), size


def check_persistence(
    database_url: str,
    episode_id: str,
    subject_id: str,
    consent_id: str,
    checksum: str,
    size: int,
    recorded_at: datetime,
    result: EpisodeResult,
) -> tuple[str, str]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            episode = session.get(Episode, episode_id)
            if episode is None or episode.subject_id != subject_id:
                raise ValueError("Episode is missing or belongs to a different Subject")
            if episode.recording_consent_id != consent_id:
                raise ValueError("Episode does not retain the supplied recording consent")
            if episode.audio_checksum != checksum or episode.audio_size_bytes != size:
                raise ValueError("Episode audio metadata differs from the uploaded file")
            if as_utc(episode.recorded_at) != recorded_at:
                raise ValueError("Episode lost the supplied recording time")
            if episode.status != "ready" or episode.model_version != result.model_version:
                raise ValueError("Persisted Episode state differs from the result API")
            if episode.stt_backend != "http" or not episode.stt_model_version:
                raise ValueError("Episode did not use the configured HTTP STT adapter")
            if episode.stt_model_version.startswith("fake-stt-"):
                raise ValueError("Episode used fake STT")
            if not episode.transcript or not episode.transcript.strip():
                raise ValueError("Episode has no persisted transcript")
            if episode.transcript.lstrip().startswith("[fake-stt]"):
                raise ValueError("Episode contains a fake STT transcript")
            if result.model_version.startswith("fixture-"):
                raise ValueError("Episode used the AI fixture provider")

            stored = list(session.scalars(
                select(MemoryItem).where(MemoryItem.episode_id == episode_id)
                .order_by(MemoryItem.ordinal)
            ))
            if len(stored) != len(result.memory_items) or not stored:
                raise ValueError("Result Memory count differs from persisted rows")
            evidence_ids: set[str] = set()
            for ordinal, (row, item) in enumerate(zip(stored, result.memory_items)):
                if row.ordinal != ordinal or any((
                    row.memory_type != item.memory_type,
                    row.content != item.content,
                    row.source_type != item.source_type,
                    row.evidence_ids != item.evidence_ids,
                    row.confidence != item.confidence,
                    row.model_version != item.model_version,
                    row.prompt_version != item.prompt_version,
                    row.schema_version != item.schema_version,
                    (as_utc(row.effective_at) if row.effective_at else None)
                    != item.effective_at,
                    row.item_metadata != item.metadata,
                )):
                    raise ValueError(f"Result Memory {ordinal} differs from its persisted row")
                if item.model_version != result.model_version:
                    raise ValueError(f"Memory {ordinal} model version differs from Episode")
                evidence_ids.update(item.evidence_ids)

            evidence = session.scalars(
                select(Evidence).where(Evidence.evidence_id.in_(evidence_ids))
            ).all()
            if {row.evidence_id for row in evidence} != evidence_ids:
                raise ValueError("A Memory references missing Evidence")
            evidence_episodes = session.scalars(
                select(Episode).where(Episode.episode_id.in_(
                    {row.episode_id for row in evidence}
                ))
            ).all()
            if {row.episode_id for row in evidence_episodes} != {
                row.episode_id for row in evidence
            } or any(row.subject_id != subject_id for row in evidence_episodes):
                raise ValueError("Memory Evidence crosses the Subject boundary")
            return episode.stt_model_version, episode.model_version
    finally:
        engine.dispose()


def run() -> None:
    backend_url = required("PHASE1_BACKEND_URL").rstrip("/")
    parsed_url = httpx.URL(backend_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.host:
        raise ValueError("PHASE1_BACKEND_URL must be an HTTP(S) URL")
    if parsed_url.userinfo or parsed_url.query or parsed_url.fragment:
        raise ValueError("PHASE1_BACKEND_URL must be a base URL without credentials or query")
    token = required("PHASE1_ACTOR_TOKEN")
    subject_id = required("PHASE1_SUBJECT_ID")
    consent_id = required("PHASE1_RECORDING_CONSENT_ID")
    database_url = required("PHASE1_DATABASE_URL")
    recorded_at = datetime.fromisoformat(
        required("PHASE1_RECORDED_AT").replace("Z", "+00:00")
    )
    if recorded_at.tzinfo is None:
        raise ValueError("PHASE1_RECORDED_AT must include a UTC offset")
    recorded_at = recorded_at.astimezone(timezone.utc)
    path, content_type, checksum, size = audio_input()
    timeout_seconds = float(os.environ.get("PHASE1_TIMEOUT_SECONDS", "180"))
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("PHASE1_TIMEOUT_SECONDS must be a positive finite number")

    headers = {"Authorization": f"Bearer {token}"}
    capture_source = os.environ.get("PHASE1_CAPTURE_SOURCE", "ANDROID_MIC")
    if capture_source not in {"ANDROID_MIC", "IMPORT"}:
        raise ValueError("PHASE1_CAPTURE_SOURCE must be ANDROID_MIC or IMPORT")
    capture = {
        "subject_id": subject_id,
        "recording_consent_id": consent_id,
        "source": capture_source,
        "recorded_at": recorded_at.isoformat(),
        "audio_ref": path.name,
        "idempotency_key": f"phase1-live-{uuid4().hex}",
    }
    with httpx.Client(timeout=30) as client, path.open("rb") as audio:
        response = client.post(
            backend_url + "/api/v1/episodes",
            headers=headers,
            data=capture,
            files={"file": (path.name, audio, content_type)},
        )
        response.raise_for_status()
        if response.status_code != 201:
            raise ValueError(f"Expected a new Episode (201), got {response.status_code}")
        created = EpisodeCreated.model_validate(response.json())
        episode_id = created.episode_id
        print(f"episode_id={episode_id} upload=201", flush=True)

        deadline = time.monotonic() + timeout_seconds
        while True:
            response = client.get(
                backend_url + f"/api/v1/episodes/{episode_id}", headers=headers
            )
            response.raise_for_status()
            status = ProcessingStatus.model_validate(response.json())
            if status.episode_id != episode_id:
                raise ValueError("Status returned a different Episode")
            if status.status == "failed":
                raise ValueError(f"Episode failed: {status.error_code or 'unknown'}")
            if status.status == "ready":
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Episode remained {status.status} after {timeout_seconds:g}s")
            time.sleep(1)

        response = client.get(
            backend_url + f"/api/v1/episodes/{episode_id}/result", headers=headers
        )
        response.raise_for_status()
        result = EpisodeResult.model_validate(response.json())
        if result.episode_id != episode_id or not result.memory_items:
            raise ValueError("Ready Episode has no same-ID Memory result")
        if status.trace_id != result.trace_id:
            raise ValueError("Status and result have different trace IDs")

    stt_version, ai_version = check_persistence(
        database_url, episode_id, subject_id, consent_id, checksum, size,
        recorded_at, result,
    )
    print(
        f"episode=ready result=200 memories={len(result.memory_items)}"
        f" stt={stt_version} ai={ai_version} persistence=verified"
    )
    print("Service path verified; real-device acceptance remains separate")


if __name__ == "__main__":
    try:
        run()
    except ValidationError:
        print("Live Phase 1 check failed: API response violates the Contract", file=sys.stderr)
        raise SystemExit(1) from None
    except httpx.HTTPStatusError as error:
        print(
            f"Live Phase 1 check failed: HTTP {error.response.status_code}"
            f" at {error.request.url.path}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except httpx.HTTPError:
        print("Live Phase 1 check failed: service connection error", file=sys.stderr)
        raise SystemExit(1) from None
    except SQLAlchemyError:
        print("Live Phase 1 check failed: database readback error", file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, TimeoutError) as error:
        print(f"Live Phase 1 check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None

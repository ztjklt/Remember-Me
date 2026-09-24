"""Focused persistence checks for the live Phase 1 verifier.

Run from services/backend with ``uv run --locked python
../../scripts/test_verify_phase1_live.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from verify_phase1_live import check_persistence
from app.contracts import EpisodeResult
from app.models import Base, Episode, Evidence, MemoryItem


class LivePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="remember-live-check-")
        self.addCleanup(self.temp.cleanup)
        self.database_url = f"sqlite:///{Path(self.temp.name) / 'test.db'}"
        engine = create_engine(self.database_url)
        Base.metadata.create_all(engine)
        now = datetime.now(timezone.utc)
        self.recorded_at = now
        with Session(engine) as session:
            session.add(Episode(
                episode_id="ep_test", subject_id="sub_test", actor_id="actor_test",
                recording_consent_id="consent_test", idempotency_key="test-key",
                source="ANDROID_MIC", recorded_at=now, audio_ref="sample.wav",
                audio_object_key="objects/sample.wav", audio_size_bytes=128,
                audio_content_type="audio/wav", audio_checksum="a" * 64,
                status="ready", trace_id="trace_test", transcript="A real sentence.",
                stt_backend="http", stt_model_version="stt-test-1",
                model_version="ai-test-1",
            ))
            session.add(Evidence(
                evidence_id="ev_test", episode_id="ep_test", source_type="SUBJECT",
                source_ref="ep_test", excerpt="A real sentence.",
            ))
            session.add(MemoryItem(
                memory_item_id="mi_test", episode_id="ep_test", ordinal=0,
                memory_type="EVENT", content="A real sentence.",
                source_type="SUBJECT", evidence_ids=["ev_test"], confidence=0.8,
                model_version="ai-test-1", prompt_version="prompt-test-1",
                schema_version="integration-contract-v0.1",
            ))
            session.commit()
        engine.dispose()
        self.result = EpisodeResult.model_validate({
            "episode_id": "ep_test", "status": "ready", "model_version": "ai-test-1",
            "trace_id": "trace_test", "memory_items": [{
                "memory_type": "EVENT", "content": "A real sentence.",
                "source_type": "SUBJECT", "evidence_ids": ["ev_test"],
                "confidence": 0.8, "model_version": "ai-test-1",
                "prompt_version": "prompt-test-1",
                "schema_version": "integration-contract-v0.1",
            }],
        })

    def verify(self, result: EpisodeResult | None = None) -> tuple[str, str]:
        return check_persistence(
            self.database_url, "ep_test", "sub_test", "consent_test",
            "a" * 64, 128, self.recorded_at, result or self.result,
        )

    def update(self, model: type, id: str, **changes: object) -> None:
        engine = create_engine(self.database_url)
        with Session(engine) as session:
            row = session.get(model, id)
            assert row is not None
            for name, value in changes.items():
                setattr(row, name, value)
            session.commit()
        engine.dispose()

    def test_real_persisted_result_passes(self) -> None:
        self.assertEqual(self.verify(), ("stt-test-1", "ai-test-1"))

    def test_fake_stt_is_rejected(self) -> None:
        self.update(Episode, "ep_test", stt_backend="fake")
        with self.assertRaisesRegex(ValueError, "HTTP STT"):
            self.verify()

    def test_fixture_ai_is_rejected(self) -> None:
        self.update(Episode, "ep_test", model_version="fixture-ai-v2")
        fixture_result = self.result.model_copy(update={"model_version": "fixture-ai-v2"})
        with self.assertRaisesRegex(ValueError, "fixture provider"):
            self.verify(fixture_result)

    def test_missing_evidence_is_rejected(self) -> None:
        self.update(MemoryItem, "mi_test", evidence_ids=["ev_missing"])
        changed = self.result.model_copy(deep=True)
        changed.memory_items[0].evidence_ids = ["ev_missing"]
        with self.assertRaisesRegex(ValueError, "missing Evidence"):
            self.verify(changed)

    def test_result_must_match_stored_memory(self) -> None:
        changed = self.result.model_copy(deep=True)
        changed.memory_items[0].content = "Different content"
        with self.assertRaisesRegex(ValueError, "differs from its persisted row"):
            self.verify(changed)


if __name__ == "__main__":
    unittest.main()

from app.ai_core import FakeAiCoreClient
from app.contracts import AICoreInput
from app.models import Episode, Evidence, MemoryItem
from app.repositories.memory import MemoryRepository
from app.seed import seed_development_data
from sqlalchemy import select


def test_two_episodes_with_the_same_provider_id_store_isolated_stable_evidence(
    client, session, app
):
    seed = seed_development_data(session, subject_name="a", actor_name="a")
    episodes = []
    for key in ("a", "b"):
        response = client.post(
            "/api/v1/episodes",
            headers={"Authorization": "Bearer " + seed.actor_token},
            data={
                "subject_id": seed.subject_id,
                "recording_consent_id": seed.consent_id,
                "audio_ref": "a.wav",
                "idempotency_key": key,
                "source": "IMPORT",
                "recorded_at": "2026-10-03T00:00:00Z",
            },
            files={"file": ("a.wav", b"audio", "audio/wav")},
        )
        episodes.append(session.get(Episode, response.json()["episode_id"]))
    for episode in episodes:
        output = FakeAiCoreClient().process(
            AICoreInput(
                episode_id=episode.episode_id,
                subject_id=seed.subject_id,
                transcript="same",
                existing_model_version="old",
            )
        )
        output.evidence[0].evidence_id = "model-always-returns-evidence-1"
        output.memory_items[0].evidence_ids = ["model-always-returns-evidence-1"]
        MemoryRepository(session).store_result(episode, output)
        session.commit()
        # A retried store returns the same canonical ID, with no duplicate rows.
        MemoryRepository(session).store_result(episode, output)
        session.commit()
    rows = session.scalars(select(Evidence)).all()
    assert len(rows) == 2 and len({r.evidence_id for r in rows}) == 2
    for memory in session.scalars(select(MemoryItem)):
        assert memory.evidence_ids == [
            r.evidence_id for r in rows if r.episode_id == memory.episode_id
        ]

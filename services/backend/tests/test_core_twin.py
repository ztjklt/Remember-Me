"""The iOS branch's provisional Phase 2 read and Original Router boundary."""

from app.contracts import AICoreOutput, Evidence, MemoryItem
from app.models import Episode, EpisodeStatus
from app.repositories.memory import MemoryRepository
from app.seed import seed_development_data
from app.tokens import generate_actor_token, hash_actor_token
from app.models import Actor


def _ready_episode(client, session, seeded, auth):
    response = client.post(
        "/api/v1/episodes",
        headers=auth,
        data={
            "subject_id": seeded.subject_id,
            "recording_consent_id": seeded.consent_id,
            "source": "IMPORT",
            "recorded_at": "2026-09-25T08:00:00Z",
            "audio_ref": "subject.m4a",
            "idempotency_key": "ios-phase2-test",
        },
        files={"file": ("subject.m4a", b"recording", "audio/mp4")},
    )
    assert response.status_code == 201, response.text
    episode = session.get(Episode, response.json()["episode_id"])
    MemoryRepository(session).store_result(
        episode,
        AICoreOutput(
            memory_items=[
                MemoryItem(
                    memory_type="PREFERENCE",
                    content="我喜欢咖啡。",
                    source_type="SUBJECT",
                    evidence_ids=["ev_ios_1"],
                    confidence=0.9,
                    model_version="real-model-1",
                    prompt_version="memory-extractor-v2",
                    schema_version="integration-contract-v0.1",
                )
            ],
            graph_updates=[],
            persona_updates=[],
            evidence=[
                Evidence(
                    evidence_id="ev_ios_1",
                    source_type="SUBJECT",
                    source_ref=episode.episode_id,
                    excerpt="我喜欢咖啡。",
                    confidence=0.95,
                )
            ],
            model_version="real-model-1",
        ),
    )
    episode.status = EpisodeStatus.READY
    session.commit()
    return episode


def test_memories_and_twin_require_actor_isolation_and_independent_consent(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    episode = _ready_episode(client, session, seeded, auth)

    memories = client.get(f"/api/v1/subjects/{seeded.subject_id}/memories", headers=auth)
    assert memories.status_code == 200
    body = memories.json()
    assert body["items"][0]["episode_id"] == episode.episode_id
    assert body["items"][0]["evidence"][0]["excerpt"] == "我喜欢咖啡。"
    assert body["domain_counts"]["Preferences"] == 1
    assert body["domain_counts"]["Decision Patterns"] == 0

    query_path = f"/api/v1/subjects/{seeded.subject_id}/twin/query"
    question = {"question": "我喜欢咖啡吗？", "cloud_twin_consent_id": seeded.consent_id}
    rejected = client.post(query_path, headers=auth, json=question)
    assert rejected.status_code == 403
    assert rejected.json()["error_code"] == "CONSENT_INVALID"

    granted = client.post(
        "/api/v1/consents", headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "CLOUD_TWIN", "evidence_ref": "explicit test grant"},
    )
    assert granted.status_code == 201, granted.text
    consent_id = granted.json()["consent_id"]
    question["cloud_twin_consent_id"] = consent_id

    original = client.post(query_path, headers=auth, json=question)
    assert original.status_code == 200, original.text
    assert original.json()["response_type"] == "ORIGINAL"
    assert original.json()["answer"] == "我喜欢咖啡。"
    assert original.json()["evidence"][0]["evidence_id"] == "ev_ios_1"

    unknown = client.post(
        query_path, headers=auth,
        json={"question": "我最喜欢的城市是什么？", "cloud_twin_consent_id": consent_id},
    )
    assert unknown.status_code == 200
    assert unknown.json()["response_type"] == "SIMULATION"
    assert unknown.json()["confidence"] == 0
    assert unknown.json()["evidence"] == []

    other_token = generate_actor_token()
    session.add(Actor(actor_id="actor_other", display_name="Other", token_hash=hash_actor_token(other_token)))
    session.commit()
    other_auth = {"Authorization": f"Bearer {other_token}"}
    hidden = client.get(f"/api/v1/subjects/{seeded.subject_id}/memories", headers=other_auth)
    assert hidden.status_code == 404
    hidden_query = client.post(query_path, headers=other_auth, json=question)
    assert hidden_query.status_code == 404

    revoked = client.post(f"/api/v1/consents/{consent_id}/revoke", headers=auth)
    assert revoked.status_code == 200
    after_revoke = client.post(query_path, headers=auth, json=question)
    assert after_revoke.status_code == 403


def test_correction_suppresses_original_and_deletion_propagates(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    episode = _ready_episode(client, session, seeded, auth)
    base = f"/api/v1/subjects/{seeded.subject_id}/memories"
    item = client.get(base, headers=auth).json()["items"][0]
    item_path = f"{base}/{item['memory_item_id']}"
    grant = client.post(
        "/api/v1/consents", headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "CLOUD_TWIN"},
    )
    consent_id = grant.json()["consent_id"]
    query = f"/api/v1/subjects/{seeded.subject_id}/twin/query"
    question = {"question": "我喜欢咖啡吗？", "cloud_twin_consent_id": consent_id}

    corrected = client.put(
        item_path + "/correction", headers=auth,
        json={"proposed_content": "我不喜欢咖啡。"},
    )
    assert corrected.status_code == 200
    assert client.get(base, headers=auth).json()["items"][0]["correction"] == "我不喜欢咖啡。"
    assert client.post(query, headers=auth, json=question).json()["response_type"] == "SIMULATION"

    other_token = generate_actor_token()
    session.add(Actor(actor_id="actor_correction_other", display_name="Other", token_hash=hash_actor_token(other_token)))
    session.commit()
    other_auth = {"Authorization": f"Bearer {other_token}"}
    assert client.put(
        item_path + "/correction", headers=other_auth,
        json={"proposed_content": "secret"},
    ).status_code == 404
    assert client.delete(item_path, headers=other_auth).status_code == 404

    assert client.delete(item_path + "/correction", headers=auth).status_code == 204
    assert client.post(query, headers=auth, json=question).json()["response_type"] == "ORIGINAL"
    assert client.delete(item_path, headers=auth).status_code == 204
    assert client.get(base, headers=auth).json()["items"] == []
    assert client.post(query, headers=auth, json=question).json()["response_type"] == "SIMULATION"
    result = client.get(f"/api/v1/episodes/{episode.episode_id}/result", headers=auth)
    assert result.status_code == 200
    assert result.json()["memory_items"] == []

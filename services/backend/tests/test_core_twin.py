"""The iOS branch's provisional Phase 2 read and Original Router boundary."""

import httpx

from app.contracts import AICoreOutput, Evidence, MemoryItem
from app.models import Episode, EpisodeStatus, Evidence as EvidenceRow, MemoryItem as MemoryRow
from app.repositories.memory import MemoryRepository
from app.seed import seed_development_data
from app.tokens import generate_actor_token, hash_actor_token
from app.models import Actor


def _ready_episode(
    client, session, seeded, auth, *,
    key="ios-phase2-test", recorded_at="2026-09-25T08:00:00Z",
    evidence_id="ev_ios_1", content="我喜欢咖啡。",
):
    response = client.post(
        "/api/v1/episodes",
        headers=auth,
        data={
            "subject_id": seeded.subject_id,
            "recording_consent_id": seeded.consent_id,
            "source": "IMPORT",
            "recorded_at": recorded_at,
            "audio_ref": "subject.m4a",
            "idempotency_key": key,
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
                    content=content,
                    source_type="SUBJECT",
                    evidence_ids=[evidence_id],
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
                    evidence_id=evidence_id,
                    source_type="SUBJECT",
                    source_ref=episode.episode_id,
                    excerpt=content,
                    confidence=0.95,
                )
            ],
            model_version="real-model-1",
        ),
    )
    episode.status = EpisodeStatus.READY
    session.commit()
    return episode


def test_memory_graph_preserves_provenance_order_and_suppresses_disputes(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    first = _ready_episode(client, session, seeded, auth)
    second = _ready_episode(
        client, session, seeded, auth,
        key="ios-phase2-second", recorded_at="2026-09-25T09:00:00Z",
        evidence_id="ev_ios_2", content="我现在不喜欢咖啡。",
    )
    path = f"/api/v1/subjects/{seeded.subject_id}/memory-graph"
    response = client.get(path, headers=auth)
    assert response.status_code == 200, response.text
    graph = response.json()
    memories = {node["label"]: node["node_id"] for node in graph["nodes"] if node["kind"] == "MEMORY"}
    assert set(memories) == {"我喜欢咖啡。", "我现在不喜欢咖啡。"}
    relations = {(edge["source_id"], edge["target_id"], edge["relation"]) for edge in graph["edges"]}
    assert (memories["我喜欢咖啡。"], f"episode:{first.episode_id}", "CAPTURED_IN") in relations
    assert (memories["我现在不喜欢咖啡。"], "evidence:ev_ios_2", "SUPPORTED_BY") in relations
    assert (memories["我喜欢咖啡。"], memories["我现在不喜欢咖啡。"], "PRECEDES_IN_DOMAIN") in relations

    other_token = generate_actor_token()
    session.add(Actor(actor_id="actor_graph_other", display_name="Other", token_hash=hash_actor_token(other_token)))
    session.commit()
    assert client.get(path, headers={"Authorization": f"Bearer {other_token}"}).status_code == 404

    memory_id = memories["我喜欢咖啡。"].split(":", 1)[1]
    base = f"/api/v1/subjects/{seeded.subject_id}/memories/{memory_id}"
    assert client.put(base + "/correction", headers=auth, json={"proposed_content": "我不喝咖啡。"}).status_code == 200
    after_correction = client.get(path, headers=auth).json()
    assert memories["我喜欢咖啡。"] not in {node["node_id"] for node in after_correction["nodes"]}
    assert not any(edge["relation"] == "PRECEDES_IN_DOMAIN" for edge in after_correction["edges"])
    assert client.delete(base + "/correction", headers=auth).status_code == 204
    assert client.delete(base, headers=auth).status_code == 204
    after_delete = client.get(path, headers=auth).json()
    assert memories["我喜欢咖啡。"] not in {node["node_id"] for node in after_delete["nodes"]}
    assert f"episode:{second.episode_id}" in {node["node_id"] for node in after_delete["nodes"]}


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


def test_inference_returns_cited_simulation_without_impersonating_subject(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    episode = _ready_episode(client, session, seeded, auth)
    memory = session.query(MemoryRow).filter_by(episode_id=episode.episode_id).one()
    source = session.get(EvidenceRow, "ev_ios_1")
    memory.source_type = "AI_INFERENCE"
    memory.content = "The user likes coffee."
    source.source_type = "AI_INFERENCE"
    source.excerpt = "我喜歡咖啡。"
    session.commit()
    grant = client.post(
        "/api/v1/consents", headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "CLOUD_TWIN"},
    )
    question = {"question": "我喜欢咖啡吗？", "cloud_twin_consent_id": grant.json()["consent_id"]}
    response = client.post(
        f"/api/v1/subjects/{seeded.subject_id}/twin/query", headers=auth, json=question,
    )
    assert response.status_code == 200
    assert response.json()["response_type"] == "SIMULATION"
    assert response.json()["confidence"] <= 0.5
    assert response.json()["evidence"][0]["excerpt"] == "我喜歡咖啡。"
    assert "尚未确认说话人" in response.json()["answer"]


def test_real_provider_semantic_twin_stays_cited_and_rejects_foreign_ids(
    client, session, monkeypatch,
):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    _ready_episode(client, session, seeded, auth)
    consent_id = client.post(
        "/api/v1/consents", headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "CLOUD_TWIN"},
    ).json()["consent_id"]
    client.app.state.settings.ai_backend = "http"
    sent = {}

    def generated(url, *, json, **_kwargs):
        if url.endswith("/persona/reconcile"):
            memory_id = json["memories"][0]["memory_item_id"]
            return httpx.Response(200, json={
                "traits": [{
                    "domain": "Preferences", "statement": "喜欢咖啡",
                    "support_memory_ids": [memory_id], "counter_memory_ids": [],
                    "context": None, "confidence": 0.8, "status": "current",
                    "conflict_type": None,
                }],
                "entities": [{"name": "咖啡", "kind": "TOPIC", "support_memory_ids": [memory_id]}],
                "relations": [], "model_version": "real-persona-model",
                "schema_version": "persona-temporal-v1",
            })
        sent.update(json)
        return httpx.Response(200, json={
            "route": "SIMULATION", "answer": "根据本人录音，他喜欢咖啡。",
            "evidence_ids": ["ev_ios_1"], "confidence": 0.76,
            "model_version": "real-twin-model",
        })

    monkeypatch.setattr("app.api.core_twin.httpx.post", generated)
    path = f"/api/v1/subjects/{seeded.subject_id}/twin/query"
    query = {"question": "我平时喝什么饮品？", "cloud_twin_consent_id": consent_id}
    response = client.post(path, headers=auth, json=query)
    assert response.status_code == 200, response.text
    assert response.json()["response_type"] == "SIMULATION"
    assert response.json()["confidence"] <= 0.8
    assert response.json()["evidence"][0]["evidence_id"] == "ev_ios_1"
    assert response.json()["answer"] == "根据本人录音，他喜欢咖啡。"
    assert "subject_id" not in sent

    def foreign(_url, *, json, **_kwargs):
        return httpx.Response(200, json={
            "route": "SIMULATION", "answer": "不可信的回答",
            "evidence_ids": ["ev_foreign"], "confidence": 0.7,
            "model_version": "real-twin-model",
        })

    monkeypatch.setattr("app.api.core_twin.httpx.post", foreign)
    denied = client.post(path, headers=auth, json=query)
    assert denied.status_code == 502

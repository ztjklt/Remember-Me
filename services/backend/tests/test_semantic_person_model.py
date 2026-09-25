"""Real-model path updates temporal traits, graph and Twin after source changes."""

import httpx
import pytest
from sqlalchemy import select

from app.errors import AiSchemaInvalid
from app.models import MemoryItem
from app.person_model import rebuild_person_model
from app.seed import seed_development_data
from test_core_twin import _ready_episode


def test_backend_rejects_persona_relation_without_shared_entity_evidence(
    client, session, monkeypatch,
):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    _ready_episode(client, session, seeded, auth, key="first", evidence_id="ev_first")
    _ready_episode(client, session, seeded, auth, key="second", evidence_id="ev_second")
    client.app.state.settings.ai_backend = "http"

    def unrelated(_url, *, json, **_kwargs):
        first, second = [item["memory_item_id"] for item in json["memories"]]
        return httpx.Response(200, json={
            "traits": [],
            "entities": [
                {"name": "阿明", "kind": "PERSON", "support_memory_ids": [first]},
                {"name": "北京", "kind": "PLACE", "support_memory_ids": [second]},
            ],
            "relations": [
                {"source_name": "阿明", "target_name": "北京", "relation": "居住于",
                 "support_memory_ids": [first]},
            ],
            "model_version": "real-persona-v1", "schema_version": "persona-temporal-v1",
        })

    monkeypatch.setattr("app.person_model.httpx.post", unrelated)
    with pytest.raises(AiSchemaInvalid):
        rebuild_person_model(
            session, subject_id=seeded.subject_id, actor_id=seeded.actor_id,
            settings=client.app.state.settings,
        )


def test_existing_ready_memories_build_persona_when_snapshot_is_missing(client, session, monkeypatch):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    _ready_episode(client, session, seeded, auth)
    client.app.state.settings.ai_backend = "http"

    def persona(url, *, json, **_kwargs):
        assert url.endswith("/persona/reconcile")
        memory_id = json["memories"][0]["memory_item_id"]
        return httpx.Response(200, json={
            "traits": [{
                "domain": "Preferences", "statement": "我喜欢咖啡。",
                "support_memory_ids": [memory_id], "counter_memory_ids": [],
                "context": None, "confidence": 0.9, "status": "current",
                "conflict_type": None,
            }],
            "entities": [], "relations": [],
            "model_version": "real-persona-v1", "schema_version": "persona-temporal-v1",
        })

    monkeypatch.setattr("app.person_model.httpx.post", persona)
    response = client.get(f"/api/v1/subjects/{seeded.subject_id}/person-model", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["processing_state"] == "ready"
    assert body["model_version"] == "real-persona-v1"
    assert body["domains"]["Preferences"][0]["content"] == "我喜欢咖啡。"


def test_semantic_change_and_correction_recompute_twin_and_graph(client, session, monkeypatch):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    first = _ready_episode(client, session, seeded, auth, key="old",
                           evidence_id="ev_old", content="我以前喜欢咖啡。")
    second = _ready_episode(client, session, seeded, auth, key="new",
                            recorded_at="2026-09-25T09:00:00Z",
                            evidence_id="ev_new", content="我现在不喜欢咖啡。")
    old = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == first.episode_id))
    new = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == second.episode_id))
    client.app.state.settings.ai_backend = "http"
    calls = []

    def provider(url, *, json, **_kwargs):
        if url.endswith("/persona/reconcile"):
            facts = json["memories"]
            calls.append([fact["memory_item_id"] for fact in facts])
            traits = []
            for fact in facts:
                later = next((item for item in facts if item["memory_item_id"] != fact["memory_item_id"]), None)
                superseded = later is not None and fact["memory_item_id"] == old.memory_item_id
                traits.append({
                    "domain": "Preferences", "statement": fact["content"],
                    "support_memory_ids": [fact["memory_item_id"]],
                    "counter_memory_ids": [later["memory_item_id"]] if later else [],
                    "context": None, "confidence": 0.85,
                    "status": "superseded" if superseded else "current",
                    "conflict_type": "changed" if later else None,
                })
            return httpx.Response(200, json={
                "traits": traits,
                "entities": [{"name": "咖啡", "kind": "TOPIC",
                              "support_memory_ids": [fact["memory_item_id"] for fact in facts]}],
                "relations": [], "model_version": "real-persona-v1",
                "schema_version": "persona-temporal-v1",
            })
        assert url.endswith("/twin/answer")
        ids = {fact["evidence_id"] for fact in json["evidence"]}
        selected = "ev_new" if "ev_new" in ids else "ev_old"
        return httpx.Response(200, json={
            "route": "ORIGINAL", "answer": "provider paraphrase must be ignored",
            "evidence_ids": [selected], "confidence": 0.9,
            "model_version": "real-twin-v1",
        })

    monkeypatch.setattr("app.person_model.httpx.post", provider)
    rebuild_person_model(session, subject_id=seeded.subject_id, actor_id=seeded.actor_id,
                         settings=client.app.state.settings)
    session.commit()
    base = f"/api/v1/subjects/{seeded.subject_id}"
    model = client.get(base + "/person-model", headers=auth).json()
    assert model["model_version"] == "real-persona-v1"
    old_trait, new_trait = model["domains"]["Preferences"]
    assert old_trait["status"] == "superseded"
    assert old_trait["valid_to"] == new_trait["valid_from"]
    assert old_trait["counter_evidence_ids"] == ["ev_new"]
    graph = client.get(base + "/memory-graph", headers=auth).json()
    assert any(node["kind"] == "TOPIC" and node["label"] == "咖啡" for node in graph["nodes"])
    assert any(edge["relation"] == "GROUNDED_IN" for edge in graph["edges"])
    graph_node_ids = {node["node_id"] for node in graph["nodes"]}
    assert all(edge["source_id"] in graph_node_ids and edge["target_id"] in graph_node_ids
               for edge in graph["edges"])
    consent = client.post("/api/v1/consents", headers=auth,
                          json={"subject_id": seeded.subject_id, "scope": "CLOUD_TWIN"}).json()
    query = {"question": "现在还爱喝咖啡吗？", "cloud_twin_consent_id": consent["consent_id"]}
    twin = client.post(base + "/twin/query", headers=auth, json=query).json()
    assert twin["response_type"] == "ORIGINAL"
    assert twin["answer"] == "我现在不喜欢咖啡。"
    assert twin["evidence"][0]["evidence_id"] == "ev_new"

    correction = client.put(base + f"/memories/{new.memory_item_id}/correction",
                            headers=auth, json={"proposed_content": "这段转录有误"})
    assert correction.status_code == 200, correction.text
    def unavailable(*_args, **_kwargs):
        raise httpx.ConnectError("provider offline")
    monkeypatch.setattr("app.person_model.httpx.post", unavailable)
    rebuilding = client.get(base + "/person-model", headers=auth).json()
    assert rebuilding["processing_state"] == "rebuilding"
    assert rebuilding["source_memory_ids"] == []
    assert rebuilding["domains"]["Preferences"] == []
    monkeypatch.setattr("app.person_model.httpx.post", provider)
    corrected_twin = client.post(base + "/twin/query", headers=auth, json=query).json()
    assert calls[-1] == [old.memory_item_id]
    assert corrected_twin["evidence"][0]["evidence_id"] == "ev_old"
    assert client.delete(base + f"/memories/{old.memory_item_id}", headers=auth).status_code == 204
    refused = client.post(base + "/twin/query", headers=auth, json=query).json()
    assert refused["confidence"] == 0 and refused["evidence"] == []

"""The real Persona worker must not persist uncited claims or graph edges."""

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.errors import AIOutputInvalid
from app.persona import PersonaInput, PersonaSynthesizer


def source(memory_id: str, content: str, hour: int) -> dict:
    return {
        "memory_item_id": memory_id, "content": content, "domain_hint": "Preferences",
        "source_type": "SUBJECT", "evidence_ids": [f"ev_{memory_id}"],
        "excerpts": [content], "recorded_at": f"2026-09-25T{hour:02d}:00:00Z",
        "effective_at": None, "confidence": 0.9,
    }


class Stub:
    def __init__(self, output: dict):
        self.output = output

    def complete(self, payload, schema, prompt, name):
        assert name == "remember_me_persona_temporal"
        assert len(payload["memories"]) == 2
        assert "counter" in str(schema)
        return self.output


def output() -> dict:
    return {
        "traits": [{
            "domain": "Preferences", "statement": "现在不喜欢咖啡",
            "support_memory_ids": ["m2"], "counter_memory_ids": ["m1"],
            "context": None, "confidence": 0.82, "status": "current",
            "conflict_type": "changed",
        }],
        "entities": [{"name": "咖啡", "kind": "TOPIC", "support_memory_ids": ["m1", "m2"]}],
        "relations": [], "model_version": "untrusted", "schema_version": "untrusted",
    }


def test_persona_reconciles_real_sources_and_stamps_versions():
    payload = PersonaInput(memories=[
        source("m1", "我以前喜欢咖啡", 8), source("m2", "我现在不喜欢咖啡", 9),
    ])
    worker = PersonaSynthesizer(provider=Stub(output()), model_version="real-deepseek")
    result = worker.synthesize(payload)
    assert result.traits[0].counter_memory_ids == ["m1"]
    assert result.model_version == "real-deepseek"
    assert result.schema_version == "persona-temporal-v1"
    with TestClient(create_app(Settings(_env_file=None, environment="test", provider="fixture"),
                               persona_synthesizer=worker)) as client:
        response = client.post("/persona/reconcile", json=payload.model_dump(mode="json"))
    assert response.status_code == 200, response.text


def test_persona_rejects_foreign_citations_and_unsupported_graph():
    payload = PersonaInput(memories=[source("m1", "我以前喜欢咖啡", 8),
                                     source("m2", "我现在不喜欢咖啡", 9)])
    foreign = output()
    foreign["traits"][0]["support_memory_ids"] = ["other_account"]
    with pytest.raises(AIOutputInvalid):
        PersonaSynthesizer(provider=Stub(foreign), model_version="real").synthesize(payload)
    invalid_relation = output()
    invalid_relation["relations"] = [{"source_name": "咖啡", "target_name": "陌生人",
                                      "relation": "喜欢", "support_memory_ids": ["m2"]}]
    with pytest.raises(AIOutputInvalid):
        PersonaSynthesizer(provider=Stub(invalid_relation), model_version="real").synthesize(payload)
    unrelated_relation = output()
    unrelated_relation["entities"] = [
        {"name": "阿明", "kind": "PERSON", "support_memory_ids": ["m2"]},
        {"name": "北京", "kind": "PLACE", "support_memory_ids": ["m2"]},
    ]
    unrelated_relation["relations"] = [
        {"source_name": "阿明", "target_name": "北京", "relation": "居住于", "support_memory_ids": ["m1"]}
    ]
    with pytest.raises(AIOutputInvalid):
        PersonaSynthesizer(provider=Stub(unrelated_relation), model_version="real").synthesize(payload)
    # A pronoun may refer to an entity anchored in another recording. The
    # relation itself still cites a Memory supporting its other endpoint.
    one_sided = output()
    one_sided["entities"] = [
        {"name": "阿明", "kind": "PERSON", "support_memory_ids": ["m1"]},
        {"name": "北京", "kind": "PLACE", "support_memory_ids": ["m2"]},
    ]
    one_sided["relations"] = [
        {"source_name": "阿明", "target_name": "北京", "relation": "居住于", "support_memory_ids": ["m2"]}
    ]
    accepted = PersonaSynthesizer(provider=Stub(one_sided), model_version="real").synthesize(payload)
    assert accepted.relations[0].support_memory_ids == ["m2"]


def test_fixture_refuses_persona_generation():
    with TestClient(create_app(Settings(_env_file=None, environment="test", provider="fixture"))) as client:
        assert client.post("/persona/reconcile", json={"memories": []}).status_code == 503

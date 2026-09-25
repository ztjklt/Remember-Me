"""Twin synthesis can cite only supplied evidence and cannot invent ORIGINAL."""

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.errors import AIOutputInvalid
from app.twin import TwinInput, TwinSynthesizer


def payload() -> dict:
    return {
        "question": "我爱喝什么？",
        "candidates": [{
            "evidence_id": "ev_1", "excerpt": "我喜欢咖啡。",
            "memory_content": "我喜欢咖啡。", "source_type": "SUBJECT",
        }],
    }


class Stub:
    def __init__(self, output: dict):
        self.output = output

    def complete(self, data, schema, prompt, name):
        assert data["question"] == "我爱喝什么？"
        assert schema["type"] == "object"
        assert name == "remember_me_twin_simulation"
        return self.output


def test_fixture_refuses_and_real_stub_stamps_advisory_response():
    settings = Settings(_env_file=None, environment="test", provider="fixture")
    with TestClient(create_app(settings)) as client:
        assert client.post("/twin/simulate", json=payload()).status_code == 503
    synth = TwinSynthesizer(provider=Stub({
        "supported": True,
        "evidence_ids": ["ev_1"], "model_version": "guessed",
    }), model_version="real-local")
    with TestClient(create_app(settings, twin_synthesizer=synth)) as client:
        response = client.post("/twin/simulate", json=payload())
    assert response.status_code == 200, response.text
    assert response.json()["evidence_ids"] == ["ev_1"]
    assert response.json()["model_version"] == "real-local"


def test_unknown_citation_is_rejected_and_unsupported_answer_is_cleared():
    synth = TwinSynthesizer(provider=Stub({
        "supported": True, "evidence_ids": ["ev_other"],
        "model_version": "guessed",
    }), model_version="real")
    with pytest.raises(AIOutputInvalid):
        synth.synthesize(TwinInput.model_validate(payload()))
    unsupported = TwinSynthesizer(provider=Stub({
        "supported": False, "evidence_ids": ["ev_1"],
        "model_version": "guessed",
    }), model_version="real")
    result = unsupported.synthesize(TwinInput.model_validate(payload()))
    assert result.evidence_ids == []

"""Five-dimension comparison stays advisory, versioned and schema-bound."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.calibration import CalibrationAssessor, CalibrationInput
from app.config import Settings
from app.errors import AIOutputInvalid
from app.providers.calibration_http import HttpComparisonProvider


def _payload() -> dict:
    return {
        "question": "我喜欢咖啡吗？",
        "locked_answer": "我喜欢咖啡。",
        "human_answer": "我现在不喜欢咖啡。",
    }


def _output() -> dict:
    dimensions = {
        key: {"verdict": "UNCERTAIN", "rationale": "回答没有提供该维度的信息。"}
        for key in (
            "decision", "reasoning", "value_priority",
            "emotional_reaction", "expression",
        )
    }
    dimensions["expression"] = {"verdict": "DIFFERENT", "rationale": "两次回答的偏好表述不同。"}
    return {
        **dimensions, "overall": "DIFFERENT",
        "model_version": "model-guessed", "assessment_version": "version-guessed",
    }


class StubComparisonProvider:
    def compare(self, payload, schema):
        assert payload.human_answer == "我现在不喜欢咖啡。"
        assert schema["type"] == "object"
        return _output()

    def close(self):
        pass


def test_api_stamps_comparison_and_fixture_does_not_fake_one():
    settings = Settings(_env_file=None, environment="test", provider="fixture")
    with TestClient(create_app(settings)) as client:
        unavailable = client.post("/calibrate", json=_payload())
    assert unavailable.status_code == 503
    assessor = CalibrationAssessor(provider=StubComparisonProvider(), model_version="real-local-model")
    with TestClient(create_app(settings, assessor=assessor)) as client:
        response = client.post("/calibrate", json=_payload())
    assert response.status_code == 200, response.text
    assert response.json()["overall"] == "DIFFERENT"
    assert all(
        response.json()[dimension]["verdict"] == "UNCERTAIN"
        for dimension in (
            "decision", "reasoning", "value_priority", "emotional_reaction", "expression"
        )
    )
    assert response.json()["model_version"] == "real-local-model"
    assert response.json()["assessment_version"] == "calibration-assessment-v1"


def test_ollama_comparison_uses_structured_output_and_excludes_subject_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "done": True, "message": {"content": json.dumps(_output())},
        })

    provider = HttpComparisonProvider(
        kind="ollama_local", base_url="http://127.0.0.1:11434",
        model="qwen", api_key="", timeout_seconds=10,
        max_response_bytes=1024 * 1024,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assessor = CalibrationAssessor(provider=provider, model_version="qwen-real")
    result = assessor.assess(CalibrationInput.model_validate(_payload()))
    assert result.overall == "DIFFERENT"
    assert seen["path"] == "/api/chat"
    assert seen["body"]["think"] is False
    assert seen["body"]["format"]["type"] == "object"
    assert "subject_id" not in seen["body"]["messages"][1]["content"]


def test_openai_compatible_comparison_supports_json_object_mode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(_output())},
        }]})

    provider = HttpComparisonProvider(
        kind="openai_compatible", base_url="https://provider.test",
        model="test-model", api_key="test-secret", structured_output_mode="json_object",
        timeout_seconds=10, max_response_bytes=1024 * 1024,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = CalibrationAssessor(provider=provider, model_version="real-model").assess(
        CalibrationInput.model_validate(_payload())
    )
    assert result.model_version == "real-model"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in seen["body"]["messages"][0]["content"]


def test_invalid_comparison_is_rejected():
    class InvalidProvider(StubComparisonProvider):
        def compare(self, payload, schema):
            return {**_output(), "decision": {"verdict": "CERTAIN", "rationale": "bad"}}

    assessor = CalibrationAssessor(provider=InvalidProvider(), model_version="real")
    with pytest.raises(AIOutputInvalid):
        assessor.assess(CalibrationInput.model_validate(_payload()))


def test_insufficient_locked_answer_cannot_become_a_confident_comparison():
    assessor = CalibrationAssessor(provider=StubComparisonProvider(), model_version="real")
    payload = CalibrationInput.model_validate({
        **_payload(), "locked_answer": "没有足够证据，无法可靠回答。",
    })
    result = assessor.assess(payload)
    assert result.overall == "UNCERTAIN"
    assert all(
        getattr(result, dimension).verdict == "UNCERTAIN"
        for dimension in (
            "decision", "reasoning", "value_priority", "emotional_reaction", "expression"
        )
    )

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.calibration import CalibrationInput, DeepSeekCalibrationProvider
from app.config import Settings
from app.errors import AIOutputInvalid

PAYLOAD = {"question": "我喜欢什么？", "locked_answer": "我喜欢散步",
           "human_answer": "我更喜欢游泳，因为我觉得自由"}
DIMENSIONS = [{"dimension": dimension,
               "alignment": "DIFFERENT" if dimension == "VALUE_PRIORITY" else "NOT_OBSERVED",
               "note": "提到自由" if dimension == "VALUE_PRIORITY" else "没有谈及",
               "human_excerpt": "我觉得自由" if dimension == "VALUE_PRIORITY" else None}
              for dimension in ("DECISION", "REASONING", "VALUE_PRIORITY",
                                "EMOTIONAL_REACTION", "EXPRESSION")]


def _provider(result):
    observed = {}

    def handler(request):
        observed.update(json.loads(request.content))
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(result, ensure_ascii=False)},
        }]})

    return DeepSeekCalibrationProvider(
        base_url="https://api.deepseek.com", api_key="test-secret",
        model="deepseek-v4-flash", timeout_seconds=5,
        client=httpx.Client(transport=httpx.MockTransport(handler))), observed


def test_calibration_limits_input_and_validates_human_excerpt():
    provider, observed = _provider({"summary": "有差异", "dimensions": DIMENSIONS,
                                   "suggested_question": "为什么喜欢游泳？"})
    output = provider.compare(CalibrationInput.model_validate(PAYLOAD))
    assert output.model_version == "deepseek-flash"
    assert observed["thinking"] == {"type": "disabled"}
    assert json.loads(observed["messages"][1]["content"]) == PAYLOAD
    assert "subject_id" not in observed["messages"][1]["content"]

    forged = [dict(item) for item in DIMENSIONS]
    forged[2]["human_excerpt"] = "我从没说过这句话"
    provider, _ = _provider({"summary": "有差异", "dimensions": forged,
                             "suggested_question": None})
    with pytest.raises(AIOutputInvalid):
        provider.compare(CalibrationInput.model_validate(PAYLOAD))


def test_private_calibration_endpoint_refuses_extra_input_without_echo():
    class Provider:
        def compare(self, _payload):
            return {"summary": "有差异", "dimensions": DIMENSIONS,
                    "suggested_question": None, "model_version": "test"}

    app = create_app(Settings(_env_file=None, provider="fixture"), calibration_provider=Provider())
    with TestClient(app) as client:
        assert client.post("/calibrate", json=PAYLOAD).status_code == 200
        invalid = client.post("/calibrate", json={**PAYLOAD, "private_extra": "do not echo"})
        assert invalid.status_code == 422
        assert "do not echo" not in invalid.text

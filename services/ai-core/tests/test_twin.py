import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.errors import AIOutputInvalid
from app.twin import DeepSeekTwinProvider, TwinInput


PAYLOAD = {"question": "我喜欢什么？", "candidates": [{
    "memory_item_id": "mem_1", "statement": "喜欢散步", "domain": "PREFERENCES",
    "evidence": [{"evidence_id": "ev_1", "excerpt": "我喜欢散步", "source_type": "SUBJECT"}],
}]}


def test_deepseek_twin_uses_only_selected_evidence_and_actual_model_identity():
    observed = {}

    def handler(request):
        observed.update(json.loads(request.content))
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({
                "answer": "我喜欢散步", "response_type": "ORIGINAL",
                "evidence_ids": ["ev_1"], "confidence": 0.9,
            }, ensure_ascii=False)},
        }]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DeepSeekTwinProvider(base_url="https://api.deepseek.com", api_key="test-secret",
                                    model="deepseek-v4-flash", timeout_seconds=5, client=http)
    result = provider.answer(TwinInput.model_validate(PAYLOAD))
    assert result.model_version == "deepseek-flash"
    assert observed["thinking"] == {"type": "disabled"}
    assert json.loads(observed["messages"][1]["content"]) == {**PAYLOAD, "candidates": [{
        **PAYLOAD["candidates"][0], "unresolved": False, "traits": [], "graph_facts": []}]}
    assert "subject_id" not in observed["messages"][1]["content"]


def test_twin_provider_rejects_invalid_structured_answer():
    def handler(_request):
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
            "finish_reason": "stop", "message": {"content": '{"response_type":"ORIGINAL"}'},
        }]})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DeepSeekTwinProvider(base_url="https://api.deepseek.com", api_key="test-secret",
                                    model="deepseek-v4-flash", timeout_seconds=5, client=http)
    with pytest.raises(AIOutputInvalid):
        provider.answer(TwinInput.model_validate(PAYLOAD))


def test_private_twin_endpoint_validates_input_without_leaking_payload():
    class Provider:
        def answer(self, payload):
            return {"answer": "现有记录还不足以确定。", "response_type": "UNKNOWN",
                    "evidence_ids": [], "confidence": 0, "model_version": "test"}
    app = create_app(Settings(_env_file=None, provider="fixture"), twin_provider=Provider())
    with TestClient(app) as client:
        assert client.post("/twin", json=PAYLOAD).json()["response_type"] == "UNKNOWN"
        invalid = client.post("/twin", json={"question": "private question", "candidates": [],
                                             "secret_extra": "do not echo"})
        assert invalid.status_code == 422
        assert "do not echo" not in invalid.text

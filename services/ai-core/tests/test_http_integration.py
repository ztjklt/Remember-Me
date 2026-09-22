"""Exercise the complete app -> HTTP adapter -> validation -> wire response path."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app.api import create_app
from app.config import Settings
from app.extractor import MemoryExtractor
from app.providers.openai_compatible import OpenAICompatibleProvider


def completion():
    return {
        "memory_items": [{
            "memory_type": "PREFERENCE", "content": "喜欢咖啡。", "source_type": "AI_INFERENCE",
            "evidence_ids": ["e1"], "confidence": 0.8, "model_version": "guessed",
            "prompt_version": "guessed", "schema_version": "guessed",
            "effective_at": None, "metadata": None,
        }],
        "evidence": [{
            "evidence_id": "e1", "source_type": "SUBJECT", "source_ref": "episode:episode-unicode#span:0-7",
            "excerpt": "🙂我喜欢咖啡。", "span_start": 0, "span_end": 7, "confidence": 0.9,
        }],
        "graph_updates": [], "persona_updates": [], "model_version": "guessed",
    }


@pytest.mark.parametrize("broken", [None, "cross_episode", "missing_span", "invalid_number"])
def test_real_adapter_boundary_preserves_unicode_and_rejects_bad_provenance(broken):
    raw = completion()
    if broken == "cross_episode":
        raw["evidence"][0]["source_ref"] = "episode:another-person#span:0-7"
    elif broken == "missing_span":
        raw["evidence"][0]["span_start"] = raw["evidence"][0]["span_end"] = None
    elif broken == "invalid_number":
        raw["memory_items"][0]["confidence"] = True

    def upstream(request):
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(raw)},
        }]})

    with httpx.Client(transport=httpx.MockTransport(upstream)) as transport:
        provider = OpenAICompatibleProvider(base_url="https://provider.test/v1", api_key="test-only-key", client=transport)
        extractor = MemoryExtractor(provider=provider, model="test", model_version="verified-revision")
        with TestClient(create_app(Settings(environment="test"), extractor=extractor)) as client:
            response = client.post("/process", json={
                "episode_id": "episode-unicode", "subject_id": "subject-unicode",
                "transcript": "🙂我喜欢咖啡。她喜欢茶。", "existing_model_version": "v0",
            })

    if broken:
        assert response.status_code == 502
        assert "咖啡" not in response.text
        assert "test-only-key" not in response.text
    else:
        assert response.status_code == 200
        body = response.json()
        assert body["model_version"] == body["memory_items"][0]["model_version"] == "verified-revision"
        assert body["evidence"][0]["excerpt"] == "🙂我喜欢咖啡。"
        assert "metadata" not in body["memory_items"][0]
        path = Path(__file__).resolve().parents[3] / "packages/contracts/schemas/integration-contract-v0.1.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        target = {"$ref": "#/$defs/aiCoreOutput", "$defs": schema["$defs"]}
        Draft202012Validator(target, format_checker=FormatChecker()).validate(body)


def test_provider_closes_owned_connections_but_not_injected_clients():
    owned = OpenAICompatibleProvider(base_url="https://provider.test/v1", api_key="test-key")
    owned.close()
    assert owned._client.is_closed
    with httpx.Client() as client:
        injected = OpenAICompatibleProvider(base_url="https://provider.test/v1", api_key="test-key", client=client)
        injected.close()
        assert not client.is_closed

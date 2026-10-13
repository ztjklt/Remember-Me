import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable
from app.extractor import MemoryExtractor
from app.providers.base import ModelRequest, StructuredModelProvider


class InvalidProvider(StructuredModelProvider):
    def generate(self, request: ModelRequest) -> dict:
        raise AIOutputInvalid("provider payload contained TOP-SECRET-RAW-PAYLOAD")


class TimeoutProvider(StructuredModelProvider):
    def generate(self, request: ModelRequest) -> dict:
        raise ProviderTimeout("internal timeout detail")


class UnavailableProvider(StructuredModelProvider):
    def generate(self, request: ModelRequest) -> dict:
        raise ProviderUnavailable("internal connection detail")


def _payload() -> dict:
    return {
        "episode_id": "episode-api-1",
        "subject_id": "subject-api-1",
        "transcript": "我喜欢周末去爬山。",
        "existing_model_version": "model-v0",
    }


def _client(*, extractor: MemoryExtractor | None = None) -> TestClient:
    app = create_app(
        Settings(_env_file=None,
            environment="test",
            provider="fixture",
            model="fixture-ai-v1",
            model_version="fixture-ai-v1",
        ),
        extractor=extractor,
    )
    return TestClient(app)


def test_health_is_provider_neutral() -> None:
    with _client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_returns_contract_valid_output_without_backend_identifiers() -> None:
    with _client() as client:
        response = client.post("/process", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"memory_items", "graph_updates", "persona_updates", "evidence", "model_version"}
    assert "episode_id" not in body
    assert "job_id" not in body
    assert "effective_at" not in body["memory_items"][0]
    assert "metadata" not in body["memory_items"][0]


def test_process_rejects_missing_input_with_422() -> None:
    with _client() as client:
        response = client.post("/process", json={"episode_id": "episode-only"})

    assert response.status_code == 422


def test_process_maps_invalid_provider_output_to_safe_502() -> None:
    extractor = MemoryExtractor(
        provider=InvalidProvider(),
        model="test",
        model_version="test-v1",
    )
    with _client(extractor=extractor) as client:
        response = client.post("/process", json=_payload())

    assert response.status_code == 502
    assert response.json() == {
        "error_code": "AI_SCHEMA_INVALID",
        "error_message": "AI Core returned invalid structured output",
    }
    assert "TOP-SECRET-RAW-PAYLOAD" not in response.text


def test_process_maps_provider_timeout_to_504() -> None:
    extractor = MemoryExtractor(provider=TimeoutProvider(), model="test", model_version="test-v1")
    with _client(extractor=extractor) as client:
        response = client.post("/process", json=_payload())

    assert response.status_code == 504
    assert response.json() == {
        "error_code": "AI_TIMEOUT",
        "error_message": "AI Core provider timed out",
    }


def test_process_maps_provider_unavailable_to_503() -> None:
    extractor = MemoryExtractor(provider=UnavailableProvider(), model="test", model_version="test-v1")
    with _client(extractor=extractor) as client:
        response = client.post("/process", json=_payload())

    assert response.status_code == 503
    assert response.json() == {
        "error_code": "AI_UNAVAILABLE",
        "error_message": "AI Core provider is unavailable",
    }


def test_fixture_provider_is_refused_outside_development_and_test() -> None:
    with pytest.raises(ValueError, match="fixture"):
        create_app(Settings(_env_file=None, environment="staging", provider="fixture"))

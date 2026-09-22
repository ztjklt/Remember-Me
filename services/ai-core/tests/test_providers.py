import json

import httpx
import pytest

from app.contracts import AICoreOutput, load_fixture
from app.errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable
from app.prompts import PROMPT_VERSION, SCHEMA_VERSION, build_system_prompt
from app.providers.base import ModelRequest
from app.providers.fixture import FixtureProvider
from app.providers.openai_compatible import OpenAICompatibleProvider


def _request() -> ModelRequest:
    return ModelRequest(
        payload=load_fixture("phase1-happy"),
        system_prompt=build_system_prompt(),
        response_schema=AICoreOutput.model_json_schema(),
        model="test-model",
        model_version="test-model-v1",
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
    )


def _provider_response() -> dict:
    return {
        "memory_items": [],
        "graph_updates": [],
        "persona_updates": [],
        "evidence": [],
        "model_version": "test-model-v1",
    }


def test_fixture_provider_labels_its_output() -> None:
    output = FixtureProvider().generate(_request())

    assert output["model_version"] == "test-model-v1"
    assert output["graph_updates"] == []
    assert output["persona_updates"] == []


def test_openai_compatible_provider_sends_schema_and_parses_json_content() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(_provider_response(), ensure_ascii=False)}}
                ]
            },
        )

    client = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1",
        api_key="secret-key",
        timeout_seconds=3,
        client=client,
    )

    output = provider.generate(_request())

    assert output == _provider_response()
    assert seen["request"]["model"] == "test-model"
    assert seen["request"]["response_format"]["type"] == "json_schema"
    assert seen["request"]["response_format"]["json_schema"]["strict"] is True
    assert seen["request"]["messages"][1]["role"] == "user"


def test_openai_compatible_provider_rejects_invalid_json_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    client = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1",
        api_key="secret-key",
        client=client,
    )

    with pytest.raises(AIOutputInvalid, match="JSON"):
        provider.generate(_request())


def test_openai_compatible_provider_preserves_timeout_class() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out", request=request)

    client = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1",
        api_key="secret-key",
        client=client,
    )

    with pytest.raises(ProviderTimeout):
        provider.generate(_request())


def test_openai_compatible_provider_preserves_connection_class() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("provider unavailable", request=request)

    client = httpx.Client(
        base_url="https://provider.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1",
        api_key="secret-key",
        client=client,
    )

    with pytest.raises(ProviderUnavailable):
        provider.generate(_request())

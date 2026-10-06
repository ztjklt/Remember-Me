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
                    {"finish_reason": "stop", "message": {"content": json.dumps(_provider_response(), ensure_ascii=False)}}
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
    projected = seen["request"]["response_format"]["json_schema"]["schema"]
    assert projected["$defs"]["MemoryItem"]["properties"]["source_type"]["enum"] == ["AI_INFERENCE"]
    assert "SUBJECT" in AICoreOutput.model_json_schema()["$defs"]["MemoryItem"]["properties"]["source_type"]["enum"]
    assert seen["request"]["messages"][1]["role"] == "user"
    assert "enable_thinking" not in seen["request"]
    user = json.loads(seen["request"]["messages"][1]["content"])
    span = user["evidence_spans"][0]
    assert span["excerpt"] == _request().payload.transcript
    assert user["transcript"][span["span_start"]:span["span_end"]] == span["excerpt"]
    assert "喜欢" in seen["request"]["messages"][1]["content"]


def test_openai_compatible_provider_rejects_invalid_json_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]},
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


def _http_provider(handler, **kwargs):
    return OpenAICompatibleProvider(
        base_url="https://provider.test/v1", api_key="test-secret",
        client=httpx.Client(base_url="https://provider.test/v1/", transport=httpx.MockTransport(handler)), **kwargs,
    )


@pytest.mark.parametrize("thinking", [False, True])
def test_provider_sends_thinking_extension_only_when_configured(thinking):
    def handler(request):
        assert json.loads(request.content)["enable_thinking"] is thinking
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(_provider_response())},
        }]})
    assert _http_provider(handler, enable_thinking=thinking).generate(_request()) == _provider_response()


def _assert_strict_schema(node):
    if isinstance(node, dict):
        assert "default" not in node
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(node.get("properties", {}))
        for child in node.values():
            _assert_strict_schema(child)
    elif isinstance(node, list):
        for child in node:
            _assert_strict_schema(child)


def test_outbound_schema_is_strict_and_private_context_stays_local() -> None:
    def handler(request):
        assert str(request.url) == "https://provider.test/v1/chat/completions"
        body = json.loads(request.content)
        _assert_strict_schema(body["response_format"]["json_schema"]["schema"])
        assert b"PRIVATE-SUBJECT-CONTEXT" not in request.content
        assert b"PRIVATE-TRACE" not in request.content
        assert request.extensions["timeout"]["read"] == 2.0
        assert "test-model-v1" in body["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(_provider_response())},
        }]})

    request = _request()
    request.payload.subject_context = {"sensitive": "PRIVATE-SUBJECT-CONTEXT"}
    request.payload.trace_id = "PRIVATE-TRACE"
    provider = _http_provider(handler, timeout_seconds=2.0)
    assert provider.generate(request) == _provider_response()


@pytest.mark.parametrize("status, expected", [(429, ProviderUnavailable), (503, ProviderUnavailable), (408, ProviderTimeout)])
def test_transient_upstream_errors_remain_retryable(status, expected) -> None:
    provider = _http_provider(lambda request: httpx.Response(status, text="PRIVATE-PROVIDER-ERROR"))
    with pytest.raises(expected) as result:
        provider.generate(_request())
    assert "PRIVATE-PROVIDER-ERROR" not in str(result.value)


@pytest.mark.parametrize("reason", ["length", "content_filter", "tool_calls", None])
def test_incomplete_completion_is_rejected_even_if_content_is_valid_json(reason) -> None:
    provider = _http_provider(lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": reason, "message": {"content": json.dumps(_provider_response())},
    }]}))
    with pytest.raises(AIOutputInvalid):
        provider.generate(_request())


def test_refusal_is_not_accepted_as_a_successful_extraction() -> None:
    provider = _http_provider(lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {
            "refusal": "PRIVATE REFUSAL", "content": json.dumps(_provider_response()),
        },
    }]}))
    with pytest.raises(AIOutputInvalid):
        provider.generate(_request())


def test_oversized_provider_response_is_rejected_before_parsing() -> None:
    provider = _http_provider(lambda request: httpx.Response(200, json={
        "padding": "x" * 1_048_577,
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(_provider_response())}}],
    }))
    with pytest.raises(AIOutputInvalid):
        provider.generate(_request())


@pytest.mark.parametrize("envelope", [None, {}, {"choices": []}, {"choices": [None]}, {
    "choices": [{"finish_reason": "stop", "message": None}],
}])
def test_malformed_envelopes_are_schema_errors(envelope):
    provider = _http_provider(lambda request: httpx.Response(200, content=json.dumps(envelope)))
    with pytest.raises(AIOutputInvalid):
        provider.generate(_request())


def test_non_json_infinity_is_rejected_even_inside_freeform_metadata():
    invalid = {**_provider_response(), "metadata": {"number": float("inf")}}
    provider = _http_provider(lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": json.dumps(invalid)},
    }]}))
    with pytest.raises(AIOutputInvalid):
        provider.generate(_request())


def test_streaming_limit_closes_response_without_consuming_unbounded_data():
    class LargeStream(httpx.SyncByteStream):
        reads = 0
        closed = False

        def __iter__(self):
            for _ in range(100):
                self.reads += 1
                yield b"x" * 65_536

        def close(self):
            self.closed = True

    stream = LargeStream()
    provider = _http_provider(lambda request: httpx.Response(200, stream=stream), max_response_bytes=65_536)
    with pytest.raises(AIOutputInvalid):
        provider.generate(_request())
    assert stream.reads == 2
    assert stream.closed


def test_question_answer_sampling_is_fixed_without_changing_memory_requests():
    from dataclasses import replace
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(_provider_response())}}]})
    provider = _http_provider(handler)
    provider.generate(_request())
    provider.generate(replace(_request(), task='twin'))
    assert 'temperature' not in bodies[0]
    assert bodies[1]['temperature'] == 0

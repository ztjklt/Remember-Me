import base64
import json

import httpx
import pytest

from app.config import Settings
from app.errors import SttFailed, SttTimeout, SttUnavailable
from app.stt import build_stt_provider
from app.stt_dashscope import DashScopeSttProvider


@pytest.fixture
def transport(monkeypatch):
    def install(handler):
        sent = []
        def post(url, **kwargs):
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                request = client.build_request("POST", url, **kwargs)
                sent.append(request)
                return client.send(request)
        monkeypatch.setattr(httpx, "post", post)
        return sent
    return install


def provider():
    return DashScopeSttProvider(base_url="https://asr.test", path="/native",
        model="qwen-audio-test", api_key="private-test-key")


@pytest.mark.parametrize("output", [
    {"text": "我叫陈安，是一名研究生。"},
    {"output": {"sentence": {"text": "我叫陈安，是一名研究生。"}}},
])
def test_real_audio_is_encoded_and_native_transcript_preserves_provenance(transport, output):
    sent = transport(lambda request: httpx.Response(200, json={"output": output}))
    result = provider().transcribe(b"recorded-mp4", "audio/mp4")
    body = json.loads(sent[0].content)
    uri = body["input"]["messages"][0]["content"][0]["input_audio"]["data"]
    assert uri.startswith("data:audio/mp4;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"recorded-mp4"
    assert body["parameters"]["format"] == "mp4"
    assert sent[0].headers["authorization"] == "Bearer private-test-key"
    assert result.text == "我叫陈安，是一名研究生。"
    assert result.backend == "dashscope"
    assert result.model_version == "qwen-audio-test"


@pytest.mark.parametrize("status,error", [
    (401, SttFailed), (403, SttFailed), (400, SttFailed),
    (429, SttUnavailable), (503, SttUnavailable), (408, SttTimeout), (504, SttTimeout),
])
def test_provider_failures_are_typed_and_never_expose_response_or_key(transport, status, error):
    transport(lambda request: httpx.Response(status, text="private-test-key raw speech"))
    with pytest.raises(error) as raised:
        provider().transcribe(b"recording", "audio/mp4")
    assert "private-test-key" not in str(raised.value)
    assert "raw speech" not in str(raised.value)


@pytest.mark.parametrize("body", [[], {}, {"output": []}, {"output": {"text": 17}}])
def test_missing_transcript_never_falls_back_to_fake_speech(transport, body):
    transport(lambda request: httpx.Response(200, json=body))
    with pytest.raises(SttFailed, match="transcript"):
        provider().transcribe(b"recording", "audio/mp4")


def test_unsupported_or_oversized_audio_is_rejected_before_network(transport):
    sent = transport(lambda request: pytest.fail("must not send rejected audio"))
    with pytest.raises(SttFailed, match="format"):
        provider().transcribe(b"recording", "text/plain")
    with pytest.raises(SttFailed, match="limit"):
        provider().transcribe(b"x" * (8 * 1024 * 1024), "audio/mp4")
    assert not sent


def test_factory_uses_secret_configuration_and_refuses_missing_credentials():
    settings = Settings(_env_file=None, stt_backend="dashscope", stt_url="https://asr.test",
        stt_path="/native", stt_model="qwen-audio-test", stt_api_key="private-test-key")
    assert isinstance(build_stt_provider(settings), DashScopeSttProvider)
    assert "private-test-key" not in repr(settings)
    assert "private-test-key" not in str(settings.model_dump())
    with pytest.raises(ValueError, match="requires"):
        build_stt_provider(Settings(_env_file=None, stt_backend="dashscope"))

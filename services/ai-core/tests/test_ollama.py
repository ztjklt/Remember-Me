import json

import httpx

from app.contracts import AICoreInput
from app.extractor import MemoryExtractor
from app.providers.ollama import OllamaProvider


def _extract(candidates):
    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5", "digest": "abcdef1234567890"}]})
        body = json.loads(request.content)
        assert body["think"] is False
        assert body["format"]["properties"]["memories"]
        return httpx.Response(200, json={"message": {"content": json.dumps({"memories": candidates}, ensure_ascii=False)}})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", timeout_seconds=5, client=client)
    return MemoryExtractor(provider=provider, model="qwen3.5", model_version="qwen3.5-digest").process(
        AICoreInput(episode_id="ep_1", subject_id="sub_1", transcript="我喜欢喝热茶，但不喜欢咖啡。", existing_model_version="v0")
    )


def test_chinese_quote_is_located_by_code_and_versions_are_stamped():
    output = _extract([{"quote": "不喜欢咖啡", "statement": "不喜欢咖啡", "domain": "PREFERENCES",
                        "memory_type": "PREFERENCE", "confidence": 0.9}])
    assert len(output.memory_items) == 1
    assert output.evidence[0].span_start == 8
    assert output.evidence[0].excerpt == "不喜欢咖啡"
    assert output.persona_updates[0].domain == "PREFERENCES"
    assert output.memory_items[0].model_version == "qwen3.5-abcdef123456"


def test_unmatched_quote_does_not_enter_memory_or_model():
    output = _extract([{"quote": "我每天喝咖啡", "statement": "每天喝咖啡", "domain": "PREFERENCES",
                        "memory_type": "PREFERENCE", "confidence": 0.9}])
    assert output.memory_items == []
    assert output.evidence == []
    assert output.persona_updates == []


def test_model_digest_is_read_from_ollama_at_extraction_time():
    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:latest", "digest": "abcdef1234567890"}]})
        return httpx.Response(200, json={"message": {"content": '{"memories": []}'}})
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", timeout_seconds=5,
                              client=httpx.Client(transport=httpx.MockTransport(respond)))
    output = MemoryExtractor(provider=provider, model="qwen3.5:latest", model_version="operator-label").process(
        AICoreInput(episode_id="ep_1", subject_id="sub_1", transcript="你好", existing_model_version="v0")
    )
    assert output.model_version == "qwen3.5:latest-abcdef123456"

import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.contracts import AICoreInput
from app.extractor import MemoryExtractor
from app.providers.deepseek import DeepSeekProvider


def test_flash_uses_json_mode_without_thinking_and_only_keeps_located_quotes():
    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-only-key"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        assert "sub_1" not in request.content.decode()
        assert body["messages"][1]["content"] == "我喜欢喝热茶，但不喜欢咖啡。"
        return httpx.Response(200, json={
            "model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"memories": [
                    {"quote": "不喜欢咖啡", "statement": "不喜欢咖啡", "domain": "PREFERENCES",
                     "memory_type": "PREFERENCE", "confidence": 0.9},
                    {"quote": "每天喝咖啡", "statement": "每天喝咖啡", "domain": "PREFERENCES",
                     "memory_type": "PREFERENCE", "confidence": 0.9},
                ]}, ensure_ascii=False),
            }}],
        })

    provider = DeepSeekProvider(base_url="https://api.deepseek.com", api_key="test-only-key",
                                timeout_seconds=5,
                                client=httpx.Client(transport=httpx.MockTransport(respond)))
    output = MemoryExtractor(provider=provider, model="deepseek-v4-flash",
                             model_version="operator-label").process(AICoreInput(
        episode_id="ep_1", subject_id="sub_1", transcript="我喜欢喝热茶，但不喜欢咖啡。",
        existing_model_version="v0",
    ))
    assert len(output.memory_items) == 1
    assert output.evidence[0].excerpt == "不喜欢咖啡"
    assert output.model_version == "deepseek-flash"
    assert output.memory_items[0].model_version == "deepseek-flash"
    assert output.persona_updates[0].model_version == "deepseek-flash"


@pytest.mark.parametrize("overrides", [
    {"base_url": "http://api.deepseek.com"},
    {"base_url": "https://example.com"},
    {"base_url": "https://api.deepseek.com:8443"},
    {"api_key": ""},
    {"model": "deepseek-v4-pro"},
])
def test_flash_key_cannot_be_sent_to_an_unapproved_host(overrides):
    settings = {"provider": "deepseek", "model": "deepseek-v4-flash",
                "model_version": "deepseek-flash", "base_url": "https://api.deepseek.com",
                "api_key": "test-only-key", "_env_file": None}
    settings.update(overrides)
    with pytest.raises(ValidationError):
        Settings(**settings)


def test_profile_worker_uses_flash_and_preserves_owner_review_and_source_handles(monkeypatch):
    from fastapi.testclient import TestClient
    from app import api
    from app.providers.deepseek_chat import DeepSeekChat
    def remote(request):
        assert str(request.url) == 'https://api.deepseek.com/chat/completions'
        body=json.loads(request.content)
        assert body['model']=='deepseek-flash' and body['thinking']=={'type':'disabled'}
        assert 'real-source' not in request.content.decode()
        return httpx.Response(200,json={'model':'deepseek-flash','choices':[{
            'finish_reason':'stop','message':{'content':json.dumps({'candidates':[{
                'domain':'PREFERENCES','statement':'偏好热茶','context':'饮品选择',
                'evidence_ids':['s1'],'counter_evidence_ids':[],'kind':'trait'}]})}}]})
    with httpx.Client(transport=httpx.MockTransport(remote)) as transport:
        monkeypatch.setattr(api,'DeepSeekChat',lambda **kw:DeepSeekChat(**kw,client=transport))
        settings=Settings(provider='deepseek',model='deepseek-flash',model_version='deepseek-flash',
            base_url='https://api.deepseek.com',api_key='fixture-key',_env_file=None)
        with TestClient(api.create_app(settings)) as client:
            result=client.post('/profile-proposals',json={'materials':[{
                'evidence_id':'real-source','episode_id':'fixture-episode','excerpt':'我更喜欢热茶。'}]})
        assert result.status_code==200
        proposal=result.json()['candidates'][0]
        assert proposal['evidence_ids']==['real-source']
        assert 'status' not in proposal and 'confidence' not in proposal


@pytest.mark.parametrize('status', [401, 307])
def test_flash_profile_transport_does_not_retry_or_forward_credential(status):
    from app.providers.deepseek_chat import DeepSeekChat
    from app.errors import AICoreError
    calls=[]
    def remote(request):
        calls.append(request)
        return httpx.Response(status,headers={'Location':'https://other.invalid'},text='fixture private body')
    with httpx.Client(transport=httpx.MockTransport(remote)) as client:
        chat=DeepSeekChat(api_key='fixture-key',model='deepseek-flash',client=client)
        with pytest.raises(AICoreError) as error:chat.complete('JSON',{})
    assert len(calls)==1 and 'private body' not in str(error.value)

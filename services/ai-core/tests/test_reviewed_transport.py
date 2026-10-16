"""Slow verified voice calls get one bounded backup, with identical evidence."""
import asyncio
import json

import httpx
import pytest

from app.errors import AIOutputInvalid, ProviderTimeout, ProviderRateLimited
from test_weixin_deadline import bounded_chat, envelope


def test_slow_review_closes_first_before_identical_retry(monkeypatch):
    requests=[]; closed=[]
    async def handle(request):
        number=len(requests)+1; requests.append(json.loads(request.content))
        if number==2: assert closed==[1]
        try:
            if number==1: await asyncio.sleep(10)
            return httpx.Response(200,json=envelope())
        finally: closed.append(number)
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=1,json_retry_after_seconds=.1):
            assert chat.complete('review',{'source':'full evidence'},timeout_seconds=45)[0]=={'valid':True}
        assert len(requests)==2 and requests[0]==requests[1]
        assert set(closed)=={1,2}
    finally: chat.close()


def test_fast_generation_and_review_keep_separate_full_checks(monkeypatch):
    seen=[]
    async def handle(request):
        seen.append(json.loads(request.content)['messages'][0]['content'])
        return httpx.Response(200,json=envelope())
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=1,json_retry_after_seconds=.1):
            chat.complete('generation',{})
            chat.complete('review',{})
        assert seen==['generation','review']
    finally: chat.close()


def test_review_deadline_never_resets_and_no_lingering_requests(monkeypatch):
    calls=[]; closed=[]
    async def handle(request):
        number=len(calls)+1; calls.append(number)
        try: await asyncio.sleep(10)
        finally: closed.append(number)
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=.5,json_retry_after_seconds=.1):
            with pytest.raises(ProviderTimeout): chat.complete('review',{})
        assert calls==[1,2] and set(closed)=={1,2}
    finally: chat.close()


def test_rate_limit_is_not_retried(monkeypatch):
    requests=[]
    async def handle(request):
        requests.append(request); return httpx.Response(429)
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=1,json_retry_after_seconds=.1):
            with pytest.raises(ProviderRateLimited): chat.complete('review',{})
        assert len(requests)==1
    finally: chat.close()


def test_outer_persona_retry_cannot_multiply_managed_attempts():
    from app.persona import PersonaInput, PersonaProvider
    from test_persona import payload, ScriptedChat
    chat=ScriptedChat(ProviderTimeout('bounded attempts exhausted'))
    chat.json_retry_managed=True
    with pytest.raises(ProviderTimeout):
        PersonaProvider(chat).answer(PersonaInput.model_validate(dict(payload(),voice_response=True)))
    assert len(chat.requests)==1


def test_malformed_backup_cannot_publish_after_stalled_primary_closed(monkeypatch):
    calls=[]
    async def handle(request):
        number=len(calls)+1;calls.append(number)
        if number==1:
            await asyncio.sleep(.2)
            return httpx.Response(200,json=envelope())
        return httpx.Response(200,text='broken JSON')
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=1,json_retry_after_seconds=.1):
            with pytest.raises(AIOutputInvalid):chat.complete('review',{})
        assert calls==[1,2]
    finally:chat.close()


@pytest.mark.parametrize('json_delay',[None,1.5])
def test_persona_http_voice_uses_backup_policy_and_keeps_review(monkeypatch,json_delay):
    from contextlib import contextmanager
    from app.providers.weixin import WeixinChat
    from test_persona import payload, point, review, ScriptedChat, post
    scopes=[]
    monkeypatch.setenv('AI_VOICE_RETRY_AFTER_SECONDS','3')
    monkeypatch.delenv('AI_VOICE_JSON_RETRY_AFTER_SECONDS',raising=False)
    if json_delay is not None:
        monkeypatch.setenv('AI_VOICE_JSON_RETRY_AFTER_SECONDS',str(json_delay))
    @contextmanager
    def scope(self,**options):
        scopes.append(options);yield
    monkeypatch.setattr(WeixinChat,'transport_scope',scope)
    # Reviewed JSON recovery can be tuned without shortening streamed requests.
    chat=ScriptedChat({'points':[point()]},review())
    response=post(monkeypatch,dict(payload(),voice_response=True),chat,provider='weixin')
    assert response.status_code==200,response.text
    assert scopes==[{'timeout_seconds':8.0,'json_retry_after_seconds':3.0 if json_delay is None else json_delay}]
    assert len(chat.requests)==2 and 'review_scope' in chat.requests[1][1]

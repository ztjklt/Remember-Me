"""Exercise the real bounded HTTP transport with local in-memory responses."""
import asyncio
import json
import time

import httpx
import pytest

from app.errors import AIOutputInvalid, ProviderTimeout, ProviderUnavailable
from app.providers.weixin import WeixinChat


def envelope():
    return {'model':'Deepseek-v4-flash','choices':[{'finish_reason':'stop',
        'message':{'content':'{"valid":true}'}}]}


def bounded_chat(monkeypatch, handler, **options):
    chat = WeixinChat(api_key='test-only', **options)
    monkeypatch.setattr(chat, '_async_client', lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False))
    return chat


def test_bounded_transport_uses_requested_timeout_and_parses_json(monkeypatch):
    requests = []
    async def handle(request):
        requests.append(request)
        return httpx.Response(200, json=envelope())
    chat = bounded_chat(monkeypatch, handle)
    try:
        value, model = chat.complete('system', {}, timeout_seconds=12)
        assert value == {'valid':True} and model == 'Deepseek-v4-flash'
        assert requests[0].extensions['timeout']['read'] == 12
    finally: chat.close()


def test_total_deadline_cancels_slow_chunk_stream_and_closes_it(monkeypatch):
    state = {'closed':False,'yielded':0}
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(20):
                await asyncio.sleep(.015)
                state['yielded'] += 1
                yield b' '
        async def aclose(self):
            state['closed'] = True
    async def handle(request):
        return httpx.Response(200, stream=SlowStream())
    chat = bounded_chat(monkeypatch, handle)
    started = time.monotonic()
    try:
        with pytest.raises(ProviderTimeout):
            chat.complete('system', {}, timeout_seconds=.04)
        assert time.monotonic()-started < .5
        assert 0 < state['yielded'] < 20 and state['closed']
    finally: chat.close()


@pytest.mark.parametrize('status,error', [(503,ProviderUnavailable),(504,ProviderTimeout),(400,AIOutputInvalid)])
def test_deadline_transport_preserves_provider_errors(monkeypatch,status,error):
    chat = bounded_chat(monkeypatch, lambda request: httpx.Response(status))
    try:
        with pytest.raises(error): chat.complete('system',{},timeout_seconds=1)
    finally: chat.close()


def test_bounded_transport_retains_response_size_limit(monkeypatch):
    chat = bounded_chat(monkeypatch, lambda request:httpx.Response(200,json=envelope()),max_response_bytes=10)
    try:
        with pytest.raises(AIOutputInvalid): chat.complete('system',{},timeout_seconds=1)
    finally: chat.close()


def test_voice_request_reuses_transport_between_generation_and_review_and_closes_scope(monkeypatch):
    chat=WeixinChat(api_key='test-only');clients=[];loops=[]
    async def handle(request):
        loops.append(asyncio.get_running_loop());return httpx.Response(200,json=envelope())
    def create():
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle));clients.append(client);return client
    monkeypatch.setattr(chat,'_async_client',create)
    try:
        with chat.transport_scope():
            assert chat.complete('generation',{},timeout_seconds=1)[0]=={'valid':True}
            assert chat.complete('review',{},timeout_seconds=1)[0]=={'valid':True}
            assert len(clients)==1 and not clients[0].is_closed
            assert loops[0] is loops[1]
        assert clients[0].is_closed
        with chat.transport_scope():chat.complete('different user',{},timeout_seconds=1)
        assert len(clients)==2 and all(c.is_closed for c in clients)
    finally:chat.close()


def test_transport_places_complete_material_before_changing_question_without_dropping_fields(monkeypatch):
    captured=[]
    async def handle(request):
        captured.append(json.loads(request.content));return httpx.Response(200,json=envelope())
    chat=bounded_chat(monkeypatch,handle)
    payload={'question':'后来呢？','recordings':[{'text':'之前不喜欢；后来改变了。'}],
        'conversation_only_not_evidence':[{'heard_answer':'刚才的话'}],
        'response_schema':{'type':'object'},'confirmed_understanding':[]}
    try:
        chat.complete('system',payload,timeout_seconds=1)
        text=captured[0]['messages'][1]['content']
        assert json.loads(text)==payload
        assert text.index('recordings') < text.index('question')
        assert text.index('confirmed_understanding') < text.index('question')
    finally:chat.close()


def test_voice_scope_caps_each_request_without_changing_normal_requests(monkeypatch):
    seen=[]
    async def handle(request):
        seen.append(request.extensions['timeout']['read'])
        return httpx.Response(200,json=envelope())
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=8):
            chat.complete('generation',{},timeout_seconds=45)
            chat.complete('review',{},timeout_seconds=3)
        chat.complete('normal',{},timeout_seconds=45)
        assert seen==[8,3,45]
    finally:chat.close()

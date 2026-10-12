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

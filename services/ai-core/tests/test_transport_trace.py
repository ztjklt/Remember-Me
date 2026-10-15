import asyncio
import json

import httpx
import pytest

from app.errors import ProviderTimeout
from app.providers.weixin import WeixinChat


def test_stream_timeout_records_phase_without_logging_request_secrets(monkeypatch, caplog):
    chat = WeixinChat(api_key='private-test-key')
    async def handle(request):
        trace = request.extensions.get('trace')
        if trace:
            await trace('connection.connect_tcp.started', {'host':'private-host'})
            await trace('connection.connect_tcp.complete', {'return_value':'private-object'})
            await trace('http11.send_request_body.started', {'request':request})
            await trace('http11.send_request_body.complete', {})
            await trace('http11.receive_response_headers.started', {})
        await asyncio.sleep(1)
    monkeypatch.setattr(chat, '_async_client', lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        with pytest.raises(ProviderTimeout):
            chat.complete_stream('secret-prompt', {}, on_point=lambda *a:None, timeout_seconds=.03)
    finally:
        chat.close()
    row = next(json.loads(r.message) for r in caplog.records if 'weixin_chat_stream' in r.message)
    assert row.get('timeout_phase') == 'response_headers'
    assert row['transport']['request_sent_ms'] < row['duration_ms']
    assert row['transport']['connect_ms'] >= 0
    assert all(secret not in json.dumps(row) for secret in ('private-test-key','secret-prompt','private-host','private-object'))


def test_stream_times_first_content_separately_from_complete_point(monkeypatch, caplog):
    chat = WeixinChat(api_key='test-only')
    def event(content, finish=None):
        return ('data: '+json.dumps({'model':'actual','choices':[{'delta':{'content':content},'finish_reason':finish}]})+'\n\n').encode()
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield event('{"points":[')
            await asyncio.sleep(.02)
            yield event('{"known":false,"source_ids":[]}]}', 'stop')
            yield b'data: [DONE]\n\n'
    monkeypatch.setattr(chat, '_async_client', lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=Body()))))
    try:
        chat.complete_stream('system',{},on_point=lambda *a:None)
    finally:
        chat.close()
    row = next(json.loads(r.message) for r in caplog.records if 'weixin_chat_stream' in r.message)
    assert row.get('first_content_ms') is not None
    assert row['first_content_ms'] < row['first_point_ms']
    assert row['transport']['headers_ms'] <= row['first_content_ms']


def test_retried_transport_validates_winner_and_never_emits_failed_draft(monkeypatch):
    from app.errors import AIOutputInvalid
    chat=WeixinChat(api_key='test'); calls=[]; seen=[]; closed=[]
    class Body(httpx.AsyncByteStream):
        def __init__(self, number): self.number=number
        async def __aiter__(self):
            value={'points':[{'known':True,'source_ids':['private' if self.number==1 else 's1']}]}
            data={'model':'actual','choices':[{'delta':{'content':json.dumps(value)},'finish_reason':'stop'}]}
            yield ('data: '+json.dumps(data)+'\n\ndata: [DONE]\n\n').encode()
        async def aclose(self): closed.append(self.number)
    async def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,stream=Body(len(calls)))
    monkeypatch.setattr(chat,'_async_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    def validate(result,model):
        if result['points'][0]['source_ids']!=['s1']:raise AIOutputInvalid('not visible')
    try:
        with chat.transport_scope(timeout_seconds=1,retry_after_seconds=.05):
            result,_=chat.complete_stream('system',{},on_point=lambda p,m:seen.append(p),validate_result=validate)
            assert chat.stream_retry_managed
            with pytest.raises(ProviderTimeout):
                chat.complete_stream('repair',{},on_point=lambda *a:None)
        assert calls[0]==calls[1] and len(calls)==2
        assert seen==result['points'] and seen[0]['source_ids']==['s1']
        assert set(closed)=={1,2}
    finally:chat.close()


def test_cancelled_source_request_cannot_start_a_network_retry(monkeypatch):
    from threading import Event
    from app.cancellation import cancelled_request
    from app.errors import ProviderUnavailable
    stopped=Event(); token=cancelled_request.set(stopped);calls=[]
    chat=WeixinChat(api_key='test')
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            stopped.set()
            yield b'data: {}\n\n'
    async def handle(request):calls.append(request);return httpx.Response(200,stream=Body())
    monkeypatch.setattr(chat,'_async_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        with chat.transport_scope(timeout_seconds=1,retry_after_seconds=.2):
            with pytest.raises(ProviderUnavailable):
                chat.complete_stream('system',{},on_point=lambda *a:None)
        assert len(calls)==1
    finally:
        cancelled_request.reset(token);chat.close()

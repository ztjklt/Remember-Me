import asyncio
import json
import httpx
import pytest
from app.providers.weixin import WeixinChat
from app.quoted_twin import QuotedTwin
from test_grounded_twin import data
from test_voice_fast import collect


def test_first_complete_point_prepares_before_generation_ends():
    class Chat:
        def complete_stream(self, system, payload, *, on_point, **kw):
            point={'known':True,'source_ids':['s1']}
            on_point(point,'test')
            return {'points':[point]},'test'
    payload=data();payload.voice_response=True
    events=collect(lambda:QuotedTwin(Chat()).answer(payload),review_required=False,stream_generation=True)
    assert [e['type'] for e in events]==['draft','draft','final']
    assert events[-1]['semantic_review']=='skipped'


def test_streamed_compact_input_can_still_use_semantic_review():
    class Chat:
        def complete_stream(self, system, payload, *, on_point, **kw):
            assert 'source_columns' in payload['recordings'][0]
            return {'points':[{'known':True,'source_ids':['s1']}]},'test'
        def complete(self, system, payload):
            assert payload['cited_material'][0]['sources'][0]['id']=='s1'
            return dict(reasoning='Source attribution is intact.',valid=True,
                        failure_codes=[],replacement=None),'test'
    payload=data();payload.voice_response=True
    events=collect(lambda:QuotedTwin(Chat()).answer(payload),review_required=True,stream_generation=True)
    assert events[-1]['type']=='final'


def test_stream_transport_validates_stop_and_calls_point_before_eof(monkeypatch):
    chat=WeixinChat(api_key='test-only');seen=[]
    def sse(content=None,finish=None):
        return ('data: '+json.dumps({'model':'actual','choices':[{'index':0,'delta':{'content':content},'finish_reason':finish}]})+'\n\n').encode()
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse('{"points":[{"known":true,"source_ids":["s1"]}')
            assert seen==[({'known':True,'source_ids':['s1']},'actual')]
            yield sse(']}','stop')
            yield b'data: [DONE]\n\n'
    def serve(req):
        body=json.loads(req.content);assert body['stream'] is True
        assert body['model']=='Deepseek-v4-flash'
        return httpx.Response(200,stream=Body())
    monkeypatch.setattr(chat,'_async_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(serve)))
    try:
        result,model=chat.complete_stream('system',{},on_point=lambda p,m:seen.append((p,m)))
        assert model=='actual' and result['points'][0]==seen[0][0]
    finally:chat.close()


@pytest.mark.parametrize('suffix',['','data: [DONE]\n\n'])
def test_missing_stop_cannot_publish_completed_result(monkeypatch,suffix):
    from app.errors import AIOutputInvalid
    chat=WeixinChat(api_key='test-only')
    message={'model':'actual','choices':[{'delta':{'content':'{"points":[{"known":false,"source_ids":[]}]}'}}]}
    transport=httpx.MockTransport(lambda req:httpx.Response(200,text='data: '+json.dumps(message)+'\n\n'+suffix))
    monkeypatch.setattr(chat,'_async_client',lambda:httpx.AsyncClient(transport=transport))
    try:
        with pytest.raises(AIOutputInvalid):chat.complete_stream('system',{},on_point=lambda *a:None)
    finally:chat.close()

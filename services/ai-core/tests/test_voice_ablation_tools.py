"""Isolated experiment controls. No production review policy changes."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'/'voice_call'))
from ablation_core import SSE, CompletePoints, StreamFailure, fast_answer
from test_grounded_twin import data


def test_sse_handles_split_utf8_and_requires_terminal_stop():
    wire=('data: '+json.dumps({'model':'Deepseek-v4-flash','choices':[{'delta':{'content':'陈岚'},'finish_reason':None}]},ensure_ascii=False)+'\n\n'+
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n').encode()
    decoder=SSE();events=[]
    for byte in wire:events.extend(decoder.feed(bytes([byte])))
    decoder.finish()
    assert events[0]['choices'][0]['delta']['content']=='陈岚'


@pytest.mark.parametrize('wire',[
    b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n',
    b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n',
    b'data: {"error":{"message":"bad"}}\n\n',
])
def test_sse_truncation_errors_are_not_success(wire):
    with pytest.raises(StreamFailure):
        decoder=SSE();list(decoder.feed(wire));decoder.finish()


def test_only_complete_point_is_released_before_final_json():
    parser=CompletePoints()
    assert parser.feed('{"points":[{"known":true,"source_ids":["s1"')==[]
    assert parser.feed(']}')==[{'known':True,'source_ids':['s1']}]
    assert parser.feed(',{"known":false,"source_ids":[]}]')==[{'known':False,'source_ids':[]}]
    parser.feed('}')
    assert len(parser.finish()['points'])==2


@pytest.mark.parametrize('text',['{"points":[{"known":true,"source_ids":["s1"]}',
    '{"points":[{"known":true,"source_ids":["s1"]}],"other":1}',
    '{"points":[{"known":true,"source_ids":["s1"]}],"points":[]}'])
def test_final_json_must_be_complete_and_unambiguous(text):
    with pytest.raises(StreamFailure):
        parser=CompletePoints();parser.feed(text);parser.finish()


def test_fast_uses_same_selection_prompt_but_does_not_claim_review():
    class Chat:
        def __init__(self):self.calls=[]
        def complete(self,prompt,payload):
            self.calls.append((prompt,payload))
            return {'points':[{'known':True,'source_ids':['s1']}]},'actual'
    from app.quoted_twin import SYSTEM
    chat=Chat();value=fast_answer(chat,data())
    assert len(chat.calls)==1 and chat.calls[0][0]==SYSTEM
    assert '同事老周' in value.answer


def test_fast_still_rejects_nonexistent_evidence():
    class Chat:
        def complete(self,*args):return {'points':[{'known':True,'source_ids':['missing']}]},'actual'
    from app.errors import AIOutputInvalid
    with pytest.raises(AIOutputInvalid):fast_answer(Chat(),data())


def test_fast_keeps_baseline_selection_timeout_retry(monkeypatch):
    from app.errors import ProviderTimeout
    class Chat:
        calls=0
        def complete(self,*args):
            self.calls+=1
            if self.calls==1:raise ProviderTimeout('test timeout')
            return {'points':[{'known':True,'source_ids':['s1']}]},'actual'
    chat=Chat()
    assert fast_answer(chat,data()).model_version=='actual'
    assert chat.calls==2


def test_fast_keeps_baseline_selection_repair():
    class Chat:
        def __init__(self):self.prompts=[]
        def complete(self,prompt,payload):
            self.prompts.append(prompt)
            if len(self.prompts)==1:return {'bad':'shape'},'actual'
            assert 'schema_errors' in payload and 'rejected_draft' in payload
            return {'points':[{'known':True,'source_ids':['s1']}]},'actual'
    chat=Chat()
    assert fast_answer(chat,data()).model_version=='actual'
    assert len(chat.prompts)==2 and '这是唯一一次修正' in chat.prompts[1]


@pytest.mark.anyio
async def test_cancelled_blocking_generation_cannot_start_late_draft():
    import asyncio
    import threading
    from contextlib import nullcontext
    from app.cancellation import cancelled_request
    from run_ablation import run_once
    entered=threading.Event();release=threading.Event();finished=threading.Event()
    observed=[];spoken=[]
    class Chat:
        def transport_scope(self,**kw):return nullcontext()
        def complete(self,*args):
            observed.append(cancelled_request.get());entered.set()
            release.wait(2)
            finished.set()
            return {'points':[{'known':True,'source_ids':['s1']}]},'actual'
    async def tts(text):
        spoken.append(text)
        yield b'\0\0'
    task=asyncio.create_task(run_once('A',data().model_copy(update={'voice_response':True}),Chat(),None,tts,prepared_module(),None))
    assert await asyncio.to_thread(entered.wait,1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    release.set()
    await asyncio.to_thread(finished.wait,1)
    await asyncio.sleep(.02)
    assert observed[0] is not None and observed[0].is_set()
    assert not spoken


def prepared_module():
    from run_ablation import load
    return load(Path(__file__).resolve().parents[2]/'backend'/'app'/'prepared_speech.py', 'test_prepared')


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_first_point_reaches_tts_before_whole_stream_finishes():
    import asyncio
    from run_ablation import run_once
    from app.quoted_twin import render_ids
    emitted=asyncio.Event()
    result,_=render_ids({'points':[{'known':True,'source_ids':['s1']}]},data(),'actual')
    async def tts(text):
        emitted.set()
        yield b'\0\0'
    async def stream(payload,on_point,record):
        await on_point(result)
        await asyncio.wait_for(emitted.wait(),1)
        return result
    record=await run_once('C',data(),None,stream,tts,prepared_module(),None)
    assert record['status']=='ok'
    assert record['first_pcm_ms']<=record['validated_text_ms']
    assert record['review']=='not_run'


@pytest.mark.anyio
async def test_final_failure_after_audio_is_not_reported_success():
    import asyncio
    from run_ablation import run_once
    from app.quoted_twin import render_ids
    emitted=asyncio.Event();closed=asyncio.Event()
    result,_=render_ids({'points':[{'known':True,'source_ids':['s1']}]},data(),'actual')
    async def tts(text):
        try:
            yield b'\0\0'
            emitted.set()
            await asyncio.Event().wait()
        finally: closed.set()
    async def stream(payload,on_point,record):
        await on_point(result)
        await asyncio.wait_for(emitted.wait(),1)
        raise StreamFailure('truncated')
    record=await run_once('C',data(),None,stream,tts,prepared_module(),None)
    assert record['status']=='partial_failed' and closed.is_set()


@pytest.mark.anyio
async def test_cancellation_stops_late_audio():
    import asyncio
    from run_ablation import run_once
    from app.quoted_twin import render_ids
    emitting=asyncio.Event();closed=asyncio.Event()
    result,_=render_ids({'points':[{'known':True,'source_ids':['s1']}]},data(),'actual')
    async def tts(text):
        try:
            yield b'\0\0';emitting.set()
            await asyncio.Event().wait()
        finally:closed.set()
    async def stream(payload,on_point,record):
        await on_point(result)
        await asyncio.Event().wait()
    task=asyncio.create_task(run_once('C',data(),None,stream,tts,prepared_module(),None))
    await asyncio.wait_for(emitting.wait(),1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert closed.is_set()


@pytest.mark.anyio
async def test_second_unknown_point_can_add_quote_wrapper_without_changing_first_fact():
    from run_ablation import run_once
    from app.quoted_twin import render_ids
    payload=data().model_copy(update={'voice_response':True})
    points=[{'known':True,'source_ids':['s1']},{'known':False,'source_ids':[]}]
    first,_=render_ids({'points':points[:1]},payload,'actual')
    final,_=render_ids({'points':points},payload,'actual')
    async def tts(text):yield b'\0\0'
    async def stream(payload,on_point,record):
        await on_point(first)
        return final
    result=await run_once('C',payload,None,stream,tts,prepared_module(),None)
    assert result['status']=='ok'


@pytest.mark.anyio
async def test_changed_first_fact_still_fails():
    from run_ablation import run_once
    from app.quoted_twin import render_ids
    payload=data().model_copy(update={'voice_response':True})
    first,_=render_ids({'points':[{'known':True,'source_ids':['s1']}]},payload,'actual')
    final=first.model_copy(update={'answer':'完全不同的答案。'})
    async def tts(text):yield b'\0\0'
    async def stream(payload,on_point,record):
        await on_point(first)
        return final
    result=await run_once('C',payload,None,stream,tts,prepared_module(),None)
    assert result['status'] in ('failed','partial_failed')


@pytest.mark.anyio
async def test_invalid_stream_keeps_bounded_selection_and_failure_stage(monkeypatch):
    import httpx
    import run_ablation
    from app.errors import AIOutputInvalid
    raw='{"points":[{"known":true,"source_ids":["absent"]}]}'
    event={'model':'actual','choices':[{'delta':{'content':raw}}]}
    real=httpx.AsyncClient
    transport=httpx.MockTransport(lambda request:httpx.Response(200,
        headers={'content-type':'text/event-stream'},content=('data: '+json.dumps(event)+'\n\n').encode()))
    monkeypatch.setattr(run_ablation.httpx,'AsyncClient',lambda **kw:real(transport=transport,**kw))
    record={}
    async def on_point(result):pytest.fail('invalid source was released')
    with pytest.raises(AIOutputInvalid):
        await run_ablation.streamed_selection('test-only',data(),on_point,record,1)
    assert record['partial_selection_text']==raw
    assert record['stream_stage']=='point_validation'


@pytest.mark.anyio
async def test_stream_retries_timeout_before_release_only(monkeypatch):
    import run_ablation
    calls=[]
    async def stream(key,payload,on_point,record,timeout):
        calls.append(1)
        if len(calls)==1:raise TimeoutError()
        return 'completed'
    monkeypatch.setattr(run_ablation,'streamed_selection',stream)
    record={}
    assert await run_ablation.stream_with_retry('test-only',data(),None,record)=='completed'
    assert len(calls)==2
    assert 'error' not in record
    assert record['stream_attempts'][0]['error']=='TimeoutError'


@pytest.mark.anyio
async def test_stream_cannot_retry_after_releasing_a_point(monkeypatch):
    import run_ablation
    calls=[]
    async def stream(key,payload,on_point,record,timeout):
        calls.append(1)
        await on_point('point')
        raise TimeoutError()
    async def on_point(value):pass
    monkeypatch.setattr(run_ablation,'streamed_selection',stream)
    with pytest.raises(TimeoutError):
        await run_ablation.stream_with_retry('test-only',data(),on_point,{})
    assert len(calls)==1


@pytest.mark.anyio
async def test_valid_content_before_malformed_sse_in_same_chunk_is_auditable(monkeypatch):
    import httpx
    import run_ablation
    raw='{"points":['
    event={'model':'actual','choices':[{'delta':{'content':raw}}]}
    real=httpx.AsyncClient
    wire=('data: '+json.dumps(event)+'\n\ndata: {bad}\n\n').encode()
    transport=httpx.MockTransport(lambda request:httpx.Response(200,
        headers={'content-type':'text/event-stream'},content=wire))
    monkeypatch.setattr(run_ablation.httpx,'AsyncClient',lambda **kw:real(transport=transport,**kw))
    record={}
    async def on_point(result):pytest.fail('incomplete point released')
    with pytest.raises(StreamFailure):
        await run_ablation.streamed_selection('test-only',data(),on_point,record,1)
    assert record['partial_selection_text']==raw

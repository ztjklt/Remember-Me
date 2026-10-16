import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from starlette.websockets import WebSocketDisconnect
from test_reader_understandings import prepare
from test_persona_dialogue import cloud
from app.api import voice_sessions as api


def test_only_one_simultaneous_connection_can_claim_a_call():
    call=api.Call('id','subject','actor',None)
    barrier=threading.Barrier(8)
    def claim(_):
        barrier.wait();return call.claim()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(claim,range(8)))==1


def test_cancel_before_transport_and_during_registration(monkeypatch):
    from types import SimpleNamespace
    from app.realtime_providers import RealtimeFailure
    async def run():
        bridge=api.AsyncTwinBridge(asyncio.get_running_loop(),SimpleNamespace(ai_core_url='http://invalid'),[],threading.Event())
        bridge.cancel()
        with pytest.raises(RealtimeFailure): await bridge._request('/twin',{})
        with pytest.raises(RealtimeFailure): bridge.request('/twin',{})
        bridge=api.AsyncTwinBridge(asyncio.get_running_loop(),SimpleNamespace(),[],threading.Event())
        entered=threading.Event(); release=threading.Event(); cancellation=threading.Event()
        original=asyncio.run_coroutine_threadsafe
        async def transport(*args): await asyncio.sleep(30)
        bridge._request=transport
        def registering(coro,loop):
            future=original(coro,loop); entered.set();release.wait(2);return future
        monkeypatch.setattr(asyncio,'run_coroutine_threadsafe',registering)
        worker=asyncio.create_task(asyncio.to_thread(bridge.request,'/twin',{}))
        assert await asyncio.to_thread(entered.wait,2)
        def cancel(): cancellation.set();bridge.cancel()
        killer=asyncio.create_task(asyncio.to_thread(cancel))
        assert await asyncio.to_thread(cancellation.wait,2)
        release.set()
        await killer
        with pytest.raises((asyncio.CancelledError,RealtimeFailure, __import__('concurrent.futures').futures.CancelledError)):
            await worker
        assert not bridge.futures
    asyncio.run(run())


def setup_call(app,client,session):
    owner,reader,oh,rh,*_=prepare(app,client,session)
    app.state.settings.realtime_voice_enabled=True
    app.state.settings.realtime_voice_actor_ids=[owner.actor_id]
    consent=cloud(client,owner.subject_id,oh)
    body=dict(cloud_consent_id=consent,mode='evidence',policy='continuous-voice-v1',
              cloud_asr_allowed=True,cloud_tts_allowed=True)
    return owner,oh,rh,body


def test_reviewed_voice_prepares_retrieval_without_early_answer_or_audio(app,client,session,monkeypatch):
    owner,oh,_,body=setup_call(app,client,session)
    app.state.settings.realtime_voice_prefetch_enabled=True
    requests=[];prepared=threading.Event()
    class ASR:
        def __init__(self,*args):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def send(self,audio):pass
        async def events(self):
            yield dict(type='transcript',text='我家以前在哪里',final=False)
            await asyncio.to_thread(prepared.wait,.7)
            yield dict(type='transcript',text='我家以前不在哪里？',final=True)
            await asyncio.sleep(10)
    def generate(*args,**kwargs):
        requests.append((args[1].question,kwargs))
        if kwargs.get('prepare_only'):
            prepared.set();return None
        raise RuntimeError('End fixture after inspecting the real final dispatch')
    monkeypatch.setattr(api,'ParaformerRealtime',ASR)
    monkeypatch.setattr(api,'generate_answer',generate)
    created=client.post(f'/api/v1/subjects/{owner.subject_id}/voice-sessions',headers=oh,json=body).json()
    assert app.state.voice_sessions[created['session_id']].payload.response_speed=='reviewed'
    events=[]
    with client.websocket_connect(created['websocket_path'],headers=oh) as ws:
        while True:
            event=ws.receive_json();events.append(event)
            if event['type']=='error':break
        ws.send_json({'type':'end'})
    assert prepared.is_set()
    assert [q for q,_ in requests]==['我家以前在哪里','我家以前不在哪里？']
    early,final=[kw for _,kw in requests]
    assert early['material_cache'] is final['material_cache']
    assert early['selection_cache'] is final['selection_cache']
    assert final['on_source_prepared'] is None  # Never speak an unreviewed source.
    assert final['material_cache'] is not None and final['selection_cache'] is not None
    assert not any(e['type'] in {'audio','answer_ready'} for e in events)


def test_step_engine_requires_explicit_gate_and_keeps_pipeline_default(app,client,session):
    from pydantic import SecretStr
    owner,oh,_,body=setup_call(app,client,session)
    path=f'/api/v1/subjects/{owner.subject_id}/voice-sessions'
    assert client.get('/api/v1/voice-capabilities',headers=oh).json()['engines']==['pipeline']
    step=dict(body,engine='step_realtime',response_speed='fast')
    assert client.post(path,headers=oh,json=step).status_code==404
    app.state.settings.realtime_voice_fast_enabled=True
    app.state.settings.step_realtime_enabled=True
    app.state.settings.step_realtime_api_key=SecretStr('test')
    assert 'step_realtime' in client.get('/api/v1/voice-capabilities',headers=oh).json()['engines']
    created=client.post(path,headers=oh,json=step)
    assert created.status_code==201,created.text
    default=client.post(path,headers=oh,json=body)
    assert app.state.voice_sessions[default.json()['session_id']].payload.engine=='pipeline'
    assert client.post(path,headers=oh,json=dict(step,purpose='calibration_report')).status_code==404


def test_fast_voice_is_explicit_and_does_not_change_default_or_calibration(app,client,session):
    owner,oh,_,body=setup_call(app,client,session)
    path=f'/api/v1/subjects/{owner.subject_id}/voice-sessions'
    assert client.get('/api/v1/voice-capabilities',headers=oh).json()['response_speeds']==['reviewed']
    fast=dict(body,response_speed='fast')
    assert client.post(path,headers=oh,json=fast).status_code==404
    app.state.settings.realtime_voice_fast_enabled=True
    assert client.get('/api/v1/voice-capabilities',headers=oh).json()['response_speeds']==['reviewed','fast']
    created=client.post(path,headers=oh,json=fast)
    assert created.status_code==201,created.text
    assert app.state.voice_sessions[created.json()['session_id']].payload.response_speed=='fast'
    default=client.post(path,headers=oh,json=body)
    assert app.state.voice_sessions[default.json()['session_id']].payload.response_speed=='reviewed'
    assert client.post(path,headers=oh,json=dict(fast,purpose='calibration_report')).status_code==404


def test_fast_bridge_routes_privately_and_requires_skip_metadata(monkeypatch):
    import httpx
    from types import SimpleNamespace
    original=httpx.AsyncClient
    requests=[]
    def serve(request):
        requests.append(request.url.path)
        return httpx.Response(200,text='{"type":"final","semantic_review":"skipped","result":{"answer":"原话"}}\n')
    monkeypatch.setattr(api.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(serve),**kw))
    async def run():
        async def draft(text):pass
        bridge=api.AsyncTwinBridge(asyncio.get_running_loop(),SimpleNamespace(ai_core_url='http://ai'),[],threading.Event(),draft,response_speed='fast')
        result=await bridge._request('/twin',{'voice_response':True})
        assert requests==['/twin/voice-fast']
        assert result['semantic_review']=='skipped'
    asyncio.run(run())


def test_streamed_voice_has_separate_gate_and_never_changes_calibration(app,client,session):
    owner,oh,_,body=setup_call(app,client,session)
    app.state.settings.realtime_voice_fast_enabled=True
    path=f'/api/v1/subjects/{owner.subject_id}/voice-sessions'
    body=dict(body,response_speed='streamed')
    assert client.post(path,headers=oh,json=body).status_code==404
    app.state.settings.realtime_voice_streamed_enabled=True
    assert client.post(path,headers=oh,json=body).status_code==201
    assert client.post(path,headers=oh,json=dict(body,purpose='calibration_report')).status_code==404


def test_optin_consent_and_socket_identity_are_required(app,client,session):
    owner,oh,rh,body=setup_call(app,client,session)
    assert not client.get('/api/v1/voice-capabilities',headers=rh).json()['enabled']
    path=f'/api/v1/subjects/{owner.subject_id}/voice-sessions'
    assert client.post(path,headers=rh,json=body).status_code==404
    assert client.post(path,headers=oh,json=dict(body,cloud_asr_allowed=False)).status_code==422
    created=client.post(path,headers=oh,json=body)
    assert created.status_code==201,created.text
    url=created.json()['websocket_path']
    for kwargs,suffix in [({},''),({'headers':rh},''),({'headers':oh},'?token=forbidden')]:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(url+suffix,**kwargs): pass
    assert client.delete('/api/v1/voice-sessions/'+created.json()['session_id'],headers=rh).status_code==404
    assert client.delete('/api/v1/voice-sessions/'+created.json()['session_id'],headers=oh).status_code==200


@pytest.mark.parametrize('new_source',[False,True])
def test_pause_reopens_asr_and_expired_identity_ends_call(app,client,session,monkeypatch,new_source):
    owner,oh,_,body=setup_call(app,client,session)
    if new_source:
        from sqlalchemy import select
        from app.models import Episode,Evidence
        episode=session.scalar(select(Episode).where(Episode.subject_id==owner.subject_id))
        episode.transcript+='。这句新核对的原话还没有提取记忆。';session.commit()
    instances=[]
    class ASR:
        def __init__(self,*args): self.q=asyncio.Queue(); self.closed=False;instances.append(self)
        async def __aenter__(self): return self
        async def __aexit__(self,*args): self.closed=True
        async def send(self,audio): pass
        async def events(self):
            while True: yield await self.q.get()
    class TTS:
        def __init__(self,*args): pass
        async def stream(self,text): yield bytes(32)
    monkeypatch.setattr(api,'ParaformerRealtime',ASR);monkeypatch.setattr(api,'XiaomiRealtime',TTS)
    result=client.post(f'/api/v1/subjects/{owner.subject_id}/voice-sessions',headers=oh,json=body).json()
    with client.websocket_connect(result['websocket_path'],headers=oh) as ws:
        assert ws.receive_json()['type']=='ready'
        if new_source:
            session.expire_all()
            assert any('这句新核对' in e.excerpt for e in session.scalars(select(Evidence)))
        ws.send_json({'type':'pause'})
        assert ws.receive_json()['type']=='interrupted'
        assert ws.receive_json()==dict(type='paused',session_id=result['session_id'],turn_id=1,paused=True)
        assert instances[0].closed
        ws.send_json({'type':'resume'})
        assert ws.receive_json()['paused'] is False
        assert len(instances)==2
        ws.send_json({'type':'end'})
    assert all(i.closed for i in instances)
    assert result['session_id'] not in app.state.voice_sessions

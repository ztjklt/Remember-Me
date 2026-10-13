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

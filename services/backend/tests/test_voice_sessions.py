import asyncio
import pytest
from starlette.websockets import WebSocketDisconnect
from test_reader_understandings import prepare
from test_persona_dialogue import cloud
from app.api import voice_sessions as api


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


def test_pause_reopens_asr_and_expired_identity_ends_call(app,client,session,monkeypatch):
    owner,oh,_,body=setup_call(app,client,session)
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

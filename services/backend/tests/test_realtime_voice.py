"""Authorization, expiry, source invalidation and live generation boundaries."""
from datetime import timedelta
import hashlib
import io
import math
import struct
import wave
from urllib.parse import urlsplit,parse_qs
import jwt
import pytest
from sqlalchemy import select
from app.models import TwinAnswer, DeviceCredential, utcnow
from app.realtime_models import VoiceCall, RealtimeVoiceProfile
from app.realtime_access import policy
from app.realtime_provider import AlibabaVoice, RealtimeUnavailable, validate_sample
from app.seed import seed_development_data
from app.twin_basis import current
from app.tokens import hash_actor_token
from test_twin_voice import _record,TinyEncoder,QuoteTwin


class Provider:
    def __init__(self):self.operations=[];self.fail_delete=False;self.after_chunk=None
    def configured(self):return True
    def operation(self,action,**fields):
        self.operations.append((action,fields))
        if action=='create_voice':return {'voice_id':'cosy-fixture'}
        if action=='query_voice':return {'status':'OK','target_model':'cosyvoice-v3-flash'}
        if self.fail_delete:raise RealtimeUnavailable('fixture provider down')
        return {}
    async def speech(self,text,voice,model):
        self.operations.append(('speech',{'text':text,'voice':voice}))
        yield b'\x01\x00'*480
        if self.after_chunk:self.after_chunk()
        yield b'\x02\x00'*480


@pytest.fixture
def ready(app,client,session):
    own=seed_development_data(session,subject_name='Voice own',actor_name='Voice own')
    other=seed_development_data(session,subject_name='Other',actor_name='Other')
    headers={'Authorization':'Bearer '+own.actor_token}
    s=app.state.settings
    s.realtime_enabled=True;s.livekit_url='wss://rtc.fixture.invalid';s.livekit_api_url='https://rtc.fixture.invalid'
    s.livekit_api_key='fixture-key';s.livekit_api_secret='fixture-livekit-secret-with-32-chars';s.realtime_worker_secret='x'*32
    # Assignment on Settings does not parse SecretStr, so explicitly wrap secrets.
    from pydantic import SecretStr
    for field in ['livekit_api_key','livekit_api_secret','realtime_worker_secret']:setattr(s,field,SecretStr(getattr(s,field)))
    s.realtime_public_url='https://backend.fixture.invalid'
    app.state.realtime_provider=Provider()
    cloud=client.post('/api/v1/consents',headers=headers,json={'subject_id':own.subject_id,'scope':'CLOUD_TWIN'}).json()['consent_id']
    voice=client.post('/api/v1/consents',headers=headers,json={'subject_id':own.subject_id,'scope':'VOICE'}).json()['consent_id']
    profile=RealtimeVoiceProfile(profile_id='rvp_fixture',subject_id=own.subject_id,actor_id=own.actor_id,consent_id=voice,
        accepted_policy=policy(s),sample_key='own/sample',reference_text='本人的样本',provider_voice_id='cosy-fixture',model=s.cosyvoice_model,status='ready',
        fetch_digest='',fetch_expires_at=utcnow(),created_at=utcnow())
    app.state.object_store.put(profile.sample_key,b'private sample','audio/mp4')
    session.add(profile);session.commit()
    return own,other,headers,cloud,voice,profile


def start(client,app,ready):
    own,_,headers,cloud,voice,_=ready
    return client.post(f'/api/v1/subjects/{own.subject_id}/twin/voice/calls',headers=headers,
        json={'cloud_consent_id':cloud,'voice_consent_id':voice,'policy':policy(app.state.settings)})


def internal():return {'Authorization':'Bearer '+'x'*32}


def answer(session,own,kind='SIMULATION'):
    row=TwinAnswer(answer_id='ta_fixture',subject_id=own.subject_id,actor_id=own.actor_id,question='喜欢什么？',
        answer='喜欢散步。',response_type=kind,confidence=.8,evidence_ids=[],memory_item_ids=[],
        model_version='fixture',person_model_version=1,source_basis=current(session,own.subject_id),created_at=utcnow())
    session.add(row);session.commit();return row


def bind(session,call_id,answer_id):
    row=session.get(VoiceCall,call_id);row.active_turn='turn';row.active_answer_id=answer_id;session.commit()


def test_ticket_is_room_scoped_short_lived_and_contains_no_actor_or_provider_secrets(ready,client,app):
    own,other,headers,cloud,voice,_=ready
    result=start(client,app,ready);assert result.status_code==200,result.text
    ticket=result.json();claims=jwt.decode(ticket['token'],app.state.settings.livekit_api_secret.get_secret_value(),algorithms=['HS256'])
    assert claims['video']['room']==ticket['call_id']==ticket['room']
    assert claims['sub']==ticket['participant_identity']
    assert claims['video']['canPublishSources']==['microphone']
    assert claims['exp']-claims['nbf']==120
    assert 'roomAdmin' not in claims['video']
    assert own.actor_token not in result.text and 'cosy-fixture' not in result.text
    assert not client.get('/internal/voice-calls/'+ticket['call_id']+'/authorize',headers=headers).is_success
    assert client.get('/internal/voice-calls/'+ticket['call_id']+'/authorize',headers=internal()).status_code==200
    assert client.post(f'/api/v1/subjects/{other.subject_id}/twin/voice/calls',headers=headers,
        json={'cloud_consent_id':cloud,'voice_consent_id':voice,'policy':policy(app.state.settings)}).status_code==404


def test_recording_consent_never_authorizes_voice_or_changed_policy(ready,client,app):
    own,_,headers,cloud,voice,_=ready
    path=f'/api/v1/subjects/{own.subject_id}/twin/voice/calls'
    assert client.post(path,headers=headers,json={'cloud_consent_id':cloud,'voice_consent_id':own.consent_id,'policy':policy(app.state.settings)}).status_code==403
    assert client.post(path,headers=headers,json={'cloud_consent_id':cloud,'voice_consent_id':voice,'policy':'old'}).status_code==503


def test_expiry_and_logout_stop_worker_even_with_valid_internal_key(ready,client,app,session):
    own,*_=ready
    credential=DeviceCredential(token_hash=hash_actor_token('device-fixture'),actor_id=own.actor_id,expires_at=utcnow()+timedelta(days=1))
    session.add(credential);session.commit()
    own,other,_,cloud,voice,profile=ready
    adjusted=(own,other,{'Authorization':'Bearer device-fixture'},cloud,voice,profile)
    identifier=start(client,app,adjusted).json()['call_id']
    path='/internal/voice-calls/'+identifier+'/authorize'
    assert client.get(path,headers=internal()).status_code==200
    session.delete(credential);session.commit()
    assert client.get(path,headers=internal()).status_code==404
    identifier=start(client,app,ready).json()['call_id']
    session.get(VoiceCall,identifier).expires_at=utcnow()-timedelta(seconds=1);session.commit()
    assert client.get('/internal/voice-calls/'+identifier+'/authorize',headers=internal()).status_code==404


def test_voice_revoke_ends_call_removes_sample_and_retries_remote_deletion(ready,client,app,session):
    own,_,headers,_,voice,profile=ready
    identifier=start(client,app,ready).json()['call_id']
    app.state.realtime_provider.fail_delete=True
    result=client.post('/api/v1/consents/'+voice+'/revoke',headers=headers)
    assert result.status_code==200
    session.expire_all();assert session.get(VoiceCall,identifier).ended_at
    assert profile.status=='delete_pending' and profile.sample_key==profile.reference_text==''
    with pytest.raises(FileNotFoundError): app.state.object_store.get('own/sample')
    app.state.realtime_provider.fail_delete=False
    assert client.post('/internal/realtime/maintenance',headers=internal()).status_code==200
    session.expire_all();assert profile.status=='deleted' and not profile.provider_voice_id


def test_interrupt_bound_to_turn_cannot_cancel_newer_answer(ready,client,app,session):
    identifier=start(client,app,ready).json()['call_id'];row=session.get(VoiceCall,identifier)
    row.active_turn='new';session.commit()
    path='/internal/voice-calls/'+identifier+'/interrupt'
    assert client.post(path,headers=internal(),json={'turn_id':'old'}).status_code==200
    session.expire_all();assert row.active_turn=='new'
    assert client.post(path,headers=internal(),json={'turn_id':'new'}).status_code==200
    session.expire_all();assert row.active_turn==''


def test_only_current_saved_answer_can_stream_and_source_change_stops_midstream(ready,client,app,session):
    own,*_=ready
    identifier=start(client,app,ready).json()['call_id'];row=answer(session,own);bind(session,identifier,row.answer_id)
    path='/internal/voice-calls/'+identifier+'/speech/'+row.answer_id
    assert client.get(path,headers=internal(),params={'turn_id':'old'}).status_code==404
    def invalidate():
        with app.state.database.session() as db:
            db.get(TwinAnswer,row.answer_id).invalidated_at=utcnow();db.commit()
    app.state.realtime_provider.after_chunk=invalidate
    result=client.get(path,headers=internal(),params={'turn_id':'turn'})
    assert result.status_code==200 and result.content==b'\x01\x00'*480
    assert app.state.realtime_provider.operations[-1][1]['text'].startswith('根据现有记录推测，')


def test_unknown_is_text_only(ready,client,app,session):
    own,*_=ready
    identifier=start(client,app,ready).json()['call_id'];row=answer(session,own,'UNKNOWN');bind(session,identifier,row.answer_id)
    assert client.get('/internal/voice-calls/'+identifier+'/speech/'+row.answer_id,headers=internal(),params={'turn_id':'turn'}).status_code==404
    assert not app.state.realtime_provider.operations


def test_real_twin_operation_keeps_original_provenance(ready,client,app,session):
    own,_,headers,*_=ready
    _record(client,app,own.subject_id,own.consent_id,headers)
    class ConversationQuote(QuoteTwin):
        def __init__(self): self.contexts=[]
        def answer(self, question, candidates, **kwargs):
            self.contexts.append(kwargs)
            return super().answer(question,candidates)
    app.state.embedding_encoder=TinyEncoder();app.state.twin_client=ConversationQuote();app.state.settings.ai_backend='http'
    identifier=start(client,app,ready).json()['call_id']
    result=client.post('/internal/voice-calls/'+identifier+'/answers',headers=internal(),json={'question':'喜欢什么？','turn_id':'turn'})
    assert result.status_code==200,result.text
    assert result.json()['response_type']=='ORIGINAL'
    assert result.json()['answer']==result.json()['evidence'][0]['excerpt']
    follow=client.post('/internal/voice-calls/'+identifier+'/answers',headers=internal(),json={'question':'那为什么？','turn_id':'next'})
    assert follow.status_code==200,follow.text
    assert app.state.twin_client.contexts[-1]['conversation_turns'][0]['question']=='喜欢什么？'


def test_signed_sample_fetch_requires_ticket_active_consent_and_expiry(ready,client,app,session):
    own,_,headers,_,voice,profile=ready
    profile.status='enrolling';profile.fetch_digest=hashlib.sha256(b'ticket').hexdigest()
    profile.fetch_expires_at=utcnow()+timedelta(minutes=1);session.commit()
    path='/api/v1/realtime-samples/'+profile.profile_id
    assert client.get(path,params={'ticket':'bad'}).status_code==404
    result=client.get(path,params={'ticket':'ticket'});assert result.content==b'private sample'
    assert result.headers['Cache-Control']=='no-store'
    profile.fetch_expires_at=utcnow()-timedelta(seconds=1);session.commit()
    assert client.get(path,params={'ticket':'ticket'}).status_code==404


def test_real_sample_validation_checks_duration_and_silence():
    def wav(duration,level):
        out=io.BytesIO()
        with wave.open(out,'wb') as w:
            w.setparams((1,2,24000,0,'NONE','not compressed'))
            w.writeframes(b''.join(struct.pack('<h',int(level*math.sin(i*.08))) for i in range(int(duration*24000))))
        return out.getvalue()
    assert validate_sample(wav(5,1000))==5
    for data in [wav(4,1000),wav(6,0),b'bad']:
        with pytest.raises(RealtimeUnavailable):validate_sample(data)


def test_enrollment_uses_dedicated_sample_signed_fetch_and_waits_for_provider_readiness(ready,client,app,session):
    own,_,headers,_,voice,old=ready
    old.revoked_at=utcnow();session.commit()
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'))
        wav.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*.08))) for i in range(6*24000)))
    path=f'/api/v1/subjects/{own.subject_id}/twin/voice/profile'
    data={'voice_consent_id':voice,'transcript':'这是虚构样本','own_voice_confirmed':'false','accepted_policy':policy(app.state.settings)}
    assert client.post(path,headers=headers,data=data,files={'sample':('sample.wav',output.getvalue(),'audio/wav')}).status_code==404
    assert not app.state.realtime_provider.operations
    data['own_voice_confirmed']='true'
    result=client.post(path,headers=headers,data=data,files={'sample':('sample.wav',output.getvalue(),'audio/wav')})
    assert result.status_code==200,result.text
    assert result.json()['status']=='enrolling' and not result.json()['ready']
    action,fields=app.state.realtime_provider.operations[-1]
    assert action=='create_voice' and fields['target_model']==app.state.settings.cosyvoice_model
    parsed=urlsplit(fields['url']);query=parse_qs(parsed.query)
    assert parsed.hostname=='backend.fixture.invalid' and len(query['ticket'][0])>=32
    assert client.get(parsed.path,params=query).content==output.getvalue()
    status=client.get(path,headers=headers)
    assert status.json()['ready'] and status.json()['status']=='ready'
    assert client.get(parsed.path,params=query).status_code==404
    assert 'cosy-fixture' not in status.text


def test_call_hangup_is_owner_scoped_and_immediately_denies_worker(ready,client,app,session,monkeypatch):
    own,other,headers,*_=ready
    async def no_network(*args):pass
    monkeypatch.setattr('app.api.realtime.remove_room',no_network)
    identifier=start(client,app,ready).json()['call_id']
    path=f'/api/v1/subjects/{own.subject_id}/twin/voice/calls/{identifier}'
    assert client.delete(path,headers={'Authorization':'Bearer '+other.actor_token}).status_code==404
    assert client.delete(path,headers=headers).json()['ended']
    assert client.get('/internal/voice-calls/'+identifier+'/authorize',headers=internal()).status_code==404


def test_real_uvicorn_websocket_handshake_enforces_worker_authorization(ready,client,app):
    import asyncio
    import socket
    import threading
    import time
    import aiohttp
    import uvicorn
    identifier=start(client,app,ready).json()['call_id']
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False,lifespan='off'))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:time.sleep(.01)
        assert server.started
        async def probe():
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as http:
                url=f'ws://127.0.0.1:{port}/internal/voice-calls/{identifier}/listen'
                with pytest.raises(aiohttp.WSServerHandshakeError) as denied:
                    await http.ws_connect(url)
                assert denied.value.status==403
                async with http.ws_connect(url,headers=internal()) as ws:
                    # Fixture upstream is deliberately unreachable. Receiving its
                    # controlled error proves a real authorized WS handshake ran.
                    message=await ws.receive_json()
                    assert message['type']=='error' and '授权' in message['message']
        asyncio.run(probe())
    finally:
        server.should_exit=True;thread.join(timeout=5);listener.close()
        assert not thread.is_alive()


def test_continuous_pcm_does_not_query_per_frame_and_revoke_closes_socket(ready,client,app,monkeypatch):
    import asyncio
    import socket
    import threading
    import time
    from types import SimpleNamespace
    import aiohttp
    import uvicorn
    from app import realtime_listen
    checks=[];original=realtime_listen.check_call
    def checked(*args):checks.append(time.monotonic());return original(*args)
    monkeypatch.setattr(realtime_listen,'check_call',checked)
    class Upstream:
        def __init__(self):self.audio=[];self.task_id='';self.closed=False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):self.closed=True
        async def send_json(self,event):self.task_id=event['header']['task_id']
        async def receive_json(self):return {'header':{'event':'task-started','task_id':self.task_id}}
        async def send_bytes(self,data):self.audio.append(data)
        def __aiter__(self):return self
        async def __anext__(self):await asyncio.Event().wait()
    upstream=Upstream()
    class ProviderSession:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def ws_connect(self,*args,**kwargs):return upstream
    monkeypatch.setattr(realtime_listen,'aiohttp',SimpleNamespace(ClientSession=ProviderSession,
        ClientTimeout=aiohttp.ClientTimeout,WSMsgType=aiohttp.WSMsgType,ClientError=aiohttp.ClientError))
    identifier=start(client,app,ready).json()['call_id']
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128);port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False,lifespan='off'))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:time.sleep(.01)
        assert server.started
        async def probe():
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as http:
                async with http.ws_connect(f'ws://127.0.0.1:{port}/internal/voice-calls/{identifier}/listen',headers=internal()) as ws:
                    assert (await ws.receive_json())['type']=='ready'
                    for _ in range(50):await ws.send_bytes(b'\x01\x00'*320)
                    deadline=time.monotonic()+2
                    while len(upstream.audio)<50 and time.monotonic()<deadline:await asyncio.sleep(.01)
                    assert len(upstream.audio)==50 and len(checks)<5
                    result=client.post('/api/v1/consents/'+ready[4]+'/revoke',headers=ready[2]);assert result.status_code==200
                    error=await asyncio.wait_for(ws.receive_json(),2.5)
                    assert error['type']=='error'
        asyncio.run(probe())
    finally:
        server.should_exit=True;thread.join(timeout=5);listener.close()
        assert not thread.is_alive() and upstream.closed

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
import json
from pydantic import ValidationError
from app.config import Settings
from sqlalchemy import select
from app.models import TwinAnswer, DeviceCredential, Consent, utcnow
from app.realtime_models import VoiceCall, RealtimeVoiceProfile
from app.realtime_access import policy, profile_for
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


def test_default_voice_can_call_without_clone_and_stays_out_of_personal_profile(app, client, session, ready):
    own, _, headers, cloud, voice, personal = ready
    personal.revoked_at = utcnow(); personal.status = 'deleted'; session.commit()
    path = f'/api/v1/subjects/{own.subject_id}/twin/voice'
    assert client.get(path+'/capabilities', headers=headers).json()['default_voice_available'] is True
    payload = {'cloud_consent_id':cloud, 'voice_consent_id':voice, 'policy':policy(app.state.settings)}
    assert client.post(path+'/calls', headers=headers, json=payload).status_code == 404
    response = client.post(path+'/calls', headers=headers, json={**payload, 'voice_mode':'default'})
    assert response.status_code == 200 and response.json()['voice_mode'] == 'default'
    row = session.get(VoiceCall, response.json()['call_id'])
    assert row.profile_id.startswith('rvp_default_')
    preset = session.get(RealtimeVoiceProfile, row.profile_id)
    assert preset.sample_key == preset.reference_text == ''
    assert profile_for(session, own.subject_id, own.actor_id) is None
    assert client.get(path+'/profile', headers=headers).json()['status'] == 'missing'
    assert not any(action == 'create_voice' for action, _ in app.state.realtime_provider.operations)
    assert 'longxiaochun' not in response.text
    client.post('/api/v1/consents/'+voice+'/revoke', headers=headers)
    session.expire_all()
    assert preset.status == 'deleted' and preset.provider_voice_id == ''
    assert row.ended_at is not None
    assert not any(action == 'delete_voice' for action, _ in app.state.realtime_provider.operations)


def test_default_voice_still_requires_both_consents(app, client, session, ready):
    own, _, headers, cloud, voice, _ = ready
    path = f'/api/v1/subjects/{own.subject_id}/twin/voice/calls'
    client.post('/api/v1/consents/'+voice+'/revoke', headers=headers)
    response = client.post(path, headers=headers, json={'cloud_consent_id':cloud, 'voice_consent_id':voice,
        'policy':policy(app.state.settings), 'voice_mode':'default'})
    assert response.status_code == 403
    assert not list(session.scalars(select(VoiceCall)))


def test_voice_preview_is_private_wave_without_twin_or_saved_evidence(app, client, session, ready):
    own, other, headers, cloud, voice, profile = ready
    path = f'/api/v1/subjects/{own.subject_id}/twin/voice/profile/preview'
    assert client.get(path).status_code == 401
    assert client.get(path, headers={'Authorization': 'Bearer ' + other.actor_token}).status_code == 404
    client.post('/api/v1/consents/' + cloud + '/revoke', headers=headers)
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    with wave.open(io.BytesIO(response.content)) as audio:
        assert audio.getframerate() == 24000 and audio.getnchannels() == 1
        assert audio.getnframes() == 960
    assert not list(session.scalars(select(VoiceCall)))
    assert not list(session.scalars(select(TwinAnswer)))


def test_voice_preview_withholds_audio_when_voice_revoked_during_generation(app, client, session, ready):
    own, _, headers, _, voice, _ = ready
    def revoke_during_generation():
        grant = session.get(Consent, voice)
        grant.status = 'revoked'; grant.revoked_at = utcnow(); session.commit()
    app.state.realtime_provider.after_chunk = revoke_during_generation
    response = client.get(f'/api/v1/subjects/{own.subject_id}/twin/voice/profile/preview', headers=headers)
    assert response.status_code in (403, 404)
    assert not response.content.startswith(b'RIFF')


def test_voice_preview_does_not_generate_for_pending_or_changed_policy(app, client, session, ready):
    own, _, headers, _, _, profile = ready
    path = f'/api/v1/subjects/{own.subject_id}/twin/voice/profile/preview'
    profile.status = 'enrolling'; session.commit()
    assert client.get(path, headers=headers).status_code == 404
    profile.status = 'ready'; profile.accepted_policy = 'old-policy'; session.commit()
    assert client.get(path, headers=headers).status_code == 404
    assert not app.state.realtime_provider.operations


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
    assert claims['roomConfig']['agents']==[{'agentName':'remember-twin',
        'metadata':json.dumps({'call_id':ticket['call_id']})}]
    assert 'roomAdmin' not in claims['video']
    assert own.actor_token not in result.text and 'cosy-fixture' not in result.text
    assert not client.get('/internal/voice-calls/'+ticket['call_id']+'/authorize',headers=headers).is_success
    assert client.get('/internal/voice-calls/'+ticket['call_id']+'/authorize',headers=internal()).status_code==200
    assert client.post(f'/api/v1/subjects/{other.subject_id}/twin/voice/calls',headers=headers,
        json={'cloud_consent_id':cloud,'voice_consent_id':voice,'policy':policy(app.state.settings)}).status_code==404


def test_configured_agent_dispatch_keeps_room_binding_and_only_call_metadata(ready,client,app,monkeypatch):
    monkeypatch.setenv('REMEMBER_LIVEKIT_AGENT_NAME','remember-twin-us')
    configured=Settings(_env_file=None)
    app.state.settings.livekit_agent_name=configured.livekit_agent_name
    response=start(client,app,ready);assert response.status_code==200,response.text
    ticket=response.json()
    claims=jwt.decode(ticket['token'],app.state.settings.livekit_api_secret.get_secret_value(),algorithms=['HS256'])
    dispatch=claims['roomConfig']['agents']
    assert len(dispatch)==1 and dispatch[0]['agentName']=='remember-twin-us'
    assert json.loads(dispatch[0]['metadata'])=={'call_id':ticket['call_id']}
    assert claims['video']['room']==ticket['room']==ticket['call_id']
    assert claims['sub']==ticket['participant_identity']


@pytest.mark.parametrize('name',['','has space','name/route','中文','a'*65,'name\n'])
def test_invalid_agent_dispatch_configuration_is_rejected(name,monkeypatch):
    monkeypatch.setenv('REMEMBER_LIVEKIT_AGENT_NAME',name)
    with pytest.raises(ValidationError):Settings(_env_file=None)


def test_agent_dispatch_configuration_accepts_ascii_punctuation_and_max_length(monkeypatch):
    monkeypatch.setenv('REMEMBER_LIVEKIT_AGENT_NAME','Agent_0.'+'-'*56)
    assert len(Settings(_env_file=None).livekit_agent_name)==64


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
    assert app.state.realtime_provider.operations[-1][1]['text'] == row.answer


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


def test_new_call_recalls_previous_call_but_keeps_an_independent_answer_chain(ready,client,app,session,monkeypatch):
    from test_chat_memory import RecallTwin,TopicEncoder
    from test_twin_conversation import send
    import app.api.realtime as api
    own,_,headers,cloud,_,_=ready
    twin=RecallTwin();app.state.twin_client=twin
    app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    async def no_room(*args):pass
    monkeypatch.setattr(api,'remove_room',no_room)
    first_call=start(client,app,ready).json()['call_id']
    def speak(call,text,turn):
        response=client.post('/internal/voice-calls/'+call+'/answers',headers=internal(),
            json={'question':text,'turn_id':turn})
        assert response.status_code==200,response.text
        return response.json()
    first=speak(first_call,'我喜欢橙色书签。','voice-old-first')
    second=speak(first_call,'书签是什么颜色？','voice-old-second')
    assert twin.options[-1]['conversation_turns'][0]['answer_id']==first['answer_id']
    assert second['parent_answer_id']==first['answer_id']
    ended=client.delete(f'/api/v1/subjects/{own.subject_id}/twin/voice/calls/{first_call}',headers=headers)
    assert ended.status_code==200
    next_call=start(client,app,ready).json()['call_id']
    restarted=speak(next_call,'继续刚才书签的话题。','voice-restarted')
    assert restarted['parent_answer_id'] is None
    assert restarted['conversation_id']!=first['conversation_id']
    assert twin.options[-1]['conversation_turns']==[]
    recalled={t['answer_id'] for t in twin.options[-1]['conversation_recall']}
    assert {first['answer_id'],second['answer_id']}<=recalled
    assert restarted['recalled_turn_count']>=2
    assert restarted['history_summary_status']=='ready'
    assert twin.options[-1]['conversation_summary']
    ordinary=send(client,own,headers,cloud,'我以前说过喜欢什么颜色的书签？')
    assert ordinary.status_code==200,ordinary.text
    assert first['answer_id'] in {t['answer_id'] for t in twin.options[-1]['conversation_recall']}


def test_new_voice_call_automatically_recalls_an_earlier_text_conversation(ready,client,app,session):
    from test_chat_memory import RecallTwin,TopicEncoder
    from test_twin_conversation import send
    own,_,headers,cloud,_,_=ready
    twin=RecallTwin();app.state.twin_client=twin
    app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    prior=send(client,own,headers,cloud,'我喜欢橙色书签。')
    assert prior.status_code==200,prior.text
    identifier=start(client,app,ready).json()['call_id']
    response=client.post('/internal/voice-calls/'+identifier+'/answers',headers=internal(),
        json={'question':'继续聊刚才的书签。','turn_id':'fresh-voice'})
    assert response.status_code==200,response.text
    assert twin.options[-1]['conversation_turns']==[]
    assert response.json()['parent_answer_id'] is None
    assert prior.json()['answer_id'] in {t['answer_id'] for t in twin.options[-1]['conversation_recall']}
    assert response.json()['recalled_turn_count']==1
    assert response.json()['history_summary_status']=='ready'


def test_greeting_in_new_call_carries_latest_previous_call_tail_despite_old_similar_chats(ready,client,app,session,monkeypatch):
    from test_chat_memory import RecallTwin,TopicEncoder,noisy_history_with_latest_tail
    import app.api.realtime as api
    from app import chat_memory
    own,_,headers,_,_,_=ready
    twin=RecallTwin();app.state.twin_client=twin;app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    async def no_room(*args):pass
    monkeypatch.setattr(api,'remove_room',no_room)
    old_call=start(client,app,ready).json()['call_id']
    old=client.post('/internal/voice-calls/'+old_call+'/answers',headers=internal(),
        json={'question':'书签的安排。','turn_id':'latest-call-first'})
    assert old.status_code==200,old.text
    tail=noisy_history_with_latest_tail(session,session.get(TwinAnswer,old.json()['answer_id']))
    assert client.delete(f'/api/v1/subjects/{own.subject_id}/twin/voice/calls/{old_call}',headers=headers).status_code==200
    flags=[];original=chat_memory.prepare
    def inspect(*args,**kwargs):
        flags.append(kwargs.get('carry_latest_conversation'));return original(*args,**kwargs)
    monkeypatch.setattr(chat_memory,'prepare',inspect)
    new_call=start(client,app,ready).json()['call_id']
    response=client.post('/internal/voice-calls/'+new_call+'/answers',headers=internal(),
        json={'question':'你好','turn_id':'new-greeting'})
    assert response.status_code==200,response.text
    carried={t['answer_id'] for t in twin.options[-1]['conversation_recall']}
    assert set(tail[-6:])<=carried and len(carried)<=12
    assert response.json()['parent_answer_id'] is None
    assert response.json()['conversation_id']!=old.json()['conversation_id']
    assert twin.options[-1]['conversation_turns']==[] and flags[-1] is True
    follow=client.post('/internal/voice-calls/'+new_call+'/answers',headers=internal(),
        json={'question':'那继续吧','turn_id':'new-followup'})
    assert follow.status_code==200,follow.text
    assert follow.json()['parent_answer_id']==response.json()['answer_id']
    assert flags[-1] is False


def test_greeting_in_new_call_carries_latest_text_conversation_as_fallback(ready,client,app,session):
    from test_chat_memory import RecallTwin,TopicEncoder,noisy_history_with_latest_tail
    from test_twin_conversation import send
    own,_,headers,cloud,_,_=ready
    twin=RecallTwin();app.state.twin_client=twin;app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    text=send(client,own,headers,cloud,'书签的计划。');assert text.status_code==200
    tail=noisy_history_with_latest_tail(session,session.get(TwinAnswer,text.json()['answer_id']))
    identifier=start(client,app,ready).json()['call_id']
    response=client.post('/internal/voice-calls/'+identifier+'/answers',headers=internal(),json={'question':'你好','turn_id':'text-fallback'})
    assert response.status_code==200,response.text
    assert set(tail[-6:])<={t['answer_id'] for t in twin.options[-1]['conversation_recall']}
    assert twin.options[-1]['conversation_turns']==[] and response.json()['parent_answer_id'] is None


def test_reused_worker_turn_id_cannot_reuse_an_answer_from_another_call(ready,client,app,session):
    from test_chat_memory import RecallTwin,TopicEncoder
    twin=RecallTwin();app.state.twin_client=twin
    app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    identifiers=[start(client,app,ready).json()['call_id']]
    first=client.post('/internal/voice-calls/'+identifiers[0]+'/answers',headers=internal(),
        json={'question':'你好。','turn_id':'reused-worker-turn'})
    assert first.status_code==200,first.text
    identifiers.append(start(client,app,ready).json()['call_id'])
    second=client.post('/internal/voice-calls/'+identifiers[1]+'/answers',headers=internal(),
        json={'question':'你好。','turn_id':'reused-worker-turn'})
    assert second.status_code==200,second.text
    assert second.json()['answer_id']!=first.json()['answer_id']
    assert second.json()['parent_answer_id'] is None
    assert len(twin.options)==2


def test_voice_recalls_older_than_twenty_current_turns_and_prior_calls_and_text(ready,client,app,session):
    from test_chat_memory import RecallTwin,TopicEncoder
    from test_twin_conversation import send
    own,_,headers,cloud,_,_=ready
    twin=RecallTwin();app.state.twin_client=twin
    app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    old_call=start(client,app,ready).json()['call_id']
    def speak(call,question,turn):
        r=client.post('/internal/voice-calls/'+call+'/answers',headers=internal(),
            json={'question':question,'turn_id':turn})
        assert r.status_code==200,r.text
        return r.json()
    previous=speak(old_call,'我喜欢橙色书签。','another-call')
    text=send(client,own,headers,cloud,'文字里我也提到了橙色书签。')
    assert text.status_code==200,text.text
    current_call=start(client,app,ready).json()['call_id']
    first=speak(current_call,'这一通电话我提到蓝色书签。','current-first')
    original=session.get(TwinAnswer,first['answer_id'])
    values={c.name:getattr(original,c.name) for c in original.__table__.columns}
    parent=original.answer_id
    for n in range(24):
        row=dict(values,answer_id=f'same_call_old_{n}',question=f'讨论散步路线{n}',
            parent_answer_id=parent,request_id=f'same-call-fixture-{n}',
            created_at=original.created_at+timedelta(microseconds=n+1))
        session.add(TwinAnswer(**row));parent=row['answer_id']
    session.get(VoiceCall,current_call).previous_answer_id=parent;session.commit()
    result=speak(current_call,'我前面提到什么颜色的书签？','current-followup')
    selected={t['answer_id'] for t in twin.options[-1].get('conversation_recall',[])}
    assert {first['answer_id'],previous['answer_id'],text.json()['answer_id']}<=selected
    assert result['recalled_turn_count']>0 and result['context_truncated']
    assert result['parent_answer_id']==parent
    assert len(twin.options[-1]['conversation_turns'])==20
    assert first['answer_id'] not in {t['answer_id'] for t in twin.options[-1]['conversation_turns']}
    assert len(selected)<=12


@pytest.mark.parametrize('action',['disable','clear'])
def test_voice_history_honors_chat_memory_switch_and_clear(ready,client,app,session,action):
    from test_chat_memory import RecallTwin,TopicEncoder
    from test_twin_conversation import send
    from app.models import ChatTurnEmbedding,ChatDigest
    own,_,headers,cloud,_,_=ready
    twin=RecallTwin();app.state.twin_client=twin
    app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    text=send(client,own,headers,cloud,'旧文字提到橙色书签。').json()
    first_call=start(client,app,ready).json()['call_id']
    spoken=client.post('/internal/voice-calls/'+first_call+'/answers',headers=internal(),
        json={'question':'上一通电话提到蓝色书签。','turn_id':'old-voice'})
    assert spoken.status_code==200,spoken.text
    path=f'/api/v1/subjects/{own.subject_id}/twin/chat-memory'
    update=(client.put(path,headers=headers,json={'enabled':False}) if action=='disable'
            else client.delete(path,headers=headers))
    assert update.status_code==200,update.text
    next_call=start(client,app,ready).json()['call_id']
    response=client.post('/internal/voice-calls/'+next_call+'/answers',headers=internal(),
        json={'question':'你好','turn_id':'after-setting'})
    assert response.status_code==200,response.text
    assert not twin.options[-1].get('conversation_recall')
    assert not twin.options[-1].get('conversation_summary')
    assert twin.options[-1]['conversation_turns']==[]
    assert response.json()['parent_answer_id'] is None and response.json()['recalled_turn_count']==0
    session.expire_all()
    assert session.scalar(select(ChatTurnEmbedding).where(ChatTurnEmbedding.subject_id==own.subject_id)) is None
    assert session.scalar(select(ChatDigest).where(ChatDigest.subject_id==own.subject_id)) is None
    # Original chats remain saved, but a clear cannot silently reindex them.
    assert session.get(TwinAnswer,text['answer_id']) is not None
    assert session.get(TwinAnswer,spoken.json()['answer_id']) is not None


def test_voice_recall_excludes_another_actor_or_subject_even_with_matching_topics(ready,client,app,session):
    from test_chat_memory import RecallTwin,TopicEncoder
    from test_twin_conversation import send
    from app.models import ChatTurnEmbedding,MemoryItem,PersonTrait,Episode
    own,other,headers,cloud,_,_=ready
    twin=RecallTwin();app.state.twin_client=twin
    app.state.embedding_encoder=TopicEncoder();app.state.settings.ai_backend='http'
    original=send(client,own,headers,cloud,'本人的文字提到橙色书签。').json()
    row=session.get(TwinAnswer,original['answer_id'])
    values={c.name:getattr(row,c.name) for c in TwinAnswer.__table__.columns}
    foreign_ids=set()
    for n,(subject,actor) in enumerate([(own.subject_id,other.actor_id),
            (other.subject_id,own.actor_id),(other.subject_id,other.actor_id)]):
        identifier=f'foreign_history_{n}';foreign_ids.add(identifier)
        session.add(TwinAnswer(**dict(values,answer_id=identifier,subject_id=subject,actor_id=actor,
            question=f'他人的秘密书签{n}',answer='不能当成本人的人格。',request_id=None)))
    session.commit()
    identifier=start(client,app,ready).json()['call_id']
    response=client.post('/internal/voice-calls/'+identifier+'/answers',headers=internal(),
        json={'question':'以前的书签聊了什么？','turn_id':'own-recall'})
    assert response.status_code==200,response.text
    selected={t['answer_id'] for t in twin.options[-1]['conversation_recall']}
    assert selected=={original['answer_id']}
    assert not foreign_ids.intersection(response.json()['recalled_answer_ids'])
    assert '他人的秘密' not in str(twin.options[-1])
    assert not set(session.scalars(select(ChatTurnEmbedding.answer_id))).intersection(foreign_ids)
    assert session.scalar(select(MemoryItem).join(Episode).where(Episode.subject_id==own.subject_id)) is None
    assert session.scalar(select(PersonTrait).where(PersonTrait.subject_id==own.subject_id)) is None


@pytest.mark.parametrize('action',['hangup','new_turn'])
@pytest.mark.parametrize('phase',['summary','answer'])
def test_answer_finishing_after_call_change_is_not_saved_or_recalled(ready,client,app,session,action,phase):
    from test_chat_memory import RecallTwin,TopicEncoder
    from test_twin_conversation import send
    from app.models import ChatDigest
    own,_,headers,cloud,_,_=ready
    app.state.twin_client=RecallTwin();app.state.embedding_encoder=TopicEncoder()
    app.state.settings.ai_backend='http'
    prior=send(client,own,headers,cloud,'之前的文字提到橙色书签。')
    assert prior.status_code==200,prior.text
    identifier=start(client,app,ready).json()['call_id']
    class LateTwin(RecallTwin):
        def change_call(self):
            with app.state.database.session() as guard:
                call=guard.get(VoiceCall,identifier)
                if action=='hangup':call.ended_at=utcnow()
                else:call.active_turn='newer-turn'
                guard.commit()
        def summarize_chat(self,*args,**kwargs):
            result=super().summarize_chat(*args,**kwargs)
            if phase=='summary':self.change_call()
            return result
        def answer(self,*args,**kwargs):
            result=super().answer(*args,**kwargs)
            if phase=='answer':self.change_call()
            return result
    app.state.twin_client=LateTwin();app.state.embedding_encoder=TopicEncoder()
    app.state.settings.ai_backend='http'
    question='这个晚到的书签语音回答不能保存。'
    response=client.post('/internal/voice-calls/'+identifier+'/answers',headers=internal(),
        json={'question':question,'turn_id':'superseded-turn'})
    assert response.status_code==404,response.text
    session.expire_all()
    assert session.scalar(select(TwinAnswer).where(TwinAnswer.subject_id==own.subject_id,TwinAnswer.question==question)) is None
    row=session.get(VoiceCall,identifier)
    assert row.previous_answer_id==''
    if action=='new_turn':assert row.active_turn=='newer-turn'
    if phase=='summary':
        assert session.scalar(select(ChatDigest).where(ChatDigest.subject_id==own.subject_id)) is None


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


def test_hangup_deadline_cancels_remote_cleanup_and_denies_worker_while_pending(ready,client,app,session,monkeypatch):
    import asyncio
    import httpx
    from app.api import realtime
    own,_,headers,*_=ready
    identifier=start(client,app,ready).json()['call_id']
    path=f'/api/v1/subjects/{own.subject_id}/twin/voice/calls/{identifier}'
    monkeypatch.setattr(realtime,'_ROOM_DELETE_TIMEOUT_SECONDS',.25)
    async def probe():
        started=asyncio.Event();cancelled=asyncio.Event()
        async def stalled_cleanup(_app,room):
            assert room==identifier
            started.set()
            try: await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set();raise
        monkeypatch.setattr(realtime,'remove_room',stalled_cleanup)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as http:
            ending=asyncio.create_task(http.delete(path,headers=headers))
            try:
                await asyncio.wait_for(started.wait(),1)
                denied=await http.get('/internal/voice-calls/'+identifier+'/authorize',headers=internal())
                assert denied.status_code==404
                assert not ending.done()  # Durable end applies before remote cleanup completes.
                response=await asyncio.wait_for(ending,1)
                assert response.status_code==200 and response.json()=={'ended':True}
                assert cancelled.is_set()
            finally:
                ending.cancel();await asyncio.gather(ending,return_exceptions=True)
    asyncio.run(probe())
    session.expire_all()
    assert session.get(VoiceCall,identifier).ended_at is not None


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
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False,lifespan='off',ws='wsproto',ws_ping_interval=0))
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
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False,lifespan='off',ws='wsproto',ws_ping_interval=0))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:time.sleep(.01)
        assert server.started
        async def probe():
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as http:
                async with http.ws_connect(f'ws://127.0.0.1:{port}/internal/voice-calls/{identifier}/listen',headers=internal(),compress=15) as ws:
                    assert (await ws.receive_json())['type']=='ready'
                    assert ws.compress==15
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


def test_partial_recognition_does_not_delay_final_or_repeat_database_guards(ready,client,app,monkeypatch):
    import asyncio,json
    from types import SimpleNamespace
    import aiohttp
    from app import realtime_listen
    identifier=start(client,app,ready).json()['call_id'];checks=[];original=realtime_listen.check_call
    def checked(*args):checks.append(1);return original(*args)
    monkeypatch.setattr(realtime_listen,'check_call',checked)
    class Upstream:
        def __init__(self):self.task_id='';self.index=0
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def send_json(self,event):self.task_id=event['header']['task_id']
        async def receive_json(self):return {'header':{'event':'task-started','task_id':self.task_id}}
        def __aiter__(self):return self
        async def __anext__(self):
            if self.index>50:raise StopAsyncIteration
            self.index+=1
            value={'header':{'event':'result-generated','task_id':self.task_id},
                'payload':{'output':{'sentence':{'text':'synthetic question','sentence_end':self.index==51,'begin_time':0}}}}
            return SimpleNamespace(type=aiohttp.WSMsgType.TEXT,data=json.dumps(value))
    upstream=Upstream()
    class ProviderSession:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def ws_connect(self,*args,**kwargs):return upstream
    monkeypatch.setattr(realtime_listen,'aiohttp',SimpleNamespace(ClientSession=ProviderSession,
        ClientTimeout=aiohttp.ClientTimeout,WSMsgType=aiohttp.WSMsgType,ClientError=aiohttp.ClientError))
    class Socket:
        headers=internal()
        def __init__(self):self.app=app;self.sent=[]
        async def accept(self):pass
        async def send_json(self,data):self.sent.append(data)
        async def iter_bytes(self):
            await asyncio.Event().wait()
            if False:yield b''
        async def close(self,**kwargs):pass
    ws=Socket();asyncio.run(realtime_listen.proxy_listen(ws,identifier))
    assert [event['type'] for event in ws.sent]==['ready','final']
    assert len(checks)==2  # Initial access and final text; live watchdog is separate.


def test_disconnected_websocket_cleanup_does_not_raise_again(ready,client,app,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    import aiohttp
    from fastapi import WebSocketDisconnect
    from app import realtime_listen
    identifier=start(client,app,ready).json()['call_id']
    class Upstream:
        def __init__(self):self.task_id='';self.closed=False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):self.closed=True
        async def send_json(self,event):self.task_id=event['header']['task_id']
        async def receive_json(self):return {'header':{'event':'task-started','task_id':self.task_id}}
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
    class Socket:
        headers=internal()
        def __init__(self):self.app=app;self.close_attempted=False;self.sent=[]
        async def accept(self):pass
        async def send_json(self,data):
            self.sent.append(data)
            if data['type']=='error':raise WebSocketDisconnect(code=1006)
        async def iter_bytes(self):
            raise WebSocketDisconnect(code=1006)
            if False:yield b''
        async def close(self,**kwargs):
            self.close_attempted=True;raise WebSocketDisconnect(code=1006)
    ws=Socket();asyncio.run(realtime_listen.proxy_listen(ws,identifier))
    assert ws.close_attempted and upstream.closed
    assert [event['type'] for event in ws.sent]==['ready','error']


def test_segment_diagnostics_show_receive_send_and_final_without_private_content(ready,client,app,monkeypatch,caplog):
    import asyncio,logging
    from types import SimpleNamespace
    import aiohttp
    from app import realtime_listen
    from app.logging_config import JsonFormatter
    identifier=start(client,app,ready).json()['call_id'];sent=asyncio.Event()
    monkeypatch.setenv('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS','1')
    caplog.set_level(logging.INFO,logger='app.realtime_listen')
    class Upstream:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def send_json(self,event):self.task_id=event['header']['task_id']
        async def receive_json(self):return {'header':{'event':'task-started','task_id':self.task_id}}
        async def send_bytes(self,data):sent.set()
        def __aiter__(self):return self.messages()
        async def messages(self):
            await sent.wait()
            yield SimpleNamespace(type=aiohttp.WSMsgType.TEXT,data=json.dumps({
                'header':{'event':'result-generated','task_id':self.task_id},
                'payload':{'output':{'sentence':{'text':'private synthetic speech','sentence_end':True,'begin_time':69000,'end_time':72000}}}}))
    class ProviderSession:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def ws_connect(self,*args,**kwargs):return Upstream()
    monkeypatch.setattr(realtime_listen,'aiohttp',SimpleNamespace(ClientSession=ProviderSession,
        ClientTimeout=aiohttp.ClientTimeout,WSMsgType=aiohttp.WSMsgType,ClientError=aiohttp.ClientError))
    class Socket:
        headers=internal()
        def __init__(self):self.app=app
        async def accept(self):pass
        async def send_json(self,data):pass
        async def iter_bytes(self):
            yield (300).to_bytes(2,'little',signed=True)*1600
            await asyncio.Event().wait()
        async def close(self,**kwargs):pass
    asyncio.run(realtime_listen.proxy_listen(Socket(),identifier))
    records=[r for r in caplog.records if r.name=='app.realtime_listen']
    stages=[r.extra_fields['stage'] for r in records]
    assert 'backend_receive.start' in stages and 'provider_send.start' in stages and 'provider_final' in stages
    formatted='\n'.join(JsonFormatter().format(r) for r in records)
    assert '69000' in formatted and 'private synthetic speech' not in formatted and identifier not in formatted
    assert 'Bearer' not in formatted

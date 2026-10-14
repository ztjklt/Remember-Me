import io,math,struct,wave
from sqlalchemy import select,func
from app.models import Episode,MemoryItem,PersonTrait,utcnow
from app.dialogue_models import DialogueSample
from app.realtime_models import RealtimeVoiceProfile
from app.dialogue_capture import run_one
from app.stt import Transcript
from app import speaker_identification
from app.api import realtime
from test_realtime_voice import ready

def setup(app,client,session,ready,monkeypatch):
    own,other,h,cloud,voice,personal=ready
    personal.revoked_at=utcnow();personal.status='deleted';session.commit()
    speaker=client.post('/api/v1/consents',headers=h,json={'subject_id':own.subject_id,'scope':'SPEAKER_IDENTIFICATION'}).json()['consent_id']
    caps=client.get(f'/api/v1/subjects/{own.subject_id}/twin/voice/capabilities',headers=h).json()
    response=client.post(f'/api/v1/subjects/{own.subject_id}/twin/voice/calls',headers=h,json={'cloud_consent_id':cloud,'voice_consent_id':voice,'recording_consent_id':own.consent_id,'speaker_consent_id':speaker,'policy':caps['policy'],'voice_mode':'default'})
    assert response.status_code==200,response.text
    monkeypatch.setattr(speaker_identification,'available',lambda _:True)
    # Natural preparation now requires an independently enrolled acoustic owner
    # reference. This fixture represents that reference, not a typed identity.
    from app import voiceprints
    class AcousticOwner:
        version='fixture-acoustic-v1'
        def extract(self,data):return [1.,0.]
    app.state.speaker_encoder=AcousticOwner()
    voiceprints.enroll(session,own.subject_id,own.actor_id,speaker,[1,0],AcousticOwner.version,{'kind':'fixture','id':'registered-owner'},role='subject',label='Voice own',person_key='subject')
    session.commit()
    return own,h,speaker,response.json()['call_id'],{'Authorization':'Bearer '+'x'*32}

def audio():
    f=io.BytesIO()
    with wave.open(f,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        w.writeframes(b''.join(struct.pack('<h',int(math.sin(n/16000*440*2*math.pi)*10000)) for n in range(96000)))
    return f.getvalue()

class STT:
    def __init__(self,mixed=False,callback=None):self.mixed=mixed;self.callback=callback
    def transcribe_authorized(self,data,kind,authorize,*,diarization):
        assert diarization;authorize()
        if self.callback:self.callback()
        authorize()
        rows=[{'speaker_id':0,'text':'那年春天，我和朋友在学校种了一棵树。','begin_time':0,'end_time':3000}]
        if self.mixed:rows.append({'speaker_id':1,'text':'我也记得那棵树。','begin_time':3500,'end_time':5500})
        return Transcript('那年春天，我和朋友在学校种了一棵树。','fixture','fixture',{'speaker_sentences':rows})

def upload(client,call,h):
    r=client.post('/internal/voice-calls/'+call+'/samples',headers=h,data={'turn_id':'fixture-turn'},files={'sample':('sample.wav',audio(),'audio/wav')})
    assert r.status_code==200,r.text
    return r

def test_natural_dialogue_saves_only_raw_user_material_pending_without_blocking_answer(app,client,session,ready,monkeypatch):
    own,h,speaker,call,worker=setup(app,client,session,ready,monkeypatch)
    monkeypatch.setattr(realtime,'answer_question',lambda *a,**kw:{'answer_id':'fixture-answer','answer':'这是AI回答，不可成为本人证据。'})
    for _ in range(2):
        r=client.post('/internal/voice-calls/'+call+'/answers',headers=worker,json={'turn_id':'t1','question':'我小时候经常和朋友在河边玩。'})
        assert r.status_code==200,r.text
    session.expire_all();episodes=list(session.scalars(select(Episode).where(Episode.subject_id==own.subject_id)))
    assert len(episodes)==1 and episodes[0].transcript=='我小时候经常和朋友在河边玩。'
    assert episodes[0].transcript_reviewed_at is None and episodes[0].capture_metadata['call_id']==call
    note=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==episodes[0].episode_id))
    assert note.review_state=='pending' and 'AI回答' not in note.content
    assert session.scalar(select(func.count()).select_from(PersonTrait))==0
    client.post('/api/v1/consents/'+speaker+'/revoke',headers=h)
    r=client.post('/internal/voice-calls/'+call+'/answers',headers=worker,json={'turn_id':'t2','question':'我们继续聊吧。'})
    assert r.status_code==200
    session.expire_all();assert session.scalar(select(func.count()).select_from(Episode))==1

def test_microphone_only_sample_is_private_idempotent_and_prepares_profile_in_background(app,client,session,ready,monkeypatch):
    own,h,speaker,call,worker=setup(app,client,session,ready,monkeypatch)
    assert upload(client,call,worker).json()['status']=='uploaded'
    assert upload(client,call,worker).json()['status']=='uploaded'
    assert client.post('/internal/voice-calls/'+call+'/samples',data={'turn_id':'bad'},files={'sample':('x.wav',audio(),'audio/wav')}).status_code==404
    assert run_one(app,STT())
    session.expire_all();row=session.scalar(select(DialogueSample));assert row.status=='prepared' and row.audio_key==''
    profile=session.get(RealtimeVoiceProfile,row.profile_id);assert profile.reference_text.startswith('那年春天') and profile.sample_key
    assert client.get(f'/api/v1/subjects/{own.subject_id}/twin/voice/profile',headers=h).json()['ready']
    client.post('/api/v1/consents/'+speaker+'/revoke',headers=h)
    session.expire_all();assert row.status=='deleted' and profile.revoked_at
    assert client.get(f'/api/v1/subjects/{own.subject_id}/twin/voice/profile',headers=h).json()['ready'] is False

def test_mixed_sample_never_creates_a_personal_voice(app,client,session,ready,monkeypatch):
    own,h,speaker,call,worker=setup(app,client,session,ready,monkeypatch);upload(client,call,worker)
    assert run_one(app,STT(mixed=True))
    session.expire_all();row=session.scalar(select(DialogueSample));assert row.status=='skipped' and row.audio_key==''
    assert not any(op=='create_voice' for op,_ in app.state.realtime_provider.operations)

def test_revocation_during_sample_recognition_cannot_create_a_voice(app,client,session,ready,monkeypatch):
    own,h,speaker,call,worker=setup(app,client,session,ready,monkeypatch);upload(client,call,worker)
    assert run_one(app,STT(callback=lambda:client.post('/api/v1/consents/'+speaker+'/revoke',headers=h)))
    session.expire_all();row=session.scalar(select(DialogueSample));assert row.status=='deleted' and row.audio_key==''
    assert not any(op=='create_voice' for op,_ in app.state.realtime_provider.operations)


def test_dialogue_review_is_optional_private_and_deletion_clears_raw_and_derived_text(app,client,session,ready,monkeypatch):
    own,h,speaker,call,worker=setup(app,client,session,ready,monkeypatch)
    monkeypatch.setattr(realtime,'answer_question',lambda *a,**kw:{'answer_id':'fixture-answer','answer':'不能把AI回答当原话'})
    client.post('/internal/voice-calls/'+call+'/answers',headers=worker,json={'turn_id':'t1','question':'我小时候在家乡的河边玩。'})
    path=f'/api/v1/subjects/{own.subject_id}/dialogue-materials'
    rows=client.get(path,headers=h).json()['items'];assert len(rows)==1 and rows[0]['status']=='pending'
    episode=rows[0]['episode_id'];route=path+'/'+episode
    from app.voiceprint_models import VoiceUtterance,VoiceIdentity
    identifier='review-proof'
    session.add(VoiceUtterance(utterance_id=identifier,call_id=call,turn_id='t1',audio_key='',checksum='fixture',status='ready',report={'voiceprint_model_version':'fixture-acoustic-v1','speakers':[{'voice_identity_id':session.scalar(select(VoiceIdentity)).identity_id,'is_subject':True,'voiceprint_status':'matched'}]}))
    original=session.get(Episode,episode)
    original.capture_metadata={**original.capture_metadata,'speaker_verification':'matched','voice_identity_id':session.scalar(select(VoiceIdentity)).identity_id,'voice_utterance_id':identifier}
    session.commit()
    r=client.post(route+'/confirm',headers=h,json={'text':'我小时候在家乡的河边散步。'});assert r.status_code==200,r.text
    assert r.json()['status']=='confirmed'
    session.expire_all();original=session.get(Episode,episode);assert original.stt_transcript=='我小时候在家乡的河边玩。'
    assert any(m.review_state=='active' for m in session.scalars(select(MemoryItem).where(MemoryItem.episode_id==episode)))
    r=client.delete(route,headers=h);assert r.status_code==200,r.text
    assert client.get(path,headers=h).json()['items']==[]
    session.expire_all();assert original.transcript=='' and original.stt_transcript is None
    assert all(m.content=='' and m.deleted_at for m in session.scalars(select(MemoryItem).where(MemoryItem.episode_id==episode)))
    assert client.post(route+'/confirm',headers=h,json={}).status_code==404

def test_source_revocation_after_clone_submit_disables_late_remote_voice(app,client,session,ready,monkeypatch):
    own,h,speaker,call,worker=setup(app,client,session,ready,monkeypatch);upload(client,call,worker)
    original=app.state.realtime_provider.operation
    def operation(action,**fields):
        result=original(action,**fields)
        if action=='create_voice':client.post('/api/v1/consents/'+speaker+'/revoke',headers=h)
        return result
    app.state.realtime_provider.operation=operation
    assert run_one(app,STT())
    session.expire_all()
    assert any(op=='delete_voice' for op,_ in app.state.realtime_provider.operations)
    assert all(p.revoked_at for p in session.scalars(select(RealtimeVoiceProfile).where(~RealtimeVoiceProfile.profile_id.startswith('rvp_default_'))))

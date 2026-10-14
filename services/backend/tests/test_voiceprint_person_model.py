import copy,io,wave
from sqlalchemy import select,func
from app.models import Episode,MemoryItem,Evidence,PersonTrait,ModelRevision,utcnow
from app.voiceprint_models import VoiceIdentity,VoiceUtterance
from app import voiceprints as vp
from app.voice_utterances import run_one
from app.model_coverage import coverage
from app.materials import effective_materials
from app.stt import Transcript
from app.api import realtime
from test_realtime_voice import ready
from test_dialogue_capture import setup,audio,STT

class Encoder:
    version='fixture-acoustic-v1'
    def extract(self,data):return [1.,0.]

def reference(app,session,own,speaker):
    app.state.speaker_encoder=Encoder()
    row=vp.enroll(session,own.subject_id,own.actor_id,speaker,[1,0],Encoder.version,{'kind':'fixture','id':'own'},role='subject',label='小王',person_key='subject')
    session.commit();return row

def test_match_is_subject_scoped_versioned_ambiguous_and_revocable(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch);r=reference(app,session,own,grant)
    assert vp.match(session,own.subject_id,[1,0],Encoder.version).role=='subject'
    assert vp.match(session,'different-subject',[1,0],Encoder.version) is None
    assert vp.match(session,own.subject_id,[1,0],'old-model') is None
    assert vp.match(session,own.subject_id,[0,1],Encoder.version) is None
    vp.enroll(session,own.subject_id,own.actor_id,grant,[.99,.05],Encoder.version,{'kind':'fixture','id':'other'},role='contact',label='小李',person_key='contact:li');session.commit()
    assert vp.match(session,own.subject_id,[1,0],Encoder.version) is None
    r.revoked_at=utcnow();session.commit();assert all(x.role!='subject' for x in vp.active(session,own.subject_id,Encoder.version))

def upload_utterance(client,call,worker,turn='own-turn'):
    result=client.post('/internal/voice-calls/'+call+'/utterances',headers=worker,data={'turn_id':turn},files={'sample':('u.wav',audio(),'audio/wav')})
    assert result.status_code==200,result.text
    return result

def test_owner_matched_dialogue_automatically_enqueues_extract_and_is_private(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch);r=reference(app,session,own,grant)
    upload_utterance(client,call,worker);assert run_one(app,STT())
    session.expire_all();ep=session.scalar(select(Episode).where(Episode.subject_id==own.subject_id))
    assert ep.capture_metadata['voice_identity_id']==r.identity_id and ep.capture_metadata['speaker_verification']=='matched'
    assert ep.status=='extracting' and ep.transcript.startswith('那年春天')
    from app.repositories.jobs import JobRepository
    assert JobRepository(session).for_episode(ep.episode_id).stage=='extract'
    assert client.get('/api/v1/subjects/'+own.subject_id+'/voice-identities',headers=h).json()['items'][0]['role']=='subject'
    assert 'vectors' not in client.get('/api/v1/subjects/'+own.subject_id+'/voice-identities',headers=h).text
    client.delete('/api/v1/subjects/'+own.subject_id+'/voice-identities/'+r.identity_id,headers=h)
    session.expire_all();assert ep.capture_metadata['speaker_verification']=='revoked' and r.vectors==[]

def test_unknown_audio_does_not_become_subject_memory_but_answer_continues(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch);session.query(VoiceIdentity).delete();session.commit();app.state.speaker_encoder=Encoder()
    monkeypatch.setattr(realtime,'answer_question',lambda *a,**kw:{'answer_id':'fixture-answer','answer':'继续正常交流。'})
    response=client.post('/internal/voice-calls/'+call+'/answers',headers=worker,json={'turn_id':'own-turn','question':'我是小王。'})
    assert response.status_code==200
    upload_utterance(client,call,worker);assert run_one(app,STT())
    session.expire_all();eps=list(session.scalars(select(Episode)))
    assert len(eps)==1 and eps[0].capture_metadata['speaker_verification']=='unverified'
    notes=list(session.scalars(select(MemoryItem)));assert notes[0].source_type=='THIRD_PARTY' and notes[0].review_state=='pending'
    assert client.post('/api/v1/subjects/'+own.subject_id+'/dialogue-materials/'+eps[0].episode_id+'/confirm',headers=h,json={}).status_code==422

class MixedEncoder(Encoder):
    def extract(self,data):return [1,0] if len(data)==96000 else [0,1]
class TwoVoices:
    def transcribe_authorized(self,data,kind,authorize,diarization):
        authorize();return Transcript('本人回忆。亲友发言。','fixture','fixture',{'speaker_sentences':[
            {'speaker_id':0,'text':'本人回忆。','begin_time':0,'end_time':3000},
            {'speaker_id':1,'text':'亲友发言。','begin_time':3000,'end_time':5500}]})

def test_multi_person_turn_keeps_only_acoustically_matched_owner_span(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch);reference(app,session,own,grant);app.state.speaker_encoder=MixedEncoder()
    upload_utterance(client,call,worker);assert run_one(app,TwoVoices())
    session.expire_all();ep=session.scalar(select(Episode));assert ep.transcript=='本人回忆。' and '亲友' not in ep.transcript

def test_enrollment_is_explicit_initial_and_name_claim_cannot_overwrite_reference(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch);session.query(VoiceIdentity).delete();session.commit();app.state.speaker_encoder=Encoder()
    from app.realtime_models import VoiceCall
    row=session.get(VoiceCall,call);row.enroll_owner_voice=True;session.commit()
    class Introduction:
        def transcribe_authorized(self,*args,**kwargs):
            return Transcript('你好，我叫小王，这是我自己的声音。','fixture','fixture',{'speaker_sentences':[{'speaker_id':0,'text':'你好，我叫小王，这是我自己的声音。','begin_time':0,'end_time':5500}]})
    upload_utterance(client,call,worker);assert run_one(app,Introduction())
    session.expire_all();assert session.scalar(select(VoiceIdentity)).role=='subject'
    assert session.scalar(select(func.count()).select_from(Episode))==0 # bootstrap is not an independent voice match
    vectors=copy.deepcopy(session.scalar(select(VoiceIdentity)).vectors)
    app.state.speaker_encoder=type('Other',(Encoder,),{'extract':lambda _,data:[0,1]})()
    upload_utterance(client,call,worker,'claimed-again');assert run_one(app,Introduction())
    session.expire_all();assert session.scalar(select(VoiceIdentity)).vectors==vectors
    assert session.scalar(select(func.count()).select_from(Episode))==0

def test_coverage_recomputed_from_distinct_valid_sources_and_never_100(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch)
    from app.models import PERSON_DOMAINS
    # Five genuinely different sources per domain; 2 copied transcripts do not
    # count as 2 independent inputs even if they have different Episode IDs.
    for domain in PERSON_DOMAINS:
        for i in range(6):
            n=domain+str(i);ep=Episode(episode_id=n,subject_id=own.subject_id,actor_id=own.actor_id,recording_consent_id=own.consent_id,idempotency_key=n,source='IOS_TEXT',recorded_at=utcnow(),audio_size_bytes=0,audio_content_type='text/plain',status='ready',trace_id=n,transcript=domain+str(min(i,4)),created_at=utcnow(),updated_at=utcnow());session.add(ep);session.flush()
            ev=Evidence(evidence_id='e'+n,episode_id=n,source_type='SUBJECT',source_ref='fixture',excerpt=ep.transcript);session.add(ev)
            m=MemoryItem(memory_item_id='m'+n,episode_id=n,ordinal=0,memory_type='EVENT',content=ep.transcript,source_type='SUBJECT',evidence_ids=['e'+n],confidence=.9,model_version='v',prompt_version='p',schema_version='0.2.0',review_state='active');session.add(m)
            session.add(PersonTrait(trait_id='t'+n,subject_id=own.subject_id,domain=domain,statement=ep.transcript,confidence=.9,source_type='SUBJECT',evidence_ids=['e'+n],counter_evidence_ids=[],memory_item_ids=['m'+n],status='active',model_version='v'))
    session.commit();result=coverage(session,own.subject_id);assert result['percentage']==95 and all(d['source_count']==5 for d in result['domains'])
    for m in session.scalars(select(MemoryItem)):m.deleted_at=utcnow()
    session.commit();assert coverage(session,own.subject_id)['percentage']==0

def test_verified_dialogue_completes_existing_memory_worker_and_retrieval(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch)
    reference(app,session,own,grant);upload_utterance(client,call,worker);assert run_one(app,STT())
    from app.worker import ProcessingWorker
    w=ProcessingWorker(app.state.database,app.state.object_store,app.state.stt_provider,app.state.ai_client,backoff_seconds=0)
    w.run_once();w.run_once();session.expire_all()
    ep=session.scalar(select(Episode));assert ep.status=='ready',ep.error_message
    assert session.scalar(select(func.count()).select_from(PersonTrait))>0
    assert effective_materials(session,own.subject_id,{ep.episode_id})
    assert coverage(session,own.subject_id)['percentage']>0

def test_active_answer_defers_model_publication_without_spending_retry_budget(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch)
    reference(app,session,own,grant);upload_utterance(client,call,worker);assert run_one(app,STT())
    from app.worker import ProcessingWorker
    from app.realtime_models import VoiceCall
    from app.repositories.jobs import JobRepository
    w=ProcessingWorker(app.state.database,app.state.object_store,app.state.stt_provider,app.state.ai_client,backoff_seconds=0)
    w.run_once();session.expire_all();ep=session.scalar(select(Episode));row=session.get(VoiceCall,call);row.active_turn='speaking';session.commit()
    w.run_once();session.expire_all();job=JobRepository(session).for_episode(ep.episode_id)
    assert job.state=='queued' and job.attempts==0 and ep.status=='modeling'
    assert session.scalar(select(func.count()).select_from(PersonTrait))==0
    row.completed_turn_id='speaking';job.available_at=utcnow();session.commit();w.run_once();session.expire_all();assert ep.status=='ready'

def test_normal_multi_voice_recording_does_not_turn_guest_words_into_subject_facts():
    from types import SimpleNamespace as S
    own='我喜欢散步。';guest='小李喜欢唱歌。'
    ep=S(transcript=own+guest,capture_metadata={'speaker_report':{'speakers':[{'is_subject':True,'voiceprint_status':'matched'},{'is_subject':False,'voiceprint_status':'matched'}],'segments':[{'text':own,'is_subject':True,'overlap':False},{'text':guest,'is_subject':False,'overlap':False}]}})
    evidence=[S(evidence_id='own',span_start=0,span_end=len(own),source_type='SUBJECT'),S(evidence_id='guest',span_start=len(own),span_end=len(own+guest),source_type='SUBJECT')]
    memories=[S(evidence_ids=['own'],source_type='SUBJECT'),S(evidence_ids=['guest'],source_type='SUBJECT')]
    assert vp.classify_recorded_evidence(ep,S(evidence=evidence,memory_items=memories))=={'guest'}
    assert str(memories[0].source_type)=='SUBJECT' and str(memories[1].source_type)=='THIRD_PARTY'

def test_guest_introduction_is_remembered_as_voice_label_without_person_update(app,client,session,ready,monkeypatch):
    own,h,grant,call,worker=setup(app,client,session,ready,monkeypatch);reference(app,session,own,grant)
    app.state.speaker_encoder=type('Guest',(Encoder,),{'extract':lambda _,data:[0,1]})()
    class Intro:
        def transcribe_authorized(self,*args,**kwargs):return Transcript('大家好，我叫小李，今天来和大家聊聊。','fixture','fixture',{'speaker_sentences':[{'speaker_id':0,'text':'大家好，我叫小李，今天来和大家聊聊。','begin_time':0,'end_time':5500}]})
    upload_utterance(client,call,worker,'guest-intro');assert run_one(app,Intro())
    session.expire_all();assert {r.role for r in session.scalars(select(VoiceIdentity))}=={'subject','contact'}
    upload_utterance(client,call,worker,'guest-later');assert run_one(app,STT())
    session.expire_all();rows=list(session.scalars(select(VoiceUtterance)))
    later=next(r for r in rows if r.turn_id=='guest-later')
    assert later.report['speakers'][0]['name']=='小李' and not later.report['speakers'][0]['is_subject']
    assert session.scalar(select(func.count()).select_from(Episode))==0

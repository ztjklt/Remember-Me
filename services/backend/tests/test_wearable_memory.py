from types import SimpleNamespace as S
import pytest
from sqlalchemy import select
from app import voiceprints as vp
from app.models import Episode,MemoryItem,PersonTrait
from app.seed import seed_development_data
from app.worker import ProcessingWorker


def test_unknown_wearable_speech_still_finishes_without_training_owner(app,client,session):
    own=seed_development_data(session,subject_name='QA',actor_name='QA')
    h={'Authorization':'Bearer '+own.actor_token}
    response=client.post('/api/v1/episodes',headers=h,data={'subject_id':own.subject_id,'recording_consent_id':own.consent_id,
        'idempotency_key':'unknown-wearable','source':'WORK_3200','recorded_at':'2026-10-15T03:00:00Z','audio_ref':'qa.wav'},
        files={'file':('qa.wav',b'FAKE-AUDIO','audio/wav')})
    assert response.status_code==201,response.text
    eid=response.json()['episode_id']
    worker=ProcessingWorker(app.state.database,app.state.object_store,app.state.stt_provider,app.state.ai_client,backoff_seconds=0)
    for _ in range(3):worker.run_once()
    session.expire_all();ep=session.get(Episode,eid)
    assert ep.status=='ready' and ep.transcript
    notes=list(session.scalars(select(MemoryItem).where(MemoryItem.episode_id==eid)))
    assert notes and all(m.source_type=='THIRD_PARTY' and m.review_state=='pending' for m in notes)
    assert list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id==own.subject_id)))==[]
    assert client.get(f'/api/v1/episodes/{eid}/audio',headers=h).status_code==200


@pytest.mark.parametrize('revoked_scope',['capture','reference'])
def test_matched_wearable_sources_stop_training_when_either_voice_grant_is_revoked(app,client,session,revoked_scope):
    own=seed_development_data(session,subject_name='QA',actor_name='QA')
    h={'Authorization':'Bearer '+own.actor_token}
    def grant():return client.post('/api/v1/consents',headers=h,json={'subject_id':own.subject_id,'scope':'SPEAKER_IDENTIFICATION'}).json()['consent_id']
    ref,capture=grant(),grant()
    identity=vp.enroll(session,own.subject_id,own.actor_id,ref,[1.,0.],'qa-encoder-v1',{'kind':'fixture','id':'reference'},role='subject',label='QA',person_key='subject');session.commit()
    response=client.post('/api/v1/episodes',headers=h,data={'subject_id':own.subject_id,'recording_consent_id':own.consent_id,
        'idempotency_key':'matched-wearable','source':'WORK_3200','recorded_at':'2026-10-15T03:00:00Z','audio_ref':'qa.wav'},
        files={'file':('qa.wav',b'FAKE-AUDIO','audio/wav')})
    assert response.status_code==201
    eid=response.json()['episode_id'];worker=ProcessingWorker(app.state.database,app.state.object_store,app.state.stt_provider,app.state.ai_client,backoff_seconds=0)
    worker.run_once();session.expire_all();ep=session.get(Episode,eid)
    # Declared server-ASR fixture; never treated as actual acoustic accuracy.
    ep.capture_metadata={**(ep.capture_metadata or {}),'voiceprint_consent_id':capture,'speaker_report':{
        'voiceprint_model_version':'qa-encoder-v1','speakers':[{'speaker_id':0,'voice_identity_id':identity.identity_id,'is_subject':True,'voiceprint_status':'matched'}],
        'segments':[{'speaker_id':0,'is_subject':True,'overlap':False,'text':ep.transcript}]}}
    session.commit()
    original_ai=app.state.ai_client
    class SpanFixture:
        def process(self,payload):
            output=original_ai.process(payload)
            for evidence in output.evidence:
                evidence.span_start=payload.transcript.find(evidence.excerpt)
                evidence.span_end=evidence.span_start+len(evidence.excerpt)
            return output
    worker.ai=SpanFixture()
    worker.run_once();worker.run_once();session.expire_all()
    assert ep.status=='ready'
    assert list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id==own.subject_id)))
    identifier=capture if revoked_scope=='capture' else ref
    r=client.post(f'/api/v1/consents/{identifier}/revoke',headers=h);assert r.status_code==200,r.text
    session.expire_all()
    assert list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id==own.subject_id)))==[]
    assert all(m.review_state=='pending' for m in session.scalars(select(MemoryItem).where(MemoryItem.episode_id==eid)))
    assert client.get(f'/api/v1/episodes/{eid}/audio',headers=h).status_code==200


def test_mixed_wearable_spans_keep_only_verified_owner_and_exclude_overlap(app,client,session):
    from types import SimpleNamespace as N
    from app.contracts import SourceType
    own=seed_development_data(session,subject_name='QA',actor_name='QA')
    headers={'Authorization':'Bearer '+own.actor_token}
    grant=client.post('/api/v1/consents',headers=headers,json={'subject_id':own.subject_id,'scope':'SPEAKER_IDENTIFICATION'}).json()['consent_id']
    identity=vp.enroll(session,own.subject_id,own.actor_id,grant,[1.,0.],'qa-encoder-v1',{'kind':'fixture','id':'reference'},role='subject',label='QA',person_key='subject');session.commit()
    phrases=['我喜欢散步。','我喜欢游泳。','我们一起说话。']
    text=''.join(phrases);first=len(phrases[0]);second=first+len(phrases[1])
    ep=N(source='WORK_3200',subject_id=own.subject_id,actor_id=own.actor_id,transcript=text,capture_metadata={
        'voiceprint_consent_id':grant,'speaker_report':{'voiceprint_model_version':'qa-encoder-v1',
        'speakers':[{'speaker_id':0,'voice_identity_id':identity.identity_id,'is_subject':True,'voiceprint_status':'matched'},
                    {'speaker_id':1,'is_subject':False,'voiceprint_status':'unknown'}],
        'segments':[{'speaker_id':0,'is_subject':True,'text':phrases[0]},
                    {'speaker_id':1,'is_subject':False,'text':phrases[1]},
                    {'speaker_id':0,'is_subject':True,'overlap':True,'text':phrases[2]}]}})
    evidence=[N(evidence_id='owner',span_start=0,span_end=first,source_type=SourceType.SUBJECT),
              N(evidence_id='contact',span_start=first,span_end=second,source_type=SourceType.SUBJECT),
              N(evidence_id='overlap',span_start=second,span_end=len(text),source_type=SourceType.SUBJECT),
              N(evidence_id='crossing',span_start=0,span_end=second,source_type=SourceType.SUBJECT)]
    memories=[N(evidence_ids=[e.evidence_id],source_type=SourceType.SUBJECT) for e in evidence]
    excluded=vp.classify_recorded_evidence(ep,N(evidence=evidence,memory_items=memories),session)
    assert excluded=={'contact','overlap','crossing'}
    assert memories[0].source_type==SourceType.SUBJECT
    assert all(m.source_type==SourceType.THIRD_PARTY for m in memories[1:])

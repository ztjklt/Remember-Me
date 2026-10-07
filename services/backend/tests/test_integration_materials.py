"""Rules tested against real storage/API; model doubles are explicitly local tests."""
from sqlalchemy import select
from app.models import Episode, MemoryItem
from test_agent_workbench import setup_pair
import pytest


def test_full_reviewed_text_reaches_twin_even_when_summary_omits_fact(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    row = session.get(Episode, ep)
    row.transcript += '。我养的猫叫小麦。'
    session.commit()
    seen = []
    class Inspect:
        def answer(self, question, candidates):
            seen.extend(candidates)
            return dict(answer='不知道', response_type='UNKNOWN', evidence_ids=[], confidence=0, model_version='test')
    app.state.twin_client = Inspect()
    response = client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
        json={'question':'猫的名字？', 'cloud_consent_id':cloud})
    assert response.status_code == 200, response.text
    assert any('小麦' in s['excerpt'] for c in seen for s in c['evidence'])


def test_deleted_memory_is_not_resurrected_from_full_text(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    assert client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}', headers=oh).status_code == 200
    from app.materials import effective_materials
    candidates = effective_materials(session, owner.subject_id, {ep})
    assert not any(memory.content in s['excerpt'] for c in candidates for s in c['evidence'])


def test_deleted_shared_source_is_unavailable_in_story_and_audio(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    grant = client.post(root+'/grants', headers=oh, json={'episode_id':ep,
        'reader_actor_id':reader.actor_id,'include_audio_confirmed':True,'cloud_processing_allowed':True})
    assert grant.status_code == 201
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}', headers=oh)
    story = client.get(root+'/stories',headers=rh).json()['items'][0]
    assert story['unavailable'] and story['transcript'] is None and story['memories'] == []
    assert client.get(root+f'/stories/{ep}/audio', headers=rh).status_code == 404


def test_material_budget_rejects_instead_of_truncating(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    row = session.get(Episode, ep); row.transcript = '长' * 24001; session.commit()
    r = client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
        json={'question':'故事是什么？', 'cloud_consent_id':cloud})
    assert r.status_code == 413
    assert r.json()['error_code'] == 'CONTEXT_TOO_LARGE'


def test_profile_candidate_requires_explicit_approval_and_invalidates_on_source_change(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    from app.materials import effective_materials
    material = effective_materials(session, owner.subject_id, {ep})[0]['evidence'][0]
    session.commit()
    class Proposals:
        def propose(self, materials):
            return {'candidates':[{'domain':'PREFERENCES','statement':'可能重视安静的个人活动',
                'context':'仅根据本次讲述', 'evidence_ids':[material['evidence_id']],
                'counter_evidence_ids':[], 'kind':'habit'}], 'model_version':'test-real-boundary', 'prompt_version':'test'}
    app.state.profile_client = Proposals()
    root = f'/api/v1/workbench/subjects/{owner.subject_id}/profile-candidates'
    r = client.post(root+'/refresh', headers=oh, json={'cloud_consent_id':cloud})
    assert r.status_code == 202, r.text
    from app.profiles import run_profile_once
    run_profile_once(app.state.database, app.state.profile_client)
    candidate = client.get(root, headers=oh).json()['items'][0]
    assert candidate['status'] == 'pending'
    assert candidate['independent_episodes'] == 1
    assert client.post(root+'/'+candidate['candidate_id']+'/confirm', headers=rh).status_code == 404
    assert client.post(root+'/'+candidate['candidate_id']+'/confirm', headers=oh).status_code == 200
    assert client.get(root, headers=oh).json()['items'][0]['status'] == 'confirmed'
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}', headers=oh)
    assert client.get(root, headers=oh).json()['items'][0]['status'] == 'stale'


@pytest.mark.parametrize('mutation',['delete','bad_evidence'])
def test_profile_never_publishes_invalid_or_changed_sources(app,client,session,mutation):
    from app.profiles import run_profile_once
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    root=f'/api/v1/workbench/subjects/{owner.subject_id}/profile-candidates'
    class Changed:
        def propose(self,materials):
            if mutation=='delete':
                assert client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}',headers=oh).status_code==200
            return {'candidates':[{'domain':'PREFERENCES','kind':'habit','statement':'偏好散步',
                'context':'一次观察','evidence_ids':[materials[0]['evidence_id'] if mutation=='delete' else 'fake-source'],
                'counter_evidence_ids':[]}], 'model_version':'test','prompt_version':'test'}
    assert client.post(root+'/refresh',headers=oh,json={'cloud_consent_id':cloud}).status_code==202
    run_profile_once(app.state.database,Changed())
    result=client.get(root,headers=oh).json()
    assert result['items']==[] and result['jobs'][0]['status']=='failed'


def test_android_stops_after_stt_until_explicit_confirmation(app,client,session):
    from app.worker import ProcessingWorker
    from app.ai_core import FakeAiCoreClient
    from app.models import Job
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    class Count(FakeAiCoreClient):
        calls=0
        def process(self,payload):
            self.calls+=1
            return super().process(payload)
    ai=Count()
    r=client.post('/api/v1/episodes',headers=oh,data={'subject_id':owner.subject_id,
        'recording_consent_id':owner.consent_id,'source':'ANDROID_MIC','recorded_at':'2026-10-07T12:00:00Z',
        'audio_ref':'phone.m4a','idempotency_key':'android-review'},files={'file':('phone.m4a',b'TEST','audio/mp4')})
    assert r.status_code==201
    episode=r.json()['episode_id']
    worker=ProcessingWorker(app.state.database,app.state.object_store,app.state.stt_provider,ai,backoff_seconds=0)
    worker.run_once();worker.run_once();worker.run_once()
    assert ai.calls==0
    assert client.get(f'/api/v1/episodes/{episode}/transcript-review',headers=oh).json()['state']=='reviewing'
    assert client.patch(f'/api/v1/episodes/{episode}/transcript-review',headers=oh,json={'transcript':'我不喜欢夜跑。'}).status_code==200
    worker.run_once();worker.run_once()
    assert ai.calls==1
    session.expire_all()
    saved=session.get(Episode,episode)
    assert saved.source=='ANDROID_MIC' and saved.transcript=='我不喜欢夜跑。'
    assert saved.stt_transcript!=saved.transcript


def test_partial_third_party_span_is_not_relabelled_subject(app,client,session):
    from app.models import Evidence
    from app.materials import effective_materials
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    story=session.get(Episode,ep);story.transcript='王建国说他父亲在铁路工作。'
    for source in session.scalars(select(Evidence).where(Evidence.episode_id==ep)):
        source.excerpt=story.transcript[:-1];source.span_start=0;source.span_end=len(source.excerpt);source.source_type='THIRD_PARTY'
    session.commit()
    sources=[e for c in effective_materials(session,owner.subject_id,{ep}) for e in c['evidence']]
    assert sources and all(e['source_type']=='THIRD_PARTY' for e in sources)


def test_pending_revision_never_enters_twin_via_unextracted_raw_text(app,client,session):
    from app.models import MemoryRevision
    from app.materials import effective_materials
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    session.add(MemoryRevision(revision_id='test-pending',subject_id=owner.subject_id,
        episode_id=ep,target_memory_id=memory.memory_item_id,kind='correction',status='pending'))
    session.get(Episode,ep).transcript+='。这里还有一项未提取但没有确认的新说法。'
    session.commit()
    assert effective_materials(session,owner.subject_id,{ep})==[]


@pytest.mark.parametrize('preexisting_grant',[False,True])
def test_empty_pending_revision_cannot_share_text_or_audio(app,client,session,preexisting_grant):
    from app.models import MemoryRevision, StoryGrant
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    original=session.get(Episode,ep)
    values={c.name:getattr(original,c.name) for c in Episode.__table__.columns}
    values.update(episode_id='empty-revision',idempotency_key='empty-revision',transcript='Private pending correction')
    session.add(Episode(**values));session.flush()
    session.add(MemoryRevision(revision_id='empty-pending',subject_id=owner.subject_id,
        episode_id='empty-revision',target_memory_id=memory.memory_item_id,kind='correction',status='pending'))
    if preexisting_grant:
        session.add(StoryGrant(grant_id='old-grant',episode_id='empty-revision',
            reader_actor_id=reader.actor_id,cloud_processing_allowed=1))
    session.commit()
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    if not preexisting_grant:
        response=client.post(root+'/grants',headers=oh,json={'episode_id':'empty-revision',
            'reader_actor_id':reader.actor_id,'include_audio_confirmed':True,'cloud_processing_allowed':True})
        assert response.status_code==422, response.text
    else:
        story=client.get(root+'/stories',headers=rh).json()['items'][0]
        assert story['unavailable'] and story['transcript'] is None and story['memories']==[]
        assert client.get(root+'/stories/empty-revision/audio',headers=rh).status_code==404


def test_persisted_answer_exposes_real_source_basis_and_rechecks_it(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    path=f'/api/v1/subjects/{owner.subject_id}/twin/answers'
    r=client.post(path,headers=oh,json={'question':'喜欢什么','cloud_consent_id':cloud})
    assert r.status_code==200
    value=r.json();assert len(value['source_version'])==64
    # Simulate a legitimate source mutation independent of explicit invalidators.
    session.get(Episode,ep).transcript+='。后来我又补充了其他内容。';session.commit()
    assert client.get(path+'/'+value['answer_id'],headers=oh).json()['stale'] is True

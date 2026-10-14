"""Transport recovery and revocation of retained private training artifacts."""
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.learning_models import PersonalTrainingJob,PersonalTrainerHeartbeat
from app.models import utcnow
from test_personal_learning_api import (learning_owner,_enable,_claim,_claimed_job,
    _path,_result_payload,_worker_headers,_ready_sources)

def test_idle_enabled_preference_does_not_rollback_trainer_heartbeat(learning_owner,client,app,session):
    assert _enable(client,learning_owner).status_code==200
    assert _claim(client,app).json()['job'] is None
    session.expire_all()
    heartbeat=session.get(PersonalTrainerHeartbeat,'synthetic-worker')
    assert heartbeat is not None
    assert client.get(_path(learning_owner),headers=learning_owner[2]).json()['trainer_available'] is True
    heartbeat.seen_at=utcnow()-timedelta(minutes=5);session.commit()
    assert _claim(client,app).json()['job'] is None
    session.expire_all()
    assert client.get(_path(learning_owner),headers=learning_owner[2]).json()['trainer_available'] is True

def test_expired_lease_retries_with_backoff_and_a_bounded_attempt_count(learning_owner,client,app,session):
    job=_claimed_job(client,app,session,learning_owner)
    identifiers=[]
    for attempt in range(3):
        identifiers.append(job['job_id'])
        session.expire_all();row=session.get(PersonalTrainingJob,job['job_id'])
        row.lease_expires_at=utcnow()-timedelta(seconds=1);session.commit()
        assert _claim(client,app).json()['job'] is None
        session.expire_all();row=session.get(PersonalTrainingJob,job['job_id'])
        assert row.status=='failed' and row.result['reason']=='TRAINER_LEASE_EXPIRED'
        row.updated_at=utcnow()-timedelta(minutes=10);session.commit()
        next_job=_claim(client,app).json()['job']
        if attempt<2:
            assert next_job and next_job['job_id'] not in identifiers
            assert next_job['plan']['dataset_sha256']==job['plan']['dataset_sha256']
            job=next_job
        else:
            assert next_job is None
    assert len(set(identifiers))==3

@pytest.mark.parametrize('status',['failed','rejected'])
def test_stable_runtime_failure_or_rejection_is_not_retrained_forever(learning_owner,client,app,session,status):
    job=_claimed_job(client,app,session,learning_owner)
    payload=_result_payload(job);payload['result']['status']=status
    response=client.post('/internal/personal-learning/jobs/'+job['job_id']+'/result',headers=_worker_headers(),json=payload)
    assert response.status_code==200,response.text
    session.expire_all();row=session.get(PersonalTrainingJob,job['job_id'])
    row.updated_at=utcnow()-timedelta(days=1);session.commit()
    assert _claim(client,app).json()['job'] is None

def test_local_authorization_transport_failure_can_retry_if_owner_grant_is_still_valid(learning_owner,client,app,session):
    job=_claimed_job(client,app,session,learning_owner)
    payload=_result_payload(job)
    payload['result'].update(status='revoked',reason='authorization_or_sources_changed')
    response=client.post('/internal/personal-learning/jobs/'+job['job_id']+'/result',headers=_worker_headers(),json=payload)
    assert response.status_code==200 and response.json()['status']=='failed'
    session.expire_all();row=session.get(PersonalTrainingJob,job['job_id'])
    row.updated_at=utcnow()-timedelta(seconds=31);session.commit()
    assert _claim(client,app).json()['job']['job_id']!=job['job_id']

@pytest.mark.parametrize('action',['disable','revoke'])
def test_revocation_purges_failed_rejected_and_successful_candidate_artifacts(learning_owner,client,app,session,action):
    job=_claimed_job(client,app,session,learning_owner)
    row=session.get(PersonalTrainingJob,job['job_id'])
    original={c.name:getattr(row,c.name) for c in PersonalTrainingJob.__table__.columns}
    identifiers=[]
    for status in ['failed','rejected','awaiting_validation']:
        identifier='artifact_'+status;identifiers.append(identifier)
        session.add(PersonalTrainingJob(**dict(original,job_id=identifier,status=status)))
    row.status='failed';session.commit()
    if action=='disable':
        response=client.put(_path(learning_owner),headers=learning_owner[2],json={'enabled':False})
    else:
        response=client.post('/api/v1/consents/'+learning_owner[4]['MODEL_TRAINING']+'/revoke',headers=learning_owner[2])
    assert response.status_code==200,response.text
    response=_claim(client,app)
    assert response.json()['job'] is None
    assert set(identifiers)<=set(response.json()['purge_job_ids'])
    session.expire_all()
    assert all(session.get(PersonalTrainingJob,identifier).status=='revoked' for identifier in identifiers)

def test_copied_originals_from_different_partitions_are_not_deduplicated_before_leakage_check(learning_owner,client,app,session):
    from hashlib import sha256
    from app.models import Episode,Evidence,MemoryItem
    from app.personal_learning import examples
    groups=_ready_sources(client,app,session,learning_owner)
    subject=learning_owner[0].subject_id
    train=next(g for g in groups if int(sha256(f'personal-training-v1:{subject}:{g}'.encode()).hexdigest(),16)%10>=4)
    test=next(g for g in groups if 2<=int(sha256(f'personal-training-v1:{subject}:{g}'.encode()).hexdigest(),16)%10<4)
    text='这段本人原文字在两个独立上传来源中完全相同。'
    for group in [train,test]:
        episode=session.get(Episode,group);episode.transcript=episode.stt_transcript=text
        evidence=session.scalar(select(Evidence).where(Evidence.episode_id==group))
        evidence.excerpt=text;evidence.span_start=0;evidence.span_end=len(text)
        session.scalar(select(MemoryItem).where(MemoryItem.episode_id==group)).content=text
    session.commit()
    selected=examples(session,subject,learning_owner[0].actor_id)
    assert {row.source_group_id for row in selected if row.target==text}=={train,test}
    response=_enable(client,learning_owner)
    assert response.status_code==200,response.text
    assert response.json()['status']=='ineligible_data'
    assert response.json()['dataset']['missing']==['TRAINING_DUPLICATE_ACROSS_HOLDOUT']
    assert response.json()['job'] is None and response.json()['activation_allowed'] is False
    assert session.scalar(select(PersonalTrainingJob)) is None
    view=client.get(_path(learning_owner),headers=learning_owner[2])
    assert view.status_code==200 and view.json()['status']=='ineligible_data'
    disabled=client.put(_path(learning_owner),headers=learning_owner[2],json={'enabled':False})
    assert disabled.status_code==200 and disabled.json()['status']=='disabled'
    assert client.get(_path(learning_owner),headers=learning_owner[2]).json()['enabled'] is False

def test_ineligible_new_data_still_invalidates_and_purges_old_worker_artifacts(learning_owner,client,app,session):
    from app.models import Episode,Evidence,MemoryItem
    job=_claimed_job(client,app,session,learning_owner)
    parts=job['plan']
    groups=[parts['train'][0]['source_group_id'],parts['test'][0]['source_group_id']]
    text='新核对后两个不同分区的来源中出现了同一段原文字。'
    for group in groups:
        episode=session.get(Episode,group);episode.transcript=episode.stt_transcript=text
        evidence=session.scalar(select(Evidence).where(Evidence.episode_id==group))
        evidence.excerpt=text;evidence.span_start=0;evidence.span_end=len(text)
        session.scalar(select(MemoryItem).where(MemoryItem.episode_id==group)).content=text
    session.commit()
    first=_claim(client,app)
    assert first.status_code==200 and first.json()['job'] is None
    session.expire_all()
    assert session.get(PersonalTrainingJob,job['job_id']).status=='stale'
    assert job['job_id'] in _claim(client,app).json()['purge_job_ids']

@pytest.mark.parametrize('change',['disabled','consent_revoked','owner_changed'])
def test_claim_rechecks_authorization_after_publication_lock_refresh(learning_owner,client,app,session,monkeypatch,change):
    from app.api import personal_learning as api
    from app.learning_models import LearningPreference
    from app.models import Consent,Subject
    _ready_sources(client,app,session,learning_owner)
    response=_enable(client,learning_owner);assert response.status_code==200
    identifier=response.json()['job']['job_id']
    original=api.publication_lock
    def changed_before_lock(database,subject):
        own,other,_,_,grants=learning_owner
        if change=='disabled':database.get(LearningPreference,(own.subject_id,own.actor_id)).enabled=False
        elif change=='consent_revoked':
            grant=database.get(Consent,grants['MODEL_TRAINING']);grant.status='revoked';grant.revoked_at=utcnow()
        else:database.get(Subject,subject).owner_actor_id=other.actor_id
        database.commit()
        original(database,subject)
    monkeypatch.setattr(api,'publication_lock',changed_before_lock)
    claimed=_claim(client,app)
    assert claimed.status_code==200 and claimed.json()['job'] is None
    assert 'plan' not in claimed.json()
    session.expire_all()
    assert session.get(PersonalTrainingJob,identifier).status=='revoked'

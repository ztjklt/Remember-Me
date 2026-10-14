"""Real API/storage boundaries with synthetic sources and fake model outputs.

These tests verify consent, leases and sealed human assessment. They do not
establish that a trained model reconstructs anyone's personality.
"""
from datetime import timedelta
from hashlib import sha256

from pydantic import SecretStr
import pytest
from sqlalchemy import select

from app.models import Episode, Evidence, MemoryItem, TwinAnswer, utcnow
from app.learning_models import PersonalTrainingJob, FidelityCase
from app.personal_learning import POLICY
from app.seed import seed_development_data
from test_twin_voice import _record, TinyEncoder


class Simulation:
    def __init__(self): self.options=[]
    def answer(self, question, candidates, **kwargs):
        self.options.append(kwargs)
        source=candidates[0]['evidence'][0]
        return dict(answer=source['excerpt'],response_type='SIMULATION',
                    evidence_ids=[source['evidence_id']],confidence=.8,
                    model_version='test-prediction-v1')


@pytest.fixture
def learning_owner(app,client,session):
    own=seed_development_data(session,subject_name='Synthetic learner',actor_name='Synthetic learner')
    other=seed_development_data(session,subject_name='Other synthetic owner',actor_name='Other synthetic owner')
    headers={'Authorization':'Bearer '+own.actor_token}
    foreign_headers={'Authorization':'Bearer '+other.actor_token}
    grants={}
    for scope in ['CLOUD_TWIN','VOICE','MODEL_TRAINING']:
        response=client.post('/api/v1/consents',headers=headers,json={'subject_id':own.subject_id,'scope':scope})
        assert response.status_code==201,response.text
        grants[scope]=response.json()['consent_id']
    app.state.settings.ai_backend='http'
    app.state.embedding_encoder=TinyEncoder()
    app.state.twin_client=Simulation()
    app.state.settings.personal_trainer_secret=SecretStr('synthetic-trainer-secret-32-characters')
    return own,other,headers,foreign_headers,grants


def _source(client,app,session,fixture):
    own,_,headers,_,_=fixture
    identifier=_record(client,app,own.subject_id,own.consent_id,headers)
    session.expire_all()
    return session.get(Episode,identifier)


def _ready_sources(client,app,session,fixture):
    """Synthetic reviewed original spans, sufficient for actual split gates."""
    source=_source(client,app,session,fixture)
    evidence=session.scalar(select(Evidence).where(Evidence.episode_id==source.episode_id))
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==source.episode_id))
    evalues={c.name:getattr(source,c.name) for c in Episode.__table__.columns}
    vvalues={c.name:getattr(evidence,c.name) for c in Evidence.__table__.columns}
    mvalues={c.name:getattr(memory,c.name) for c in MemoryItem.__table__.columns}
    # Populate fixed numbers in each original-source split; all holdouts are
    # distinct human targets. This creates fixtures, not model-quality proof.
    wanted={'train':40,'validation':15,'test':15};selected=[]
    for n in range(1000):
        group=f'learning_source_{n}'
        bucket=int(sha256(f'personal-training-v1:{source.subject_id}:{group}'.encode()).hexdigest(),16)%10
        split='validation' if bucket<2 else 'test' if bucket<4 else 'train'
        if not wanted[split]:continue
        wanted[split]-=1
        text=f'这是我已经核对的第 {n} 段独立原始记录，我喜欢在地点 {n} 散步。'
        evid=f'learning_evidence_{n}';mem=f'learning_memory_{n}'
        session.add(Episode(**dict(evalues,episode_id=group,idempotency_key=group,transcript=text,
            stt_transcript=text,created_at=utcnow(),updated_at=utcnow())))
        session.flush()
        session.add(Evidence(**dict(vvalues,evidence_id=evid,episode_id=group,source_ref=group,
            excerpt=text,span_start=0,span_end=len(text))))
        session.add(MemoryItem(**dict(mvalues,memory_item_id=mem,episode_id=group,content=text,evidence_ids=[evid])))
        selected.append(group)
        if not any(wanted.values()):break
    assert not any(wanted.values())
    session.commit()
    return selected


def _path(fixture):return f'/api/v1/subjects/{fixture[0].subject_id}/twin/learning'
def _worker_headers():return {'X-Personal-Trainer-Secret':'synthetic-trainer-secret-32-characters'}
def _enable(client,fixture,**changes):
    body=dict(enabled=True,training_consent_id=fixture[4]['MODEL_TRAINING'],accepted_policy=POLICY)
    return client.put(_path(fixture),headers=fixture[2],json={**body,**changes})
def _claim(client,app,**changes):
    body=dict(worker_id='synthetic-worker',base_model=app.state.settings.personal_training_base_model,available=True)
    return client.post('/internal/personal-learning/claim',headers=_worker_headers(),json={**body,**changes})


def test_learning_requires_owner_and_separate_training_consent(learning_owner,client,app,session):
    own,other,headers,foreign_headers,grants=learning_owner
    path=_path(learning_owner)
    assert client.get(path,headers=foreign_headers).status_code==404
    assert client.put(path,headers=foreign_headers,json=dict(enabled=True,
        training_consent_id=grants['MODEL_TRAINING'],accepted_policy=POLICY)).status_code==404
    for grant in [own.consent_id,grants['CLOUD_TWIN'],grants['VOICE']]:
        assert _enable(client,learning_owner,training_consent_id=grant).status_code in {403,404}
    assert _enable(client,learning_owner,accepted_policy='outdated-policy').status_code in {400,409,422}
    assert _enable(client,learning_owner).status_code==200
    assert client.get(path,headers=headers).json()['enabled'] is True


def test_insufficient_data_never_queues_or_claims_training(learning_owner,client,app,session):
    assert _enable(client,learning_owner).status_code==200
    response=_claim(client,app)
    assert response.status_code==200,response.text
    assert response.json().get('job') is None
    assert session.scalar(select(PersonalTrainingJob)) is None
    view=client.get(_path(learning_owner),headers=learning_owner[2]).json()
    assert view['status']=='insufficient_data'


def test_trainer_endpoint_rejects_mobile_tokens_and_missing_or_wrong_secret(learning_owner,client,app):
    body=dict(worker_id='synthetic-worker',base_model=app.state.settings.personal_training_base_model,available=True)
    for headers in [{},learning_owner[2],{'X-Personal-Trainer-Secret':'wrong'}]:
        response=client.post('/internal/personal-learning/claim',headers=headers,json=body)
        assert response.status_code in {401,403,404},response.text
    app.state.settings.personal_trainer_secret=SecretStr('')
    assert _claim(client,app).status_code in {401,403,404,503}


def test_claim_exports_only_reviewed_owner_originals_and_seals_holdouts(learning_owner,client,app,session):
    groups=_ready_sources(client,app,session,learning_owner)
    own,other,_,_,_=learning_owner
    original=session.get(Episode,groups[0])
    unreviewed=session.get(Episode,groups[1]);unreviewed.transcript_reviewed_at=None
    wrong_review=session.get(Episode,groups[2]);wrong_review.transcript_reviewed_by=other.actor_id
    third_party=session.scalar(select(Evidence).where(Evidence.episode_id==groups[3]));third_party.source_type='THIRD_PARTY'
    foreign_actor=session.get(Episode,groups[4]);foreign_actor.actor_id=other.actor_id
    deleted=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==groups[5]));deleted.deleted_at=utcnow()
    session.commit()
    assert _enable(client,learning_owner).status_code==200
    response=_claim(client,app)
    assert response.status_code==200,response.text
    data=response.json();assert data.get('job')
    plan=data['job']['plan']
    examples=plan['train']+plan['validation']+plan['test']
    assert examples
    selected={e['source_group_id'] for e in examples}
    assert not set(groups[1:6]).intersection(selected)
    assert all(e['subject_id']==own.subject_id and e['actor_id']==own.actor_id and
        e['source_type'] in {'SUBJECT','CALIBRATION'} and e['target_origin']=='human' and
        e['target']==e['verified_target'] for e in examples)
    partitions=[{e['source_group_id'] for e in plan[name]} for name in ['train','validation','test']]
    assert not partitions[0]&partitions[1] and not partitions[0]&partitions[2] and not partitions[1]&partitions[2]


def _claimed_job(client,app,session,fixture):
    _ready_sources(client,app,session,fixture)
    assert _enable(client,fixture).status_code==200
    response=_claim(client,app)
    assert response.status_code==200,response.text
    job=response.json()['job']
    assert job
    return job


def _result_payload(job):
    plan=job['plan']
    return dict(worker_id='synthetic-worker',lease_token=job['lease_token'],result=dict(
        status='failed',reason='synthetic_runtime_failure',subject_id=plan['subject_id'],
        person_model_version=plan['person_model_version'],source_basis=plan['source_basis'],
        dataset_sha256=plan['dataset_sha256'],train_count=len(plan['train']),
        validation_count=len(plan['validation']),test_count=len(plan['test'])))


def test_training_lease_is_private_and_bound_to_worker_and_job(learning_owner,client,app,session):
    job=_claimed_job(client,app,session,learning_owner)
    identifier=job['job_id']
    heartbeat='/internal/personal-learning/jobs/'+identifier+'/heartbeat'
    result='/internal/personal-learning/jobs/'+identifier+'/result'
    payload=dict(worker_id='synthetic-worker',lease_token=job['lease_token'])
    assert client.post(heartbeat,headers=_worker_headers(),json=payload).status_code==200
    for change in [dict(worker_id='different-worker'),dict(lease_token='x'*43)]:
        response=client.post(heartbeat,headers=_worker_headers(),json={**payload,**change})
        assert response.status_code==401,response.text
        rejected=client.post(result,headers=_worker_headers(),json={**_result_payload(job),**change})
        assert rejected.status_code==401,rejected.text
    assert client.post(result,headers=learning_owner[2],json=_result_payload(job)).status_code in {401,403,404}
    response=client.post(result,headers=_worker_headers(),json=_result_payload(job))
    assert response.status_code==200,response.text
    session.expire_all()
    row=session.get(PersonalTrainingJob,identifier)
    assert row.status=='failed' and row.lease_token_hash is None
    assert client.post(heartbeat,headers=_worker_headers(),json=payload).status_code==401
    view=client.get(_path(learning_owner),headers=learning_owner[2]).json()
    assert job['lease_token'] not in str(view)
    assert row.lease_token_hash is None


@pytest.mark.parametrize('action',['disable','revoke','stale','expired'])
def test_changed_training_permission_sources_or_lease_rejects_worker_result(learning_owner,client,app,session,action):
    job=_claimed_job(client,app,session,learning_owner)
    identifier=job['job_id'];own,_,headers,_,grants=learning_owner
    if action=='disable':
        assert client.put(_path(learning_owner),headers=headers,json={'enabled':False}).status_code==200
    elif action=='revoke':
        assert client.post('/api/v1/consents/'+grants['MODEL_TRAINING']+'/revoke',headers=headers).status_code==200
    elif action=='stale':
        row=session.scalar(select(Episode).where(Episode.subject_id==own.subject_id))
        row.transcript+=' 新核对的修订';session.commit()
    else:
        row=session.get(PersonalTrainingJob,identifier);row.lease_expires_at=utcnow()-timedelta(seconds=1);session.commit()
    payload=dict(worker_id='synthetic-worker',lease_token=job['lease_token'])
    response=client.post('/internal/personal-learning/jobs/'+identifier+'/heartbeat',headers=_worker_headers(),json=payload)
    assert response.status_code in {401,403,404,409},response.text
    response=client.post('/internal/personal-learning/jobs/'+identifier+'/result',headers=_worker_headers(),json=_result_payload(job))
    assert response.status_code in {401,403,404,409},response.text
    session.expire_all()
    row=session.get(PersonalTrainingJob,identifier)
    assert row.status!='trained'
    assert not row.result or row.result.get('status')!='trained'


def test_worker_result_must_match_the_claimed_dataset_and_version(learning_owner,client,app,session):
    job=_claimed_job(client,app,session,learning_owner)
    path='/internal/personal-learning/jobs/'+job['job_id']+'/result'
    payload=_result_payload(job)
    for field,value in [('subject_id',learning_owner[1].subject_id),('source_basis','0'*64),
            ('dataset_sha256','f'*64),('person_model_version','99999'),('train_count',99999)]:
        response=client.post(path,headers=_worker_headers(),json={**payload,'result':{**payload['result'],field:value}})
        assert response.status_code in {403,404,409,422},response.text
    session.expire_all()
    assert session.get(PersonalTrainingJob,job['job_id']).status=='running'


def test_reported_training_candidate_waits_for_validation_and_cannot_auto_activate(learning_owner,client,app,session):
    job=_claimed_job(client,app,session,learning_owner)
    path='/internal/personal-learning/jobs/'+job['job_id']+'/result'
    payload=_result_payload(job)
    candidate={**payload['result'],'status':'trained','reason':'synthetic_worker_report',
        'adapter_sha256':'a'*64,'metrics':dict(baseline_validation_loss=1.,validation_loss=.8,
            baseline_test_loss=1.,test_loss=.8,weight_delta_l2=.1,
            optimizer_steps=job['policy']['iterations'],trainable_parameter_count=100,
            peak_memory_bytes=1000,mlx_lm_version='synthetic-test')}
    assert client.post(path,headers=_worker_headers(),json={**payload,'result':{**candidate,
        'activation_allowed':True}}).status_code==422
    response=client.post(path,headers=_worker_headers(),json={**payload,'result':candidate})
    assert response.status_code==200,response.text
    assert response.json()=={'status':'awaiting_validation','activation_allowed':False}
    view=client.get(_path(learning_owner),headers=learning_owner[2]).json()
    assert view['status']=='awaiting_validation' and view['activation_allowed'] is False
    assert view['job']['activation_allowed'] is False
    assert view['job']['result']['requires_personality_evaluation'] is True
    assert job['lease_token'] not in str(view)


def _case(client,fixture,question='赶时间时，你会先选择什么？'):
    path=f'/api/v1/subjects/{fixture[0].subject_id}/twin/fidelity'
    response=client.post(path+'/cases',headers=fixture[2],json={'question':question,'cloud_consent_id':fixture[4]['CLOUD_TWIN']})
    assert response.status_code==201,response.text
    return path,response.json()


def test_fidelity_has_no_score_without_independent_human_assessment(learning_owner,client,app,session):
    own,_,headers,foreign_headers,_=learning_owner
    path=f'/api/v1/subjects/{own.subject_id}/twin/fidelity'
    assert client.get(path,headers=foreign_headers).status_code==404
    response=client.get(path,headers=headers)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['overall']['agreement_rate'] is None
    assert all(row['agreement_rate'] is None for row in data['dimensions'])
    assert data['model_diagnostics']['agreement_rate'] is None


def test_fidelity_prediction_stays_private_until_human_answer_and_never_enters_chat_or_training(learning_owner,client,app,session):
    _source(client,app,session,learning_owner)
    own,_,headers,foreign_headers,_=learning_owner
    path,created=_case(client,learning_owner)
    identifier=created['case_id']
    assert not created.get('locked_answer')
    assert created['ratings']=={}
    row=session.get(FidelityCase,identifier)
    assert row.locked_answer
    assert 'locked_answer' not in client.get(path+'/cases/'+identifier,headers=headers).json()
    assert 'locked_answer' not in client.get(path,headers=headers).json()['cases'][0]
    assert client.post(path+'/cases/'+identifier+'/ratings',headers=headers,
        json={'ratings':{'DECISION':'MATCH'}}).status_code==409
    assert session.get(TwinAnswer,row.answer_id) is None
    public=client.get(f'/api/v1/subjects/{own.subject_id}/twin/answers/{row.answer_id}',headers=headers)
    assert public.status_code==404
    assert client.post(path+'/cases/'+identifier+'/human-answer',headers=foreign_headers,
        json={'answer':'我会先核对最关键的一项。','confirmed':True}).status_code==404
    assert client.post(path+'/cases/'+identifier+'/human-answer',headers=headers,
        json={'answer':'我会先核对最关键的一项。','confirmed':False}).status_code==422
    human='这段封存的人类验证答案不能进入普通历史检索。'
    response=client.post(path+'/cases/'+identifier+'/human-answer',headers=headers,json={'answer':human,'confirmed':True})
    assert response.status_code==200,response.text
    assert response.json()['locked_answer']==row.locked_answer
    session.expire_all()
    assert not list(session.scalars(select(TwinAnswer).where(TwinAnswer.subject_id==own.subject_id)))
    from app.personal_learning import examples
    assert human not in str(examples(session,own.subject_id,own.actor_id))
    from app.chat_memory import history
    from app.twin_basis import current
    assert human not in str(history(session,own.subject_id,own.actor_id,current(session,own.subject_id)))
    from app.twin_fidelity import DIMENSIONS
    assert client.post(path+'/cases/'+identifier+'/ratings',headers=headers,
        json={'ratings':{dimension:'MATCH' for dimension in DIMENSIONS}}).status_code==200
    score=client.get(path,headers=headers).json()
    assert score['overall']['agreement_rate'] is None
    assert score['accepted_observation_count']==0
    assert score['diagnostic_case_count']==1
    assert 'NOT_FROZEN_HOLDOUT' in score['excluded_observations'][0]['reasons']


def test_fidelity_human_answer_and_ratings_are_immutable_and_owner_scoped(learning_owner,client,app,session):
    from app.twin_fidelity import DIMENSIONS
    _source(client,app,session,learning_owner)
    _,_,headers,foreign_headers,_=learning_owner
    path,created=_case(client,learning_owner)
    target=path+'/cases/'+created['case_id']
    assert client.get(target,headers=foreign_headers).status_code==404
    human={'answer':'我会先列出最关键的一项。','confirmed':True}
    assert client.post(target+'/human-answer',headers=headers,json=human).status_code==200
    assert client.post(target+'/human-answer',headers=headers,json=human).status_code==200
    assert client.post(target+'/human-answer',headers=headers,
        json={**human,'answer':'换成另一种回答。'}).status_code==409
    ratings={dimension:'MATCH' for dimension in DIMENSIONS}
    assert client.post(target+'/ratings',headers=foreign_headers,json={'ratings':ratings}).status_code==404
    for invalid in [{'DECISION':'MATCH'},{**ratings,'DECISION':'LLM_MATCH'},
            {**ratings,'MADE_UP':'MATCH'}]:
        assert client.post(target+'/ratings',headers=headers,json={'ratings':invalid}).status_code==422
    response=client.post(target+'/ratings',headers=headers,json={'ratings':ratings})
    assert response.status_code==200,response.text
    session.expire_all();stamp=session.get(FidelityCase,created['case_id']).rated_at
    assert client.post(target+'/ratings',headers=headers,json={'ratings':ratings}).status_code==200
    session.expire_all();assert session.get(FidelityCase,created['case_id']).rated_at==stamp
    assert client.post(target+'/ratings',headers=headers,
        json={'ratings':{**ratings,'DECISION':'DIFFERENT'}}).status_code==409


def test_old_model_calibration_is_diagnostic_and_never_creates_a_fidelity_score(learning_owner,client,app,session):
    from app.models import CalibrationRun
    from app.twin_fidelity import DIMENSIONS
    _source(client,app,session,learning_owner)
    own,_,headers,_,grants=learning_owner
    result=client.post(f'/api/v1/subjects/{own.subject_id}/twin/answers',headers=headers,
        json={'question':'时间紧时会怎么选？','cloud_consent_id':grants['CLOUD_TWIN']})
    assert result.status_code==200,result.text
    calibration=client.post(f'/api/v1/subjects/{own.subject_id}/calibrations',headers=headers,
        json={'twin_answer_id':result.json()['answer_id'],'cloud_consent_id':grants['CLOUD_TWIN']})
    assert calibration.status_code==200,calibration.text
    row=session.get(CalibrationRun,calibration.json()['calibration_id'])
    row.status='complete';row.comparison_model_version='synthetic-old-llm-diagnostic'
    row.dimension_diffs=[{'dimension':d,'alignment':'MATCH'} for d in DIMENSIONS]
    session.commit()
    response=client.get(f'/api/v1/subjects/{own.subject_id}/twin/fidelity',headers=headers)
    assert response.status_code==200,response.text
    report=response.json()
    assert report['model_diagnostics']['diagnostic_calibration_count']==1
    assert report['model_diagnostics']['agreement_rate'] is None
    assert report['accepted_observation_count']==0
    assert report['overall']['agreement_rate'] is None
    assert all(item['agreement_rate'] is None for item in report['dimensions'])


def test_human_reference_already_seen_in_sources_cannot_count_as_unseen_prediction(learning_owner,client,app,session):
    from app.twin_fidelity import DIMENSIONS
    episode=_source(client,app,session,learning_owner)
    path,created=_case(client,learning_owner)
    target=path+'/cases/'+created['case_id'];headers=learning_owner[2]
    response=client.post(target+'/human-answer',headers=headers,
        json={'answer':episode.transcript,'confirmed':True})
    assert response.status_code==200,response.text
    assert client.post(target+'/ratings',headers=headers,
        json={'ratings':{dimension:'MATCH' for dimension in DIMENSIONS}}).status_code==200
    report=client.get(path,headers=headers).json()
    assert report['accepted_observation_count']==0
    assert report['excluded_observation_count']==1
    assert 'HUMAN_ANSWER_EXPOSED' in report['excluded_observations'][0]['reasons']
    assert report['overall']['agreement_rate'] is None


def test_personal_learning_migration_preserves_existing_owner_and_consent(tmp_path):
    from alembic import command
    from sqlalchemy import create_engine,inspect
    from sqlalchemy.orm import Session
    from conftest import alembic_config
    from app.models import Consent,ConsentScope
    from app.repositories.consents import ConsentRepository
    url=f'sqlite:///{tmp_path / "learning-upgrade.db"}'
    config=alembic_config(url)
    command.upgrade(config,'0020_chat_memory')
    engine=create_engine(url)
    try:
        with Session(engine) as database:
            own=seed_development_data(database,subject_name='Existing owner',actor_name='Existing owner')
            previous=database.get(Consent,own.consent_id)
            previous_scope,previous_stamp=previous.scope,previous.granted_at
        command.upgrade(config,'head')
        assert {'learning_preferences','personal_training_jobs','personal_trainer_heartbeats','fidelity_cases'}<=set(inspect(engine).get_table_names())
        with Session(engine) as database:
            existing=database.get(Consent,own.consent_id)
            assert existing.scope==previous_scope and existing.granted_at==previous_stamp
            training=ConsentRepository(database).grant(subject_id=own.subject_id,
                granted_by_actor_id=own.actor_id,scope=ConsentScope.MODEL_TRAINING)
            database.commit()
            assert training.scope=='MODEL_TRAINING'
            assert existing.scope=='RECORDING'
            training_id=training.consent_id
        # A blocked rollback must leave both new tables and permission intact.
        with pytest.raises(RuntimeError,match='training grants'):
            command.downgrade(config,'0020_chat_memory')
        assert 'fidelity_cases' in inspect(engine).get_table_names()
        with Session(engine) as database:
            assert database.get(Consent,training_id).scope=='MODEL_TRAINING'
    finally:engine.dispose()

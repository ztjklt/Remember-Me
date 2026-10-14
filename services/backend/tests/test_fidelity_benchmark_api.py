"""Only server-bound independent scenarios may support an agreement score."""
from datetime import timedelta
from uuid import uuid4
from app import fidelity_benchmark as benchmark
from app.access import source_basis
from app.learning_models import FidelityCase
from app.models import utcnow
from app.personal_learning import version
from app.twin_fidelity import DIMENSIONS,text_hash
from test_personal_learning_api import learning_owner,_source

def _path(fixture):
    return f'/api/v1/subjects/{fixture[0].subject_id}/twin/fidelity'

def _create(client,fixture,**changes):
    question=benchmark.QUESTION_BANK[0]
    body={'question':question['question'],'benchmark_question_id':question['question_id'],
          'cloud_consent_id':fixture[4]['CLOUD_TWIN']}
    return client.post(_path(fixture)+'/cases',headers=fixture[2],json={**body,**changes})

def _rated_rows(session,fixture,*,fixed,duplicate_reference=False,count=20):
    own=fixture[0];now=utcnow();basis=source_basis(session,own.subject_id)
    for i in range(count):
        item=benchmark.QUESTION_BANK[i]
        question=item['question'] if fixed else '同一道家人优先的问题'+'？'*(i+1)
        reference=('这是我独立的新想法，我选择先沟通，再安排。'+'！'*i if duplicate_reference else f'这是第{i}个未见情境的本人参考回答。')
        session.add(FidelityCase(case_id='fc_'+uuid4().hex,subject_id=own.subject_id,actor_id=own.actor_id,
            question=question,question_group_id=item['question_group_id'] if fixed else text_hash(question),
            locked_answer=reference,answer_id='synthetic-private-lock-'+str(i),response_type='SIMULATION',
            model_version='test-prediction-v1',person_model_version=version(session,own.subject_id),source_basis=basis,
            exposure_manifest={'verified':True,'benchmark_id':benchmark.BENCHMARK_ID,'benchmark_verified':fixed,
                'benchmark_question_id':item['question_id'] if fixed else None,'text_hashes':[],
                'source_group_ids':[],'exposed_texts':[],'locked_at':(now-timedelta(minutes=3)).isoformat()},
            human_answer=reference,ratings={d:'MATCH' if i%2==0 else 'DIFFERENT' for d in DIMENSIONS},
            human_confirmed_at=now-timedelta(minutes=2),rated_at=now-timedelta(minutes=1),created_at=now-timedelta(minutes=4)))
    session.commit()

def test_question_bank_is_owner_scoped_and_contains_distinct_server_groups(learning_owner,client):
    path=_path(learning_owner)
    assert client.get(path+'/benchmark',headers=learning_owner[3]).status_code==404
    bank=client.get(path+'/benchmark',headers=learning_owner[2]).json()
    assert len(bank['question_bank'])==60
    assert len({q['question_id'] for q in bank['question_bank']})==60
    assert len({q['question_group_id'] for q in bank['question_bank']})==60
    assert client.get(path,headers=learning_owner[2]).json()['question_bank']==bank['question_bank']
    report=client.get(path,headers=learning_owner[2]).json()
    assert report['evaluation_target']=='current_twin'
    assert report['personal_candidate_evaluation_available'] is False

def test_unknown_or_modified_bank_question_is_rejected_before_prediction(learning_owner,client,app):
    initial=len(app.state.twin_client.options)
    assert _create(client,learning_owner,benchmark_question_id='forged-group').status_code==422
    assert _create(client,learning_owner,question=benchmark.QUESTION_BANK[0]['question']+'？').status_code==422
    assert len(app.state.twin_client.options)==initial

def test_fixed_question_prediction_is_sealed_and_counts_only_after_human_rating(learning_owner,client,app,session):
    _source(client,app,session,learning_owner)
    response=_create(client,learning_owner)
    assert response.status_code==201,response.text
    case=response.json();assert case['benchmark_verified'] is True and case['ratings']=={}
    assert 'locked_answer' not in case
    path=_path(learning_owner)+'/cases/'+case['case_id'];headers=learning_owner[2]
    assert client.post(path+'/human-answer',headers=headers,json={'answer':'这是我未曾保存的情境判断。','confirmed':True}).status_code==200
    assert client.post(path+'/ratings',headers=headers,json={'ratings':{d:'MATCH' for d in DIMENSIONS}}).status_code==200
    report=client.get(_path(learning_owner),headers=headers).json()
    assert report['accepted_observation_count']==1 and report['independent_group_count']==1
    assert report['overall']['agreement_rate'] is None

def test_twenty_free_form_paraphrases_cannot_become_trusted_independent_samples(learning_owner,client,session):
    _rated_rows(session,learning_owner,fixed=False)
    report=client.get(_path(learning_owner),headers=learning_owner[2]).json()
    assert report['accepted_observation_count']==0 and report['diagnostic_case_count']==20
    assert report['overall']['agreement_rate'] is None
    assert all('NOT_FROZEN_HOLDOUT' in row['reasons'] for row in report['excluded_observations'])

def test_different_fixed_questions_with_same_reference_join_one_group_despite_punctuation(learning_owner,client,session):
    _rated_rows(session,learning_owner,fixed=True,duplicate_reference=True)
    report=client.get(_path(learning_owner),headers=learning_owner[2]).json()
    assert report['accepted_observation_count']==20
    assert report['independent_group_count']==1
    assert report['overall']['agreement_rate'] is None

def test_fixed_bank_allows_uncertain_middle_agreement_when_enough_independent_references_exist(learning_owner,client,session):
    _rated_rows(session,learning_owner,fixed=True,count=60)
    report=client.get(_path(learning_owner),headers=learning_owner[2]).json()
    assert report['independent_group_count']==60 and report['status']=='available'
    assert len(report['cases'])==60
    assert report['overall']['agreement_rate']==.5
    assert report['overall']['confidence_interval']['lower']<.5<report['overall']['confidence_interval']['upper']

def test_already_exposed_summary_reference_cannot_count_despite_punctuation(learning_owner,client,app,session):
    from sqlalchemy import select
    from app.models import MemoryItem
    source=_source(client,app,session,learning_owner)
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==source.episode_id))
    memory.content='我会先讨论，再做决定。';session.commit()
    response=_create(client,learning_owner);assert response.status_code==201,response.text
    path=_path(learning_owner)+'/cases/'+response.json()['case_id'];headers=learning_owner[2]
    assert client.post(path+'/human-answer',headers=headers,json={'answer':'我会先讨论 再做决定！','confirmed':True}).status_code==200
    assert client.post(path+'/ratings',headers=headers,json={'ratings':{d:'MATCH' for d in DIMENSIONS}}).status_code==200
    report=client.get(_path(learning_owner),headers=headers).json()
    assert report['accepted_observation_count']==0
    assert 'HUMAN_ANSWER_EXPOSED' in report['excluded_observations'][0]['reasons']

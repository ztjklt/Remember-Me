"""Separate training permission and sealed, human-rated unseen predictions."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from uuid import uuid4
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import select, func
from ..access import require_owner, require_cloud, source_basis, publication_lock, visible_episodes
from ..db import get_session
from ..errors import AppError, RequestInvalid
from ..security import current_actor
from ..models import Actor, ConsentScope, CalibrationRun, as_utc, utcnow
from ..repositories.consents import ConsentRepository
from ..learning_models import LearningPreference, PersonalTrainingJob, PersonalTrainerHeartbeat, FidelityCase
from ..personal_training import TrainingPolicy, TrainingResult, TrainingValidationError
from .. import personal_learning as learning
from ..twin_fidelity import (DIMENSIONS, ALIGNMENTS, CalibrationObservation, ExposureManifest, HumanRating,
    EvaluationContext, summarize_fidelity, text_hash)
from ..materials import effective_materials
from .. import fidelity_benchmark as benchmark
from .twin import TwinQuestion, answer_question, SourceChanged

router=APIRouter(tags=['personal-learning'])
ROOT='/api/v1/subjects/{subject_id}/twin'

class TrainerUnauthorized(AppError):
    code='AUTH_REQUIRED';http_status=401
class LearningNotReady(AppError):
    code='LEARNING_NOT_READY';http_status=409
class Body(BaseModel):
    model_config=ConfigDict(extra='forbid')
class PreferenceInput(Body):
    enabled:StrictBool
    training_consent_id:str|None=None
    accepted_policy:str=''
class WorkerInput(Body):
    worker_id:str=Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')
    base_model:str=Field(min_length=1,max_length=128)
    available:StrictBool
class LeaseInput(Body):
    worker_id:str=Field(min_length=1,max_length=64)
    lease_token:str=Field(min_length=20,max_length=128)
class ResultInput(LeaseInput):
    result:TrainingResult
class CaseInput(Body):
    question:str=Field(min_length=1,max_length=1000)
    cloud_consent_id:str=Field(min_length=1,max_length=64)
    benchmark_question_id:str|None=Field(default=None,min_length=1,max_length=64)
class HumanInput(Body):
    answer:str=Field(min_length=1,max_length=8000)
    confirmed:StrictBool
    @field_validator("confirmed")
    @classmethod
    def confirmed_true(cls,value):
        if value is not True:raise ValueError("Explicit owner confirmation required")
        return value
class RatingInput(Body):
    ratings:dict[str,str]

def job_view(job):
    if job is None:return None
    return {'job_id':job.job_id,'status':job.status,'base_model':job.base_model,'counts':job.counts,
        'result':job.result,'created_at':job.created_at.isoformat(),'updated_at':job.updated_at.isoformat(),
        'activation_allowed':False}

def available_training_consent(session,subject,actor,pref):
    """Expose an existing revocable grant, independently of the training switch.

    Discovery never changes the saved preference or enables a job. Prefer its
    bound grant, then recover another still-active owner/subject training grant.
    """
    repository=ConsentRepository(session)
    identifiers=([pref.consent_id] if pref.consent_id else [])+[grant.consent_id for grant in
        reversed(repository.list_for_actor(subject,actor_id=actor,scope=ConsentScope.MODEL_TRAINING))]
    for identifier in dict.fromkeys(identifiers):
        try:
            repository.require_active(identifier,subject_id=subject,actor_id=actor,scope=ConsentScope.MODEL_TRAINING)
        except AppError:continue
        return identifier
    return None

def learning_view(subject,actor,request,session):
    pref=learning.preference(session,subject,actor.actor_id)
    issue=None
    try:plan,job=learning.current_job(session,pref,request.app.state.settings.personal_training_base_model)
    except TrainingValidationError as exc:
        plan,job,issue=None,None,str(exc)
    active=learning.authorized(session,pref)
    trainer=learning.worker_available(session,request.app.state.settings.personal_training_base_model)
    status='disabled' if not active else 'ineligible_data' if issue else 'insufficient_data' if plan.status!='ready' else 'trainer_offline' if not trainer and (job is None or job.status=='queued') else job.status if job else 'queued'
    return {'enabled':active,'policy':learning.POLICY,'notice':learning.POLICY_NOTICE,'status':status,
        'trainer_available':trainer,'training_consent_id':available_training_consent(session,subject,actor.actor_id,pref),
        'base_model':request.app.state.settings.personal_training_base_model,
        'dataset':{'examples':len(plan.train)+len(plan.validation)+len(plan.test),'source_groups':plan.source_group_count,
            'train':len(plan.train),'validation':len(plan.validation),'test':len(plan.test),'missing':list(plan.missing)} if plan else
            {'examples':0,'source_groups':0,'train':0,'validation':0,'test':0,'missing':[issue]},
        'requirements':TrainingPolicy().model_dump(exclude={'seed'}),'job':job_view(job),'activation_allowed':False}

@router.get(ROOT+'/learning')
def read_learning(subject_id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    # This read can enqueue a job; use the same creation boundary as claims
    # and preference writes so parallel refreshes cannot duplicate candidates.
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    result=learning_view(subject_id,actor,request,session);session.commit();return result

@router.put(ROOT+'/learning')
def configure_learning(subject_id:str,body:PreferenceInput,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    pref=learning.preference(session,subject_id,actor.actor_id)
    if body.enabled:
        if body.accepted_policy!=learning.POLICY or not body.training_consent_id:raise RequestInvalid('请先单独确认个人模型训练用途。')
        ConsentRepository(session).require_active(body.training_consent_id,subject_id=subject_id,actor_id=actor.actor_id,scope=ConsentScope.MODEL_TRAINING)
        pref.enabled=True;pref.consent_id=body.training_consent_id
    else:
        pref.enabled=False;learning.invalidate_jobs(session,subject_id,actor.actor_id)
    pref.updated_at=utcnow();session.flush()
    result=learning_view(subject_id,actor,request,session);session.commit();return result

def trainer(request):
    expected=request.app.state.settings.personal_trainer_secret.get_secret_value()
    supplied=request.headers.get('X-Personal-Trainer-Secret','')
    if len(expected)<32 or not hmac.compare_digest(expected,supplied):raise TrainerUnauthorized('训练器身份未通过验证。')

def check_job(session,job_id,body):
    job=session.get(PersonalTrainingJob,job_id)
    if job is None or job.worker_id!=body.worker_id or not job.lease_token_hash or not hmac.compare_digest(job.lease_token_hash,hashlib.sha256(body.lease_token.encode()).hexdigest()):
        raise TrainerUnauthorized('训练任务或租约无效。')
    publication_lock(session,job.subject_id)
    pref=learning.preference(session,job.subject_id,job.actor_id)
    if not learning.authorized(session,pref) or job.consent_id!=pref.consent_id:
        job.status='revoked';job.lease_token_hash=None;session.commit();raise LearningNotReady('训练授权已撤销。')
    if job.status!='running':raise LearningNotReady('训练任务已结束。')
    if job.source_basis!=source_basis(session,job.subject_id) or job.person_model_version!=learning.version(session,job.subject_id):
        job.status='stale';job.lease_token_hash=None;session.commit();raise SourceChanged('训练资料或人物版本已变化。')
    if not job.lease_expires_at or as_utc(job.lease_expires_at)<utcnow():
        job.status='failed';job.result={'reason':'TRAINER_LEASE_EXPIRED'};job.updated_at=utcnow();job.lease_token_hash=None;session.commit();raise LearningNotReady('训练租约已过期。')
    return job

@router.post('/internal/personal-learning/claim')
def claim(body:WorkerInput,request:Request,session=Depends(get_session)):
    trainer(request)
    if body.base_model!=request.app.state.settings.personal_training_base_model:raise RequestInvalid('训练器模型与当前配置不一致。')
    heartbeat=session.get(PersonalTrainerHeartbeat,body.worker_id)
    if heartbeat is None:heartbeat=PersonalTrainerHeartbeat(worker_id=body.worker_id,base_model=body.base_model);session.add(heartbeat)
    heartbeat.available=body.available;heartbeat.seen_at=utcnow();heartbeat.base_model=body.base_model
    # publication_lock starts a fresh transaction. Persist this independent
    # liveness update before iterating preferences and acquiring those locks.
    session.commit()
    purge=[j.job_id for j in session.scalars(select(PersonalTrainingJob).where(PersonalTrainingJob.worker_id==body.worker_id,PersonalTrainingJob.status.in_(['stale','revoked'])))]
    if not body.available:session.commit();return {'job':None,'purge_job_ids':purge}
    for pref in session.scalars(select(LearningPreference).where(LearningPreference.enabled.is_(True))):
        if not learning.authorized(session,pref):
            learning.invalidate_jobs(session,pref.subject_id,pref.actor_id);session.commit();continue
        publication_lock(session,pref.subject_id)
        # The lock refreshes the transaction and expires the pre-lock snapshot.
        # Recheck permission before exporting a queued task's private plan.
        if not learning.authorized(session,pref):
            learning.invalidate_jobs(session,pref.subject_id,pref.actor_id);session.commit();continue
        try:plan,job=learning.current_job(session,pref,body.base_model)
        except TrainingValidationError:session.commit();continue
        if job is None or job.status!='queued':session.commit();continue
        job.status='running';job.worker_id=body.worker_id;token=secrets.token_urlsafe(32)
        job.lease_token_hash=hashlib.sha256(token.encode()).hexdigest();job.lease_expires_at=utcnow()+timedelta(seconds=60);job.updated_at=utcnow()
        session.commit()
        return {'job':{'job_id':job.job_id,'lease_token':token,'base_model':body.base_model,
            'plan':plan.model_dump(),'policy':TrainingPolicy().model_dump()},'purge_job_ids':purge}
    session.commit();return {'job':None,'purge_job_ids':purge}

@router.post('/internal/personal-learning/jobs/{job_id}/heartbeat')
def heartbeat(job_id:str,body:LeaseInput,request:Request,session=Depends(get_session)):
    trainer(request);job=check_job(session,job_id,body)
    job.lease_expires_at=utcnow()+timedelta(seconds=60);job.updated_at=utcnow()
    worker=session.get(PersonalTrainerHeartbeat,body.worker_id)
    if worker:worker.seen_at=utcnow()
    session.commit();return {'authorized':True}

@router.post('/internal/personal-learning/jobs/{job_id}/result')
def result(job_id:str,body:ResultInput,request:Request,session=Depends(get_session)):
    trainer(request);r=body.result
    previous=session.get(PersonalTrainingJob,job_id)
    if previous and previous.status=='awaiting_validation' and previous.worker_id==body.worker_id and previous.lease_token_hash and hmac.compare_digest(previous.lease_token_hash,hashlib.sha256(body.lease_token.encode()).hexdigest()):
        publication_lock(session,previous.subject_id)
        pref=learning.preference(session,previous.subject_id,previous.actor_id)
        if learning.authorized(session,pref) and previous.source_basis==source_basis(session,previous.subject_id) and previous.result==r.model_dump():
            return {'status':previous.status,'activation_allowed':False}
        raise SourceChanged('结果已变化或训练许可已撤销。')
    job=check_job(session,job_id,body)
    if (r.subject_id,r.person_model_version,r.source_basis,r.dataset_sha256)!=(job.subject_id,str(job.person_model_version),job.source_basis,job.dataset_sha256):
        raise RequestInvalid('训练结果与原任务不一致。')
    if [r.train_count,r.validation_count,r.test_count]!=[job.counts[k] for k in ['train','validation','test']]:raise RequestInvalid('训练结果的数据划分不一致。')
    if r.status=='trained' and (r.metrics is None or not r.adapter_sha256):raise RequestInvalid('缺少真实训练与适配器证据。')
    # check_job has just verified current authorization and sources. A local
    # revoked result in that state means the worker lost its authorization
    # transport, rather than the owner withdrawing permission.
    job.status='awaiting_validation' if r.status=='trained' else 'failed' if r.status=='revoked' else r.status
    job.result=r.model_dump()
    if r.status!='trained':job.lease_token_hash=None
    job.updated_at=utcnow();session.commit()
    return {'status':job.status,'activation_allowed':False}

def case_for(session,subject,actor,case_id):
    require_owner(session,subject,actor)
    case=session.get(FidelityCase,case_id)
    if case is None or (case.subject_id,case.actor_id)!=(subject,actor):raise LearningNotReady('验证题不存在。')
    if case.source_basis!=source_basis(session,subject):raise SourceChanged('验证题依据已变化，请用新问题重新验证。')
    return case

def case_view(case):
    status='rated' if case.rated_at else 'awaiting_rating' if case.human_confirmed_at else 'awaiting_human'
    result={'case_id':case.case_id,'question':case.question,'status':status,'response_type':case.response_type,'human_answer':case.human_answer,
        'ratings':case.ratings or {},'created_at':case.created_at.isoformat(),
        'benchmark_question_id':case.exposure_manifest.get('benchmark_question_id'),
        'benchmark_verified':case.exposure_manifest.get('benchmark_verified',False)}
    if case.human_confirmed_at:result['locked_answer']=case.locked_answer
    return result

@router.post(ROOT+'/fidelity/cases',status_code=201)
def create_case(subject_id:str,body:CaseInput,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id);require_cloud(session,subject_id,actor.actor_id,body.cloud_consent_id)
    fixed=benchmark.BY_ID.get(body.benchmark_question_id) if body.benchmark_question_id else None
    if body.benchmark_question_id and (fixed is None or body.question.strip()!=fixed['question']):
        raise RequestInvalid('可信验证题必须与服务端题目编号和原题一致；自填问题可不带编号作为诊断。')
    frozen=utcnow();basis=source_basis(session,subject_id)
    materials=effective_materials(session,subject_id,visible_episodes(session,subject_id,actor.actor_id,cloud=True),enforce_budget=False)
    exposed=[e['excerpt'] for m in materials for e in m['evidence'] if e.get('excerpt')]
    exposed.extend(m['statement'] for m in materials if m.get('statement'))
    from ..profiles import approved_traits
    from ..narrative import visible_records
    for trait in approved_traits(session,subject_id):
        exposed.extend([trait.statement,trait.context or ''])
    exposed.extend(str(r.get('text','')) for r in visible_records(session,subject_id,actor.actor_id) if r.get('status')=='confirmed')
    hashes=[text_hash(x) for x in exposed if x]
    basis=source_basis(session,subject_id)
    # No chat history, no sealed human responses, and no publicly saved answer.
    answer=answer_question(subject_id,TwinQuestion(question=body.question,cloud_consent_id=body.cloud_consent_id),
        request,actor,session,chat_history_scope='conversation',persist_answer=False)
    publication_lock(session,subject_id)
    if source_basis(session,subject_id)!=basis:raise SourceChanged('验证过程中资料已变化。')
    if answer['response_type']!='SIMULATION':raise LearningNotReady('这道题没有形成可验证的预测，请提出录音未直接回答的新情境问题。')
    locked=answer.get('expression',{});locked_text=(locked.get('text') if locked and locked.get('status')=='available' else answer['answer'])
    case=FidelityCase(case_id='fc_'+uuid4().hex,subject_id=subject_id,actor_id=actor.actor_id,question=body.question.strip(),
        question_group_id=fixed['question_group_id'] if fixed else text_hash(benchmark.normalized_text(body.question)),locked_answer=locked_text,
        answer_id=answer['answer_id'],response_type=answer['response_type'],model_version=answer['model_version'],
        person_model_version=answer['person_model_version'],source_basis=basis,created_at=frozen,
        exposure_manifest={'verified':True,'benchmark_id':benchmark.BENCHMARK_ID,'benchmark_verified':fixed is not None,
            'evaluation_release_id':request.app.state.settings.release_id,
            'benchmark_question_id':body.benchmark_question_id,'text_hashes':hashes,'source_group_ids':list({e['episode_id'] for m in materials for e in m['evidence']}),
            'question_group_ids':[],'exposed_texts':exposed,'locked_at':answer['created_at']})
    session.add(case);session.commit();return case_view(case)

@router.get(ROOT+'/fidelity/cases/{case_id}')
def read_case(subject_id:str,case_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    return case_view(case_for(session,subject_id,actor.actor_id,case_id))

@router.post(ROOT+'/fidelity/cases/{case_id}/human-answer')
def human_answer(subject_id:str,case_id:str,body:HumanInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);case=case_for(session,subject_id,actor.actor_id,case_id)
    if not body.confirmed or not body.answer.strip():raise RequestInvalid('请核对并确认这确实是本人的回答。')
    if case.human_confirmed_at:
        if body.answer!=case.human_answer:raise LearningNotReady('已封存的本人验证回答不能改写，请用新问题验证。')
    else:case.human_answer=body.answer;case.human_confirmed_at=utcnow()
    session.commit();return case_view(case)

@router.post(ROOT+'/fidelity/cases/{case_id}/ratings')
def rate_case(subject_id:str,case_id:str,body:RatingInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);case=case_for(session,subject_id,actor.actor_id,case_id)
    if not case.human_confirmed_at:raise LearningNotReady('请先核对本人真实回答，再查看和评价锁定预测。')
    if set(body.ratings)!=set(DIMENSIONS) or any(x not in ALIGNMENTS for x in body.ratings.values()):raise RequestInvalid('请分别评价五个维度；未谈到的选未观察。')
    if case.rated_at and case.ratings!=body.ratings:raise LearningNotReady('已保存的评审不能改写，请创建新验证题。')
    case.ratings=body.ratings;case.rated_at=case.rated_at or utcnow();session.commit();return case_view(case)

@router.get(ROOT+'/fidelity')
def fidelity(subject_id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id);basis=source_basis(session,subject_id)
    cases=list(session.scalars(select(FidelityCase).where(FidelityCase.subject_id==subject_id,FidelityCase.actor_id==actor.actor_id).order_by(FidelityCase.created_at.desc())))
    release=request.app.state.settings.release_id
    current=next((c for c in cases if c.source_basis==basis and c.exposure_manifest.get('evaluation_release_id')==release),None)
    model=current.model_version if current else 'not_evaluated';pm=str(learning.version(session,subject_id));observations=[]
    for c in cases:
        if not c.rated_at or not c.human_confirmed_at:continue
        manifest=c.exposure_manifest
        prior_hashes=list(manifest['text_hashes'])
        reference=benchmark.normalized_text(c.human_answer)
        if not reference or any(reference in benchmark.normalized_text(text) for text in manifest.get('exposed_texts',[])):
            prior_hashes.append(text_hash(c.human_answer))
        fixed=benchmark.BY_ID.get(manifest.get('benchmark_question_id'))
        verified=manifest.get('benchmark_verified') is True and manifest.get('benchmark_id')==benchmark.BENCHMARK_ID and fixed is not None and c.question==fixed['question'] and c.question_group_id==fixed['question_group_id'] and manifest.get('evaluation_release_id')==release
        observations.append(CalibrationObservation(observation_id=c.case_id,benchmark_id=benchmark.BENCHMARK_ID,subject_id=subject_id,actor_id=actor.actor_id,
            question_group_id=c.question_group_id,holdout_source_group_ids=(c.case_id,'human-reference:'+text_hash(benchmark.normalized_text(c.human_answer))),question=c.question,locked_answer=c.locked_answer,human_answer=c.human_answer,
            model_version=c.model_version,person_model_version=str(c.person_model_version),source_basis=c.source_basis,
            benchmark_frozen_at=as_utc(c.created_at),locked_at=as_utc(__import__('datetime').datetime.fromisoformat(manifest['locked_at'])),
            human_answered_at=as_utc(c.human_confirmed_at),rated_at=as_utc(c.rated_at),ratings=tuple(HumanRating(dimension=d,alignment=a,rater_actor_id=actor.actor_id) for d,a in c.ratings.items()),
            held_out=verified,human_answer_confirmed=True,human_answer_source_type='SUBJECT',locked_response_type=c.response_type,
            exposure=ExposureManifest(verified=manifest['verified'],source_group_ids=tuple(manifest['source_group_ids']),text_hashes=tuple(prior_hashes))))
    diagnostic=session.scalar(select(func.count()).select_from(CalibrationRun).where(CalibrationRun.subject_id==subject_id,CalibrationRun.actor_id==actor.actor_id,CalibrationRun.status=='complete'))
    report=summarize_fidelity(observations,EvaluationContext(subject_id=subject_id,actor_id=actor.actor_id,benchmark_id=benchmark.BENCHMARK_ID,
        model_version=model,person_model_version=pm,source_basis=basis,training_manifest_verified=True),diagnostic_calibration_count=diagnostic)
    report['cases']=[case_view(c) for c in cases if c.source_basis==basis][:200]
    report.update(benchmark.metadata())
    report['evaluation_target']='current_twin'
    report['evaluation_release_id']=release
    report['personal_candidate_evaluation_available']=False
    report['diagnostic_case_count']=sum(not c.exposure_manifest.get('benchmark_verified',False) for c in cases)
    return report

@router.get(ROOT+'/fidelity/benchmark')
def read_benchmark(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    return benchmark.metadata()

"""Automatic eligibility and immutable owner-scoped training tasks."""
import hashlib
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from .access import require_owner, source_basis, visible_episodes
from .materials import effective_materials
from .models import CalibrationRun, ConsentScope, Episode, ModelRevision, as_utc, utcnow
from .repositories.consents import ConsentRepository
from .learning_models import LearningPreference, PersonalTrainingJob, PersonalTrainerHeartbeat
from .personal_training import TrainingExample, TrainingPolicy, prepare_dataset, TrainingValidationError

POLICY='personal-local-lora-v1'
POLICY_NOTICE='现有服务会将本人已核对的文字发送到这台 Mac 的本地 Qwen 训练器，仅在 Mac 在线时训练，不新增云端 GPU 服务。训练样本与独立验证分开，不使用孪生生成的回答作为本人目标。完成的是候选模型，手机当前模型仍需验证后再决定切换。可关闭或撤销，旧训练结果将停用并清理派生资料。'
RETRYABLE_FAILURES={'TRAINER_LEASE_EXPIRED','authorization_or_sources_changed'}
MAX_RECOVERABLE_FAILURES=3
RETRY_BACKOFF_SECONDS=30

def version(session,subject):
    row=session.get(ModelRevision,subject)
    return row.version if row else 0

def preference(session,subject,actor):
    row=session.get(LearningPreference,(subject,actor))
    if row is None:
        row=LearningPreference(subject_id=subject,actor_id=actor,enabled=False)
        session.add(row);session.flush()
    return row

def authorized(session,pref):
    if not pref.enabled or not pref.consent_id:return False
    try:
        require_owner(session,pref.subject_id,pref.actor_id)
        ConsentRepository(session).require_active(pref.consent_id,subject_id=pref.subject_id,actor_id=pref.actor_id,scope=ConsentScope.MODEL_TRAINING)
        return True
    except Exception:return False

def examples(session,subject,actor):
    require_owner(session,subject,actor)
    ids=visible_episodes(session,subject,actor)
    episodes={e.episode_id:e for e in session.scalars(select(Episode).where(Episode.subject_id==subject,Episode.actor_id==actor,Episode.status=='ready',Episode.transcript_reviewed_at.is_not(None),Episode.transcript_reviewed_by==actor))}
    verified=ids&episodes.keys()
    rows=effective_materials(session,subject,verified,enforce_budget=False)
    questions={c.human_episode_id:c.question for c in session.scalars(select(CalibrationRun).where(CalibrationRun.subject_id==subject,CalibrationRun.actor_id==actor,CalibrationRun.status=='complete'))}
    result=[];seen=set()
    for row in rows:
        for evidence in row['evidence']:
            text=evidence.get('excerpt','');episode=evidence.get('episode_id')
            kind=evidence.get('source_type')
            if kind not in {'SUBJECT','CALIBRATION'} or episode not in episodes or not text.strip() or len(text)>8000:continue
            # Deduplicate overlap inside one original source, but preserve
            # copied targets from different sources so prepare_dataset can
            # reject train/holdout leakage rather than silently move a target.
            fingerprint=(episode,hashlib.sha256(' '.join(text.split()).casefold().encode()).hexdigest())
            if fingerprint in seen:continue
            seen.add(fingerprint)
            result.append(TrainingExample(example_id=evidence['evidence_id'],subject_id=subject,actor_id=actor,owner_actor_id=actor,
                source_group_id=episode,source_ref=evidence['evidence_id'],source_type=kind,target_origin='human',verified=True,confirmed=True,
                prompt=questions.get(episode,'请以本人视角说出这段已经核对的记忆。材料：'+text[:3000]),target=text,verified_target=text))
    return result

def dataset(session,subject,actor):
    return prepare_dataset(examples(session,subject,actor),subject_id=subject,actor_id=actor,
        person_model_version=str(version(session,subject)),source_basis=source_basis(session,subject))

def invalidate_jobs(session,subject,actor):
    for job in session.scalars(select(PersonalTrainingJob).where(PersonalTrainingJob.subject_id==subject,PersonalTrainingJob.actor_id==actor,
        PersonalTrainingJob.status.not_in(['revoked','stale']))):
        # Failed/rejected runs also retain private datasets and runtime files.
        # Their worker needs the same tombstone as a successful candidate.
        job.status='revoked';job.lease_token_hash=None;job.updated_at=utcnow()

def current_job(session,pref,base_model):
    try:
        plan=dataset(session,pref.subject_id,pref.actor_id)
    except TrainingValidationError:
        # Invalid new material must still invalidate artifacts trained on an
        # older source snapshot; callers return a safe ineligible state.
        basis=source_basis(session,pref.subject_id)
        for job in session.scalars(select(PersonalTrainingJob).where(PersonalTrainingJob.subject_id==pref.subject_id,
                PersonalTrainingJob.actor_id==pref.actor_id,PersonalTrainingJob.status.not_in(['stale','revoked']))):
            if job.source_basis!=basis:
                job.status='stale';job.lease_token_hash=None;job.updated_at=utcnow()
        raise
    jobs=list(session.scalars(select(PersonalTrainingJob).where(PersonalTrainingJob.subject_id==pref.subject_id,
        PersonalTrainingJob.actor_id==pref.actor_id).order_by(PersonalTrainingJob.created_at.desc())))
    for j in jobs:
        if j.status not in {'stale','revoked'} and j.source_basis!=plan.source_basis:
            j.status='stale';j.lease_token_hash=None;j.updated_at=utcnow()
        if j.status=='running' and j.lease_expires_at and as_utc(j.lease_expires_at)<utcnow():
            j.status='failed';j.result={'reason':'TRAINER_LEASE_EXPIRED'};j.lease_token_hash=None;j.updated_at=utcnow()
    match=next((j for j in jobs if j.dataset_sha256==plan.dataset_sha256 and j.base_model==base_model and j.status not in {'stale','revoked'}),None)
    if not authorized(session,pref):return plan,match
    if match and match.status=='failed' and (match.result or {}).get('reason') in RETRYABLE_FAILURES:
        failures=sum(j.dataset_sha256==plan.dataset_sha256 and j.base_model==base_model and j.status=='failed'
            and (j.result or {}).get('reason') in RETRYABLE_FAILURES for j in jobs)
        delay=RETRY_BACKOFF_SECONDS*(2**max(0,failures-1))
        if failures<MAX_RECOVERABLE_FAILURES and utcnow()-as_utc(match.updated_at)>=timedelta(seconds=delay):
            match=None
        # Deterministic model rejection/runtime errors are not retried forever.
    if plan.status=='ready' and match is None:
        match=PersonalTrainingJob(job_id='pt_'+uuid4().hex,subject_id=pref.subject_id,actor_id=pref.actor_id,consent_id=pref.consent_id,
            source_basis=plan.source_basis,person_model_version=version(session,pref.subject_id),dataset_sha256=plan.dataset_sha256,
            base_model=base_model,status='queued',counts={'train':len(plan.train),'validation':len(plan.validation),'test':len(plan.test),'source_groups':plan.source_group_count})
        session.add(match);session.flush()
    return plan,match

def worker_available(session,model):
    return session.scalar(select(PersonalTrainerHeartbeat.worker_id).where(PersonalTrainerHeartbeat.base_model==model,
        PersonalTrainerHeartbeat.available.is_(True),PersonalTrainerHeartbeat.seen_at>utcnow()-timedelta(seconds=90))) is not None

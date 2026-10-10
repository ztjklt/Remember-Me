"""Explicit human approval for derived understanding; no competing fact store."""
from uuid import uuid4
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from sqlalchemy import select
from ..db import get_session
from ..security import current_actor
from ..access import require_owner, require_cloud, source_basis, publication_lock, Hidden
from ..models import ProfileCandidate, ProfileRefresh, ProfileUpdate, Evidence, utcnow
from ..profiles import candidate_view
from ..retrieval import invalidate_answers
from .twin import SourceChanged
from ..profile_updates import valid_snapshot, update_view, apply_update, ProfileChanged
from ..errors import RequestInvalid

router=APIRouter(prefix='/api/v1/workbench/subjects/{subject_id}/profile-candidates',tags=['profile-candidates'])

class RefreshInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    cloud_consent_id: str


class UpdateInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    candidate_id:str=Field(min_length=1,max_length=64)
    action:Literal['ADD','SUPPORT','CONFLICT','CHANGE']
    target_candidate_id:str|None=Field(default=None,min_length=1,max_length=64)
    reason:str=Field(min_length=1,max_length=1000)
    time_text:str=Field(default='',max_length=200)

    @model_validator(mode='after')
    def relation(self):
        if (self.action=='ADD') != (self.target_candidate_id is None):
            raise ValueError('ADD 不选旧目标，其他动作必须选择旧目标。')
        if self.target_candidate_id==self.candidate_id:
            raise ValueError('新旧候选不能相同。')
        if self.action=='CHANGE' and not self.time_text:
            raise ValueError('变化需要本人提供时间说明，可为模糊时间。')
        return self


def update_inputs(session,subject,actor,candidate_id,target_id,basis):
    candidate=session.get(ProfileCandidate,candidate_id)
    if candidate is None or candidate.subject_id!=subject: raise Hidden('人物候选不存在。')
    if candidate.status!='pending' or candidate.source_basis!=basis:
        raise ProfileChanged('新候选已处理或依据已变化。')
    valid_snapshot(session,subject,actor,candidate)
    target=None
    if target_id:
        target=session.get(ProfileCandidate,target_id)
        if target is None or target.subject_id!=subject: raise Hidden('目标理解不存在。')
        if target.status!='confirmed': raise ProfileChanged('旧理解已退出当前使用，请重新选择。')
        if (target.domain,target.kind)!=(candidate.domain,candidate.kind):
            raise RequestInvalid('新旧理解的领域和种类不同，不能直接关联。')
        valid_snapshot(session,subject,actor,target,require_saved=target.source_basis!=basis)
    return candidate,target


@router.get('/updates')
def updates(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    return {'items':[update_view(r) for r in session.scalars(select(ProfileUpdate).where(
        ProfileUpdate.subject_id==subject_id).order_by(ProfileUpdate.created_at.desc()))]}


@router.post('/updates',status_code=201)
def propose_update(subject_id:str,body:UpdateInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    basis=source_basis(session,subject_id,include_profiles=False)
    update_inputs(session,subject_id,actor.actor_id,body.candidate_id,body.target_candidate_id,basis)
    # Material resolution can create stable source IDs; capture after its flush.
    full_basis=source_basis(session,subject_id)
    existing=session.scalar(select(ProfileUpdate).where(ProfileUpdate.subject_id==subject_id,
        ProfileUpdate.candidate_id==body.candidate_id,ProfileUpdate.action==body.action,
        ProfileUpdate.target_candidate_id==body.target_candidate_id,ProfileUpdate.reason==body.reason,
        ProfileUpdate.time_text==body.time_text,ProfileUpdate.base_source_version==full_basis,
        ProfileUpdate.status=='pending'))
    if existing is not None: return update_view(existing)
    row=ProfileUpdate(update_id='pu_'+uuid4().hex,subject_id=subject_id,actor_id=actor.actor_id,
        **body.model_dump(),base_source_version=full_basis,status='pending')
    session.add(row);session.commit();return update_view(row)


def decide_update(subject_id,update_id,status,request,actor,session):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=session.get(ProfileUpdate,update_id)
    if row is None or row.subject_id!=subject_id: raise Hidden('人物更新不存在。')
    if row.status==status: return update_view(row)
    if row.status!='pending': raise ProfileChanged('此更新已作决定，请重新提出建议。')
    if status=='confirmed':
        if row.base_source_version!=source_basis(session,subject_id):
            raise ProfileChanged('资料、权限或人物理解已变化，请重新核对更新。')
        basis=source_basis(session,subject_id,include_profiles=False)
        candidate,target=update_inputs(session,subject_id,actor.actor_id,row.candidate_id,row.target_candidate_id,basis)
        apply_update(session,row,candidate,target,basis,actor.actor_id)
        invalidate_answers(session,request.app.state.object_store,subject_id)
    row.status=status;row.decided_at=utcnow();session.commit()
    return update_view(row)


@router.post('/updates/{update_id}/confirm')
def confirm_update(subject_id:str,update_id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    return decide_update(subject_id,update_id,'confirmed',request,actor,session)


@router.post('/updates/{update_id}/reject')
def reject_update(subject_id:str,update_id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    return decide_update(subject_id,update_id,'rejected',request,actor,session)

@router.get('')
def candidates(subject_id:str, actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    basis=source_basis(session,subject_id,include_profiles=False)
    rows=session.scalars(select(ProfileCandidate).where(ProfileCandidate.subject_id==subject_id).order_by(ProfileCandidate.created_at.desc()))
    jobs=list(session.scalars(select(ProfileRefresh).where(ProfileRefresh.subject_id==subject_id).order_by(ProfileRefresh.created_at.desc()).limit(5)))
    items=[]
    for row in rows:
        value=candidate_view(row,basis)
        value['evidence']=[{'evidence_id':e.evidence_id,'episode_id':e.episode_id,
            'excerpt':e.excerpt,'source_type':e.source_type} for id in row.evidence_ids+row.counter_evidence_ids
            for e in [session.get(Evidence,id)] if e is not None]
        items.append(value)
    return {'items':items, 'source_version':basis,
            'jobs':[{'job_id':j.job_id,'kind':j.kind,'status':j.status,'error':j.error} for j in jobs]}

@router.post('/refresh',status_code=202)
def refresh(subject_id:str,body:RefreshInput,actor=Depends(current_actor),session=Depends(get_session)):
    return enqueue_refresh(subject_id,body,actor,session,'candidates')


@router.post('/suggest-relations',status_code=202)
def suggest_relations(subject_id:str,body:RefreshInput,actor=Depends(current_actor),session=Depends(get_session)):
    return enqueue_refresh(subject_id,body,actor,session,'relations')


def enqueue_refresh(subject_id,body,actor,session,kind):
    publication_lock(session,subject_id)
    require_owner(session,subject_id,actor.actor_id); require_cloud(session,subject_id,actor.actor_id,body.cloud_consent_id)
    row=session.scalar(select(ProfileRefresh).where(ProfileRefresh.subject_id==subject_id,ProfileRefresh.kind==kind,ProfileRefresh.status.in_(['queued','running'])))
    if row is None:
        row=ProfileRefresh(job_id='pf_'+uuid4().hex[:20], subject_id=subject_id,actor_id=actor.actor_id,
            consent_id=body.cloud_consent_id,kind=kind,status='queued');session.add(row)
    session.commit()
    return {'job_id':row.job_id,'status':row.status}

def decide(subject_id,candidate_id,status,request,actor,session):
    publication_lock(session,subject_id)
    require_owner(session,subject_id,actor.actor_id)
    row=session.get(ProfileCandidate,candidate_id)
    if row is None or row.subject_id!=subject_id: raise Hidden('人物候选不存在。')
    if row.status in {'superseded','conflicted','applied'}:
        raise ProfileChanged('这条理解属于更新历史，不能直接恢复；请重新归纳和确认。')
    if row.source_basis!=source_basis(session,subject_id,include_profiles=False):
        raise SourceChanged('依据已变化，请重新归纳；旧候选未被确认。')
    if status=='confirmed':
        if row.status=='rejected': raise ProfileChanged('已拒绝的候选需重新归纳。')
        row.evidence_snapshot=valid_snapshot(session,subject_id,actor.actor_id,row)
    row.status=status
    invalidate_answers(session,request.app.state.object_store,subject_id)
    session.commit()
    return candidate_view(row,source_basis(session,subject_id,include_profiles=False))

@router.post('/{candidate_id}/confirm')
def confirm(subject_id:str,candidate_id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    return decide(subject_id,candidate_id,'confirmed',request,actor,session)

@router.post('/{candidate_id}/reject')
def reject(subject_id:str,candidate_id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    return decide(subject_id,candidate_id,'rejected',request,actor,session)

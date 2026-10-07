"""Explicit human approval for derived understanding; no competing fact store."""
from uuid import uuid4
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from ..db import get_session
from ..security import current_actor
from ..access import require_owner, require_cloud, source_basis, publication_lock, Hidden
from ..models import ProfileCandidate, ProfileRefresh, Evidence, utcnow
from ..profiles import candidate_view
from ..retrieval import invalidate_answers
from .twin import SourceChanged

router=APIRouter(prefix='/api/v1/workbench/subjects/{subject_id}/profile-candidates',tags=['profile-candidates'])

class RefreshInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    cloud_consent_id: str

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
            'jobs':[{'job_id':j.job_id,'status':j.status,'error':j.error} for j in jobs]}

@router.post('/refresh',status_code=202)
def refresh(subject_id:str,body:RefreshInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id)
    require_owner(session,subject_id,actor.actor_id); require_cloud(session,subject_id,actor.actor_id,body.cloud_consent_id)
    row=session.scalar(select(ProfileRefresh).where(ProfileRefresh.subject_id==subject_id,ProfileRefresh.status.in_(['queued','running'])))
    if row is None:
        row=ProfileRefresh(job_id='pf_'+uuid4().hex[:20], subject_id=subject_id,actor_id=actor.actor_id,
            consent_id=body.cloud_consent_id,status='queued');session.add(row)
    session.commit()
    return {'job_id':row.job_id,'status':row.status}

def decide(subject_id,candidate_id,status,request,actor,session):
    publication_lock(session,subject_id)
    require_owner(session,subject_id,actor.actor_id)
    row=session.get(ProfileCandidate,candidate_id)
    if row is None or row.subject_id!=subject_id: raise Hidden('人物候选不存在。')
    if row.source_basis!=source_basis(session,subject_id,include_profiles=False):
        raise SourceChanged('依据已变化，请重新归纳；旧候选未被确认。')
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

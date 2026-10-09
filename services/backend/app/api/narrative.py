"""Additive mobile API. Whole-source grants still govern every projection."""
from datetime import timedelta
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select
from ..db import get_session
from ..security import current_actor
from ..access import require_owner, publication_lock, source_basis, is_owner, Hidden
from ..errors import RequestInvalid
from ..retrieval import invalidate_answers
from ..models import (NarrativeRecord,NarrativeHistory,NarrativePreference,NarrativeQuestionDecision,
    ProfileCandidate,ProfileUpdate,ProfileRefresh,QuestionRequest,utcnow,as_utc)
from ..narrative import (RecordInput,FACETS,VIEW_FACETS,material_map,valid_record,visible_records,
    record_view,validate_payload,fingerprint,create_record,audit,event_support)
from .workbench import Strict
from .twin import SourceChanged

router=APIRouter(prefix='/api/v1/workbench/subjects/{subject_id}/narrative',tags=['narrative'])
class Revision(Strict): revision:int=Field(ge=1)
class Edit(RecordInput): revision:int=Field(ge=1)
class Style(Strict): enabled:bool; revision:int=Field(ge=0)
class Suggest(Strict):
    cloud_consent_id:str
    episode_ids:list[str]=Field(default_factory=list,max_length=30)

@router.post('/suggest',status_code=202)
def suggest(subject_id:str,body:Suggest,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    from ..access import require_cloud,visible_episodes
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    require_cloud(session,subject_id,actor.actor_id,body.cloud_consent_id)
    if not set(body.episode_ids)<=visible_episodes(session,subject_id,actor.actor_id): raise Hidden('录音不存在。')
    if request.app.state.settings.ai_backend!='http': raise RequestInvalid('请先连接真实的 AI Core。')
    pending=session.scalar(select(ProfileRefresh).where(ProfileRefresh.subject_id==subject_id,ProfileRefresh.kind=='narrative',
        ProfileRefresh.status.in_(['queued','running'])))
    if pending: return dict(job_id=pending.job_id,status=pending.status)
    job=ProfileRefresh(job_id='nj_'+uuid4().hex[:20],subject_id=subject_id,actor_id=actor.actor_id,
        consent_id=body.cloud_consent_id,kind='narrative',status='queued',request_payload={'episode_ids':body.episode_ids})
    session.add(job);session.commit();return dict(job_id=job.job_id,status=job.status)

@router.get('/jobs')
def jobs(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    return {'items':[dict(job_id=j.job_id,status=j.status,error=j.error,created_at=as_utc(j.created_at).isoformat())
        for j in session.scalars(select(ProfileRefresh).where(ProfileRefresh.subject_id==subject_id,ProfileRefresh.kind=='narrative').order_by(ProfileRefresh.created_at.desc()).limit(30))]}

def owned(session,subject,actor,id,revision):
    require_owner(session,subject,actor)
    row=session.get(NarrativeRecord,id)
    if row is None or row.subject_id!=subject: raise Hidden('整理记录不存在。')
    if row.revision!=revision: raise SourceChanged('记录已变化，请刷新后再操作。')
    return row

def finish(session,request,subject,row,actor,action,sources):
    row.updated_at=utcnow();audit(session,row,actor,action)
    invalidate_answers(session,request.app.state.object_store,subject)
    session.commit();return record_view(row,sources,True)

@router.post('/records',status_code=201)
def create(subject_id:str,body:RecordInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    sources=material_map(session,subject_id,actor.actor_id)
    row=create_record(session,subject_id,actor.actor_id,body.model_dump(),sources)
    session.commit();return record_view(row,sources,True)

@router.put('/records/{id}')
def edit(subject_id:str,id:str,body:Edit,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);row=owned(session,subject_id,actor.actor_id,id,body.revision)
    sources=material_map(session,subject_id,actor.actor_id)
    data=validate_payload(body.model_dump(exclude={'revision'}),sources)
    if data['kind']!=row.kind: raise RequestInvalid('请为不同内容类型新建记录。')
    row.payload=data;row.evidence_snapshot={e:fingerprint(sources[e]) for e in data['evidence_ids']}
    row.status='pending';row.revision+=1
    return finish(session,request,subject_id,row,actor.actor_id,'edit',sources)

@router.post('/records/{id}/split',status_code=201)
def split(subject_id:str,id:str,body:Edit,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);row=owned(session,subject_id,actor.actor_id,id,body.revision)
    if row.kind!='story' or body.kind!='story': raise RequestInvalid('只能拆分故事。')
    sources=material_map(session,subject_id,actor.actor_id)
    if not valid_record(row,sources): raise SourceChanged('旧故事来源已经变化，请先重新核对。')
    moved=set(body.evidence_ids);old=set(row.payload['evidence_ids'])
    if not moved or not moved<old: raise RequestInvalid('请选择原故事的部分来源，两个故事都须保留依据。')
    new=create_record(session,subject_id,actor.actor_id,body.model_dump(exclude={'revision'}),sources)
    remaining={**row.payload,'evidence_ids':[e for e in row.payload['evidence_ids'] if e not in moved]}
    # Old wording may have relied on removed evidence: never keep its confirmation.
    remaining.update(time_text='',place_text='',aliases=[])
    row.payload=remaining;row.evidence_snapshot={e:fingerprint(sources[e]) for e in remaining['evidence_ids']}
    row.status='pending';row.revision+=1;row.updated_at=utcnow();audit(session,row,actor.actor_id,'split')
    invalidate_answers(session,request.app.state.object_store,subject_id);session.commit()
    return record_view(new,sources,True)


@router.post('/records/{id}/{action}')
def decide(subject_id:str,id:str,action:str,body:Revision,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);row=owned(session,subject_id,actor.actor_id,id,body.revision)
    sources=material_map(session,subject_id,actor.actor_id)
    if action not in {'confirm','reject','undo'}: raise Hidden('操作不存在。')
    if action=='undo':
        history=list(session.scalars(select(NarrativeHistory).where(NarrativeHistory.record_id==id).order_by(NarrativeHistory.revision.desc())))
        previous=next((h for h in history if h.payload['record']!=row.payload),None)
        if previous is None: raise RequestInvalid('没有可以恢复的旧内容。')
        data=validate_payload(previous.payload['record'],sources)
        row.payload=data;row.evidence_snapshot={e:fingerprint(sources[e]) for e in data['evidence_ids']};row.status='pending'
    elif action=='confirm':
        if row.status!='pending' or not valid_record(row,sources): raise SourceChanged('来源或审核状态已变化，请重新核对。')
        row.status='confirmed'
    else: row.status='rejected'
    row.revision+=1
    return finish(session,request,subject_id,row,actor.actor_id,action,sources)

@router.get('/records/{id}/history')
def history(subject_id:str,id:str,actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    row=session.get(NarrativeRecord,id)
    if row is None or row.subject_id!=subject_id: raise Hidden('记录不存在。')
    return {'items':[dict(revision=h.revision,action=h.action,**h.payload,created_at=as_utc(h.created_at).isoformat())
        for h in session.scalars(select(NarrativeHistory).where(NarrativeHistory.record_id==id).order_by(NarrativeHistory.revision))]}

def next_question(session,subject,sources=None):
    options=[]
    for row in session.scalars(select(ProfileUpdate).where(ProfileUpdate.subject_id==subject,ProfileUpdate.action=='CONFLICT',ProfileUpdate.status=='confirmed').order_by(ProfileUpdate.created_at)):
        target=session.get(ProfileCandidate,row.target_candidate_id)
        if target is not None and target.status=='conflicted':
            options.append(dict(id='conflict:'+row.update_id,text='这两次讲述的情境有什么不同？也可以说明后来是否改变了想法。',
                reason='有一项人物理解存在尚未解释的不同说法。',profile_update_id=row.update_id,evidence_ids=list(dict.fromkeys(target.evidence_ids))))
    for q in session.scalars(select(QuestionRequest).where(QuestionRequest.subject_id==subject,QuestionRequest.status=='pending').order_by(QuestionRequest.created_at)):
        options.append(dict(id='reader:'+q.request_id,text=q.text,reason='亲友希望你补充；问题本身不是事实。',request_id=q.request_id,evidence_ids=[]))
    # A missing time is a concrete optional gap, never a date inferred by the model.
    for row in session.scalars(select(NarrativeRecord).where(NarrativeRecord.subject_id==subject,NarrativeRecord.kind=='story',NarrativeRecord.status=='confirmed').order_by(NarrativeRecord.created_at)):
        if not row.payload.get('time_text') and (sources is None or valid_record(row,sources)):
            options.append(dict(id='story:'+row.id+':'+str(row.revision),record_id=row.id,
                text='你愿意补充“'+row.payload['title']+'”大概发生在人生哪个阶段吗？不记得也没关系。',
                reason='这段故事还没有发生时间；可以回答、稍后或跳过。',evidence_ids=row.payload['evidence_ids']))
    for option in options:
        if sources is not None and not all(e in sources for e in option.get('evidence_ids',[])): continue
        decision=session.get(NarrativeQuestionDecision,subject+':'+option['id'])
        if decision and (decision.state=='declined' or (decision.until and as_utc(decision.until)>utcnow())): continue
        return option
    return None

@router.get('')
def overview(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id)
    owner=is_owner(session,subject_id,actor.actor_id)
    sources=material_map(session,subject_id,actor.actor_id)
    rows=visible_records(session,subject_id,actor.actor_id,sources=sources)
    active=[r for r in rows if r['status']=='confirmed']
    from ..profiles import approved_traits,candidate_view
    basis=source_basis(session,subject_id,include_profiles=False)
    understanding=[]
    # Reader sees reviewed story observations, never the owner's private profile cache.
    candidates=session.scalars(select(ProfileCandidate).where(ProfileCandidate.subject_id==subject_id)) if owner else []
    for c in candidates:
        refs=c.evidence_ids+c.counter_evidence_ids
        if not all(e in sources for e in refs): continue
        view=candidate_view(c,basis)
        view.update(evidence=[sources[e] for e in c.evidence_ids],counter_evidence=[sources[e] for e in c.counter_evidence_ids],
                    independent_events=event_support(session,subject_id,c.evidence_ids,sources))
        view['label']='本人确认的情境化理解' if view['status']=='confirmed' else '待本人核对的观察'
        understanding.append(view)
    pref=session.get(NarrativePreference,subject_id)
    views=[dict(title=title,records=[r['id'] for r in active if set(r['facets'])&facets]) for title,facets in VIEW_FACETS]
    # Evidence-only fallback preserves all original material while organization is pending.
    question=next_question(session,subject_id,sources) if owner else None
    if question and question.get('evidence_ids') and not all(e in sources for e in question['evidence_ids']): question=None
    session.commit()
    return dict(subject_id=subject_id,role='owner' if owner else 'reader',records=rows,understandings=understanding,views=views,
        facets=[dict(id=k,title=v,count=sum(k in r['facets'] for r in active)) for k,v in FACETS.items()],
        source_evidence=list(sources.values()),style={'enabled':bool(pref and pref.style_enabled),'revision':pref.revision if pref else 0},
        next_question=question,
        notice='空白表示尚无已审核材料；分类数量不代表人格完整度。')

@router.put('/style')
def style(subject_id:str,body:Style,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    pref=session.get(NarrativePreference,subject_id)
    if (pref.revision if pref else 0)!=body.revision: raise SourceChanged('设置已变化，请刷新。')
    if body.enabled and not any(r['kind']=='style' and r['status']=='confirmed' for r in visible_records(session,subject_id,actor.actor_id)):
        raise RequestInvalid('请先选择并确认本人原话作为表达范例。')
    if pref is None: pref=NarrativePreference(subject_id=subject_id,style_enabled=body.enabled,revision=1);session.add(pref)
    else: pref.style_enabled=body.enabled;pref.revision+=1
    invalidate_answers(session,request.app.state.object_store,subject_id);session.commit()
    return dict(enabled=pref.style_enabled,revision=pref.revision)

class QuestionDecision(Strict):
    id:str=Field(max_length=90)
    action:Literal['snoozed','declined']

@router.post('/next-question')
def question_decision(subject_id:str,body:QuestionDecision,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    sources=material_map(session,subject_id,actor.actor_id)
    current=next_question(session,subject_id,sources)
    if not current or current['id']!=body.id: raise SourceChanged('建议问题已变化。')
    id=subject_id+':'+body.id;row=session.get(NarrativeQuestionDecision,id)
    if row is None: row=NarrativeQuestionDecision(id=id,subject_id=subject_id,state=body.action);session.add(row)
    row.state=body.action;row.until=utcnow()+timedelta(days=1) if body.action=='snoozed' else None
    session.commit();return {'next_question':next_question(session,subject_id,sources)}

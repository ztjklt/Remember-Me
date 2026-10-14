"""Optional batch review of naturally captured dialogue, without recording again."""
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from ..db import get_session
from ..models import Episode,MemoryItem,Actor,ConsentScope,utcnow,as_utc
from ..access import require_owner,Hidden,publication_lock
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from ..errors import RequestInvalid
router=APIRouter(prefix='/api/v1/subjects/{subject_id}/dialogue-materials')

def own(session,subject,identifier,actor):
    require_owner(session,subject,actor.actor_id)
    row=session.get(Episode,identifier)
    if not row or row.subject_id!=subject or row.actor_id!=actor.actor_id or (row.capture_metadata or {}).get('origin')!='natural_dialogue':raise Hidden('这段对话资料不存在。')
    return row

def view(row):return {'episode_id':row.episode_id,'text':row.transcript,'recorded_at':as_utc(row.recorded_at).isoformat(),'status':(row.capture_metadata or {}).get('review_status','pending')}
@router.get('')
def listing(subject_id:str,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    rows=session.scalars(select(Episode).where(Episode.subject_id==subject_id,Episode.actor_id==actor.actor_id,Episode.capture_metadata['origin'].as_string()=='natural_dialogue').order_by(Episode.recorded_at.desc()).limit(200))
    return {'items':[view(r) for r in rows if (r.capture_metadata or {}).get('review_status')!='deleted']}
class Confirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str|None=Field(default=None,min_length=1,max_length=1000)
@router.post('/{episode_id}/confirm')
def confirm(subject_id:str,episode_id:str,body:Confirm,request:Request,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);row=own(session,subject_id,episode_id,actor)
    ConsentRepository(session).require_active(row.recording_consent_id,subject_id=subject_id,actor_id=actor.actor_id,scope=ConsentScope.RECORDING)
    state=(row.capture_metadata or {}).get('review_status')
    if state=='deleted':raise Hidden('资料已删除。')
    text=(body.text if body.text is not None else row.transcript).strip()
    if not text:raise RequestInvalid('请留下要保存的原话。')
    state=(row.capture_metadata or {}).get('review_status')
    if state=='deleted':raise Hidden('资料已删除。')
    if state=='confirmed':
        if row.transcript!=text:raise RequestInvalid('资料已核对，请使用记忆的更正操作。')
        return view(row)
    for m in session.scalars(select(MemoryItem).where(MemoryItem.episode_id==episode_id)):
        m.review_state='superseded'
    row.transcript=text;row.transcript_reviewed_at=utcnow();row.transcript_reviewed_by=actor.actor_id
    row.capture_metadata={**row.capture_metadata,'review_status':'confirmed','review_supplement':text}
    from ..language_support import store_supplement
    from ..repositories.person_model import PersonModelRepository
    from ..retrieval import invalidate_answers
    store_supplement(session,row);PersonModelRepository(session).rebuild(subject_id,include_episode_id=row.episode_id)
    invalidate_answers(session,request.app.state.object_store,subject_id);session.commit();return view(row)
@router.delete('/{episode_id}')
def delete(subject_id:str,episode_id:str,request:Request,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);row=own(session,subject_id,episode_id,actor)
    from ..models import Evidence,MemoryAudit,MemoryEmbedding,EvidenceChunkEmbedding
    from ..dialogue_models import DialogueSample
    from ..dialogue_capture import discard
    from ..repositories.person_model import PersonModelRepository
    from ..retrieval import invalidate_answers
    metadata=row.capture_metadata or {}
    for sample in session.scalars(select(DialogueSample).where(DialogueSample.call_id==metadata.get('call_id'))):
        discard(session,request.app.state.object_store,sample)
    memories=list(session.scalars(select(MemoryItem).where(MemoryItem.episode_id==episode_id)))
    mids=[m.memory_item_id for m in memories]
    for m in memories:
        m.deleted_at=utcnow();m.review_state='superseded';m.content='';m.item_metadata={}
        embedding=session.get(MemoryEmbedding,m.memory_item_id)
        if embedding:session.delete(embedding)
    for audit in session.scalars(select(MemoryAudit).where(MemoryAudit.memory_item_id.in_(mids))):audit.previous_content=''
    for evidence in session.scalars(select(Evidence).where(Evidence.episode_id==episode_id)):evidence.excerpt=''
    for embedding in session.scalars(select(EvidenceChunkEmbedding).where(EvidenceChunkEmbedding.evidence_id.in_(select(Evidence.evidence_id).where(Evidence.episode_id==episode_id)))):session.delete(embedding)
    row.transcript='';row.stt_transcript=None;row.capture_metadata={'origin':'natural_dialogue','review_status':'deleted'}
    PersonModelRepository(session).rebuild(subject_id);invalidate_answers(session,request.app.state.object_store,subject_id);session.commit()
    return {'deleted':True}

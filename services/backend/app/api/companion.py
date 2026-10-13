"""Private companion resources with actor attribution and live source gates."""
import hashlib
import json
from typing import Annotated, Literal
from uuid import uuid4
from fastapi import APIRouter, Depends
from pydantic import Field, model_validator
from sqlalchemy import select
from ..access import Hidden, is_owner, require_owner, publication_lock, source_basis, profile_source_basis
from ..db import get_session
from ..security import current_actor
from ..errors import RequestInvalid, IdempotencyConflict
from ..models import Actor, Subject, NarrativeRecord, ProfileCandidate, utcnow, as_utc
from ..companion_models import ContributionGrant, CompanionContribution, CompanionLetter, SealedSnapshot
from ..narrative import material_map, valid_record, fingerprint
from ..profile_updates import valid_snapshot as valid_profile_snapshot, ProfileChanged
from .workbench import Strict
from .twin import SourceChanged

router = APIRouter(prefix='/api/v1/workbench/subjects/{subject_id}/companion', tags=['companion'])
spaces_router = APIRouter(prefix='/api/v1/companion', tags=['companion'])
Identifier = Annotated[str, Field(min_length=1,max_length=64)]


class Revision(Strict):
    revision: int = Field(ge=1)


class GrantInput(Strict):
    revision: int = Field(ge=0)
    enabled: bool


class NoteInput(Strict):
    idempotency_key: str = Field(min_length=1,max_length=200)
    classification: Literal['firsthand','reported','opinion']
    text: str = Field(min_length=1,max_length=5000)
    audio_id: Identifier | None = None
    narrative_ids: list[Identifier] = Field(default_factory=list,max_length=12)


class Review(Revision):
    decision: Literal['accepted','rejected','disagreement']


class Recipients(Revision):
    recipient_actor_ids: list[Identifier] = Field(max_length=30)


class LetterContent(Strict):
    recipient_actor_id: Identifier
    title: str = Field(min_length=1,max_length=120)
    text: str = Field(min_length=1,max_length=10000)
    audio_id: Identifier | None = None


class LetterInput(LetterContent):
    idempotency_key: str = Field(min_length=1,max_length=200)


class LetterEdit(LetterContent):
    revision: int = Field(ge=1)


class Publish(Revision):
    confirmed: bool


class Selection(Strict):
    narrative_ids: list[Identifier] = Field(default_factory=list,max_length=30)
    profile_candidate_ids: list[Identifier] = Field(default_factory=list,max_length=30)
    recipient_actor_ids: list[Identifier] = Field(default_factory=list,max_length=30)

    @model_validator(mode='after')
    def unique(self):
        if not 1 <= len(self.narrative_ids)+len(self.profile_candidate_ids) <= 30:
            raise ValueError('请选择1至30条已确认内容。')
        for values in (self.narrative_ids,self.profile_candidate_ids,self.recipient_actor_ids):
            if len(set(values)) != len(values): raise ValueError('重复的内容或账号。')
        return self


class SnapshotInput(Selection):
    idempotency_key: str = Field(min_length=1,max_length=200)
    source_version: str = Field(min_length=64,max_length=64)
    confirmed: bool


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def subject_exists(session,subject):
    row=session.get(Subject,subject)
    if row is None or row.owner_actor_id is None: raise Hidden('人物空间不可用。')
    return row


def recipients_valid(session,ids,owner):
    if len(set(ids))!=len(ids) or any(id==owner or session.get(Actor,id) is None for id in ids):
        raise RequestInvalid('请选择其他已有账号，不可按姓名推断接收人。')


def resource(session,model,subject,id):
    row=session.get(model,id)
    if row is None or row.subject_id!=subject: raise Hidden('内容不存在。')
    return row


def retry_create(session,model,subject,actor,body):
    row=session.scalar(select(model).where(model.subject_id==subject,model.author_actor_id==actor,
        model.idempotency_key==body.idempotency_key))
    values=body.model_dump();hashes={digest(values)}
    if not values.get('audio_id') and not values.get('narrative_ids'):
        hashes.add(digest({k:v for k,v in values.items() if k not in {'audio_id','narrative_ids'}}))
    if row and row.request_hash not in hashes:
        raise IdempotencyConflict('同一请求标识不能用于不同内容。')
    return row


def action_signature(actor,action,body):
    return {'actor_id':actor,'action':action,'revision':body.revision,'body_hash':digest(body.model_dump())}


def check_revision(row,actor,action,body):
    signature=action_signature(actor,action,body)
    if row.last_action==signature: return True
    if row.revision!=body.revision: raise SourceChanged('内容已变化，请刷新后重试。')
    return False


def changed(row,actor,action,body):
    row.last_action=action_signature(actor,action,body)
    row.revision+=1;row.updated_at=utcnow()


def metadata(row,source_type,visibility):
    return dict(id=row.id,subject_id=row.subject_id,author_actor_id=row.author_actor_id,
        source_type=source_type,revision=row.revision,status=row.status,visibility=visibility,
        created_at=as_utc(row.created_at).isoformat(),updated_at=as_utc(row.updated_at).isoformat(),
        automatic_model_use=False)


def grant_view(row):
    return dict(subject_id=row.subject_id,actor_id=row.actor_id,author_actor_id=row.author_actor_id,
        source_type='OWNER_PERMISSION',revision=row.revision,enabled=row.enabled,
        status='active' if row.enabled else 'revoked',visibility='owner_and_grantee',
        created_at=as_utc(row.created_at).isoformat(),updated_at=as_utc(row.updated_at).isoformat())


def grants_list(session,subject,actor):
    subject_exists(session,subject)
    query=select(ContributionGrant).where(ContributionGrant.subject_id==subject)
    if not is_owner(session,subject,actor): query=query.where(ContributionGrant.actor_id==actor)
    return [grant_view(row) for row in session.scalars(query.order_by(ContributionGrant.actor_id))]


@router.get('/contribution-grants')
def grants(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    return {'items':grants_list(session,subject_id,actor.actor_id)}


@router.put('/contribution-grants/{actor_id}')
def set_grant(subject_id:str,actor_id:str,body:GrantInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    recipients_valid(session,[actor_id],actor.actor_id)
    row=session.get(ContributionGrant,(subject_id,actor_id))
    if row is None:
        if body.revision!=0: raise SourceChanged('授权不存在，请刷新后重试。')
        row=ContributionGrant(subject_id=subject_id,actor_id=actor_id,author_actor_id=actor.actor_id,
            enabled=body.enabled,revision=1,last_action=action_signature(actor.actor_id,'grant',body))
        session.add(row)
    elif not check_revision(row,actor.actor_id,'grant',body):
        row.enabled=body.enabled;changed(row,actor.actor_id,'grant',body)
    session.commit();return grant_view(row)


def note_visible(row,session,actor):
    owner=is_owner(session,row.subject_id,actor)
    if row.status=='withdrawn': return owner or row.author_actor_id==actor
    return owner or row.author_actor_id==actor or (
        row.status in {'accepted','disagreement'} and actor in row.recipient_actor_ids)


def note_view(row,session,actor):
    if not note_visible(row,session,actor): raise Hidden('补记不可访问。')
    view=metadata(row,'THIRD_PARTY','named_recipients' if row.recipient_actor_ids else 'owner_and_author')
    author=session.get(Actor,row.author_actor_id)
    view.update(classification=row.classification,attribution='亲友署名补记，不是本人原话',
        author_display_name=author.display_name if author else row.author_actor_id,
        audio_id=row.audio_id if row.status!='withdrawn' else None,
        model_use_author_allowed=row.model_use_author_allowed,model_use_owner_allowed=row.model_use_owner_allowed)
    # Linking a private story must not disclose even its identifier to a recipient.
    from ..narrative import visible_records
    try: available={r['id'] for r in visible_records(session,row.subject_id,actor)}
    except Hidden: available=set()
    view['narrative_ids']=[i for i in row.narrative_ids if i in available]
    if row.status!='withdrawn': view['text']=row.text
    if is_owner(session,row.subject_id,actor) or row.author_actor_id==actor:
        view['recipient_actor_ids']=row.recipient_actor_ids
    return view


@router.post('/contributions',status_code=201)
def create_note(subject_id:str,body:NoteInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);subject_exists(session,subject_id)
    grant=session.get(ContributionGrant,(subject_id,actor.actor_id))
    if grant is None or not grant.enabled: raise Hidden('没有当前补记贡献授权。')
    row=retry_create(session,CompanionContribution,subject_id,actor.actor_id,body)
    if row is None:
        from .companion_audio import validate_attachment
        validate_attachment(session,subject_id,actor.actor_id,body.audio_id,'contribution',body.text)
        if len(set(body.narrative_ids))!=len(body.narrative_ids): raise RequestInvalid('故事关联重复。')
        from ..narrative import visible_records
        if body.narrative_ids:
            available={r['id'] for r in visible_records(session,subject_id,actor.actor_id)}
            if not set(body.narrative_ids)<=available: raise Hidden('故事不可访问。')
        row=CompanionContribution(id='cc_'+uuid4().hex[:20],subject_id=subject_id,
            author_actor_id=actor.actor_id,idempotency_key=body.idempotency_key,request_hash=digest(body.model_dump()),
            classification=body.classification,text=body.text,status='pending',recipient_actor_ids=[],
            audio_id=body.audio_id,narrative_ids=body.narrative_ids)
        session.add(row)
    session.commit();return note_view(row,session,actor.actor_id)


@router.get('/contributions')
def notes(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    subject_exists(session,subject_id)
    return {'items':notes_list(session,subject_id,actor.actor_id)}


def notes_list(session,subject,actor):
    return [note_view(row,session,actor) for row in session.scalars(select(CompanionContribution).where(
        CompanionContribution.subject_id==subject).order_by(CompanionContribution.created_at,CompanionContribution.id))
        if note_visible(row,session,actor)]


@router.get('/contributions/{id}')
def get_note(subject_id:str,id:str,actor=Depends(current_actor),session=Depends(get_session)):
    subject_exists(session,subject_id)
    return note_view(resource(session,CompanionContribution,subject_id,id),session,actor.actor_id)


@router.post('/contributions/{id}/review')
def review_note(subject_id:str,id:str,body:Review,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=resource(session,CompanionContribution,subject_id,id)
    if not check_revision(row,actor.actor_id,'review',body):
        if row.status=='withdrawn': raise SourceChanged('补记已撤回。')
        row.status=body.decision;row.recipient_actor_ids=[];row.model_use_owner_allowed=False
        changed(row,actor.actor_id,'review',body)
    session.commit();return note_view(row,session,actor.actor_id)


@router.put('/contributions/{id}/recipients')
def share_note(subject_id:str,id:str,body:Recipients,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=resource(session,CompanionContribution,subject_id,id)
    if not check_revision(row,actor.actor_id,'recipients',body):
        if row.status not in {'accepted','disagreement'}: raise SourceChanged('请先审核补记。')
        recipients_valid(session,body.recipient_actor_ids,actor.actor_id)
        row.recipient_actor_ids=body.recipient_actor_ids;changed(row,actor.actor_id,'recipients',body)
    session.commit();return note_view(row,session,actor.actor_id)


@router.post('/contributions/{id}/withdraw')
def withdraw_note(subject_id:str,id:str,body:Revision,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);subject_exists(session,subject_id)
    row=resource(session,CompanionContribution,subject_id,id)
    if row.author_actor_id!=actor.actor_id and not is_owner(session,subject_id,actor.actor_id):
        raise Hidden('不能撤回他人补记。')
    if not check_revision(row,actor.actor_id,'withdraw',body):
        if row.status=='withdrawn': raise SourceChanged('补记已撤回。')
        row.status='withdrawn';row.recipient_actor_ids=[];changed(row,actor.actor_id,'withdraw',body)
    session.commit();return note_view(row,session,actor.actor_id)


def letter_visible(row,session,actor):
    return is_owner(session,row.subject_id,actor) or (row.status=='published' and row.recipient_actor_id==actor)


def letter_view(row,session,actor):
    if not letter_visible(row,session,actor): raise Hidden('留言不可访问。')
    view=metadata(row,'SUBJECT','recipient_only' if row.status=='published' else 'owner')
    view.update(recipient_actor_id=row.recipient_actor_id,title=row.title,audio_id=row.audio_id if row.status!='revoked' else None)
    if row.status!='revoked': view['text']=row.text
    return view


def letters_list(session,subject,actor):
    return [letter_view(row,session,actor) for row in session.scalars(select(CompanionLetter).where(
        CompanionLetter.subject_id==subject).order_by(CompanionLetter.created_at,CompanionLetter.id))
        if letter_visible(row,session,actor)]


@router.post('/letters',status_code=201)
def create_letter(subject_id:str,body:LetterInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    recipients_valid(session,[body.recipient_actor_id],actor.actor_id)
    row=retry_create(session,CompanionLetter,subject_id,actor.actor_id,body)
    if row is None:
        from .companion_audio import validate_attachment
        validate_attachment(session,subject_id,actor.actor_id,body.audio_id,'letter',body.text)
        row=CompanionLetter(id='cl_'+uuid4().hex[:20],subject_id=subject_id,author_actor_id=actor.actor_id,
            request_hash=digest(body.model_dump()),status='draft',**body.model_dump())
        session.add(row)
    session.commit();return letter_view(row,session,actor.actor_id)


@router.get('/letters')
def letters(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    subject_exists(session,subject_id)
    return {'items':letters_list(session,subject_id,actor.actor_id)}


@router.get('/letters/{id}')
def get_letter(subject_id:str,id:str,actor=Depends(current_actor),session=Depends(get_session)):
    subject_exists(session,subject_id)
    return letter_view(resource(session,CompanionLetter,subject_id,id),session,actor.actor_id)


@router.put('/letters/{id}')
def edit_letter(subject_id:str,id:str,body:LetterEdit,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=resource(session,CompanionLetter,subject_id,id)
    if not check_revision(row,actor.actor_id,'edit',body):
        if row.status!='draft': raise SourceChanged('发布或撤销的留言不能改写，请新建留言。')
        recipients_valid(session,[body.recipient_actor_id],actor.actor_id)
        if body.audio_id!=row.audio_id:
            from .companion_audio import validate_attachment
            validate_attachment(session,subject_id,actor.actor_id,body.audio_id,'letter',body.text)
        elif row.audio_id:
            from ..persona_models import CompanionAudio
            if session.get(CompanionAudio,row.audio_id).reviewed_text!=body.text:
                raise RequestInvalid('这封声音留言的文字须与核对稿一致。')
        row.recipient_actor_id=body.recipient_actor_id;row.title=body.title;row.text=body.text
        row.audio_id=body.audio_id
        changed(row,actor.actor_id,'edit',body)
    session.commit();return letter_view(row,session,actor.actor_id)


class ModelUse(Revision):
    allowed: bool


@router.put('/contributions/{id}/model-use')
def note_model_use(subject_id:str,id:str,body:ModelUse,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);subject_exists(session,subject_id)
    row=resource(session,CompanionContribution,subject_id,id)
    owner=is_owner(session,subject_id,actor.actor_id);author=row.author_actor_id==actor.actor_id
    if not owner and not author: raise Hidden('不能设置这段补记的使用方式。')
    if not check_revision(row,actor.actor_id,'model-use',body):
        if row.status not in {'accepted','disagreement'}: raise SourceChanged('请先处理这段补记。')
        if author: row.model_use_author_allowed=body.allowed
        if owner: row.model_use_owner_allowed=body.allowed
        changed(row,actor.actor_id,'model-use',body)
    session.commit();return note_view(row,session,actor.actor_id)


@router.post('/letters/{id}/publish')
def publish_letter(subject_id:str,id:str,body:Publish,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    if not body.confirmed: raise RequestInvalid('请明确确认向这个账号发布留言。')
    row=resource(session,CompanionLetter,subject_id,id)
    if not check_revision(row,actor.actor_id,'publish',body):
        if row.status!='draft': raise SourceChanged('留言不再是私密草稿。')
        recipients_valid(session,[row.recipient_actor_id],actor.actor_id)
        row.status='published';changed(row,actor.actor_id,'publish',body)
    session.commit();return letter_view(row,session,actor.actor_id)


@router.post('/letters/{id}/revoke')
def revoke_letter(subject_id:str,id:str,body:Revision,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=resource(session,CompanionLetter,subject_id,id)
    if not check_revision(row,actor.actor_id,'revoke',body):
        if row.status=='revoked': raise SourceChanged('留言已撤销。')
        row.status='revoked';changed(row,actor.actor_id,'revoke',body)
    session.commit();return letter_view(row,session,actor.actor_id)


def selected_item(session,subject,kind,id,sources,basis):
    model=NarrativeRecord if kind=='narrative' else ProfileCandidate
    row=resource(session,model,subject,id)
    if kind=='narrative':
        if row.status!='confirmed' or not valid_record(row,sources):
            raise SourceChanged('故事尚未确认或来源已变化。')
        content=dict(row.payload);refs=content['evidence_ids']
        version={'revision':row.revision,'evidence_snapshot':row.evidence_snapshot}
    else:
        refs=list(dict.fromkeys(row.evidence_ids+row.counter_evidence_ids))
        if (row.status!='confirmed' or row.source_basis!=basis or not refs or
                any(e not in sources for e in refs)):
            raise SourceChanged('人物理解尚未确认或来源已变化。')
        # Profile confirmation hashes effective_materials evidence, which has no
        # narrative temporal_context. Reuse its saved-source protocol exactly;
        # contextual narrative fingerprints would reject every real confirmation.
        try:
            profile_fingerprints=valid_profile_snapshot(session,subject,
                subject_exists(session,subject).owner_actor_id,row,require_saved=True)
        except ProfileChanged as exc:
            raise SourceChanged('人物理解的原始依据已变化。') from exc
        content={k:getattr(row,k) for k in ('domain','kind','statement','context','evidence_ids',
            'counter_evidence_ids','independent_episodes')}
        version={'source_basis':row.source_basis,'evidence_snapshot':row.evidence_snapshot}
    data=dict(kind=kind,source_id=id,content=content,version=version,
        model_version=row.model_version,prompt_version=row.prompt_version,
        source_type='OWNER_REVIEWED_ORGANIZATION' if kind=='narrative' else 'OWNER_CONFIRMED_INFERENCE',
        evidence_ids=refs,episode_ids=sorted({sources[e]['episode_id'] for e in refs}),
        evidence_fingerprints=({e:fingerprint(sources[e]) for e in refs}
            if kind=='narrative' else profile_fingerprints))
    data['item_fingerprint']=digest(data)
    return data


def source_map_or_empty(session,subject,actor):
    try: return material_map(session,subject,actor)
    except Hidden: return {}


def snapshot_item_authorized(session,subject,item,actor,sources):
    if not all(e in sources for e in item['evidence_ids']): return False
    if item['kind']=='narrative':
        # Reader visibility of a linked change can differ while the original
        # evidence ID remains readable. Match the full contextual protocol used
        # by narrative.valid_record; an ID alone cannot authorize private context.
        return all(fingerprint(sources[e])==item['evidence_fingerprints'][e] for e in item['evidence_ids'])
    try:
        row=resource(session,ProfileCandidate,subject,item['source_id'])
        current=valid_profile_snapshot(session,subject,actor,row,require_saved=True)
        return current==item['evidence_fingerprints']
    except (Hidden,ProfileChanged):
        return False


def preview_selection(session,subject,actor,body):
    require_owner(session,subject,actor)
    recipients_valid(session,body.recipient_actor_ids,actor)
    sources=material_map(session,subject,actor)
    basis=profile_source_basis(session,subject)
    items=[selected_item(session,subject,kind,id,sources,basis)
        for kind,ids in [('narrative',body.narrative_ids),('profile',body.profile_candidate_ids)] for id in ids]
    for recipient in body.recipient_actor_ids:
        reader_sources=source_map_or_empty(session,subject,recipient)
        if any(not snapshot_item_authorized(session,subject,item,recipient,reader_sources) for item in items):
            raise Hidden('接收账号尚无所选内容的完整来源授权。')
    return dict(source_version=source_basis(session,subject),items=items,readonly=True,
                recipient_actor_ids=body.recipient_actor_ids)


@router.post('/snapshots/preview')
def preview_snapshot(subject_id:str,body:Selection,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id)
    view=preview_selection(session,subject_id,actor.actor_id,body)
    session.commit();return view


def snapshot_view(row,session,actor,*,sources=None,basis=None,read_sources=None):
    owner=is_owner(session,row.subject_id,actor)
    if not owner and (row.status!='sealed' or actor not in row.recipient_actor_ids):
        raise Hidden('封存版本不可访问。')
    subject=subject_exists(session,row.subject_id)
    if sources is None: sources=source_map_or_empty(session,row.subject_id,subject.owner_actor_id)
    if basis is None: basis=profile_source_basis(session,row.subject_id)
    if read_sources is None: read_sources=sources if owner else source_map_or_empty(session,row.subject_id,actor)
    projected=[]
    for item in row.items:
        try:
            live=selected_item(session,row.subject_id,item['kind'],item['source_id'],sources,basis)
            valid=row.status=='sealed' and live['item_fingerprint']==item['item_fingerprint']
        except (Hidden,SourceChanged): valid=False
        authorized=(all(e in read_sources for e in item['evidence_ids']) if owner else
            snapshot_item_authorized(session,row.subject_id,item,actor,read_sources))
        if not owner and not (valid and authorized): continue
        view={k:item[k] for k in ('kind','source_id','source_type','version','model_version','prompt_version')}
        view['source_valid']=valid;view['historical']=not valid
        if valid and authorized:
            view.update(content=item['content'],evidence_ids=item['evidence_ids'],episode_ids=item['episode_ids'])
        projected.append(view)
    if not owner and not projected: raise Hidden('所选来源已变化或授权已失效。')
    view=metadata(row,'OWNER_SEALED_SELECTION','named_recipients' if row.recipient_actor_ids else 'owner')
    view.update(readonly=True,source_version=row.source_version,items=projected,
                source_valid=bool(projected) and all(item['source_valid'] for item in projected))
    if owner: view['recipient_actor_ids']=row.recipient_actor_ids
    return view


@router.post('/snapshots',status_code=201)
def create_snapshot(subject_id:str,body:SnapshotInput,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    if not body.confirmed: raise RequestInvalid('请明确确认保存所选只读版本及接收账号。')
    row=retry_create(session,SealedSnapshot,subject_id,actor.actor_id,body)
    if row is None:
        view=preview_selection(session,subject_id,actor.actor_id,body)
        if view['source_version']!=body.source_version: raise SourceChanged('资料或授权已变化，请重新预览。')
        row=SealedSnapshot(id='ss_'+uuid4().hex[:20],subject_id=subject_id,author_actor_id=actor.actor_id,
            idempotency_key=body.idempotency_key,request_hash=digest(body.model_dump()),status='sealed',
            recipient_actor_ids=body.recipient_actor_ids,source_version=body.source_version,items=view['items'])
        session.add(row)
    session.flush();view=snapshot_view(row,session,actor.actor_id)
    session.commit();return view


def snapshots_list(session,subject,actor):
    views=[]
    subject_row=subject_exists(session,subject)
    owner=is_owner(session,subject,actor)
    sources=source_map_or_empty(session,subject,subject_row.owner_actor_id)
    read_sources=sources if owner else source_map_or_empty(session,subject,actor)
    basis=profile_source_basis(session,subject)
    for row in session.scalars(select(SealedSnapshot).where(SealedSnapshot.subject_id==subject).order_by(
            SealedSnapshot.created_at,SealedSnapshot.id)):
        if not owner and (row.status!='sealed' or actor not in row.recipient_actor_ids): continue
        try: views.append(snapshot_view(row,session,actor,sources=sources,basis=basis,read_sources=read_sources))
        except Hidden: continue
    return views


@router.get('/snapshots')
def snapshots(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id)
    view={'items':snapshots_list(session,subject_id,actor.actor_id)}
    session.commit();return view


@router.get('/snapshots/{id}')
def get_snapshot(subject_id:str,id:str,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id)
    view=snapshot_view(resource(session,SealedSnapshot,subject_id,id),session,actor.actor_id)
    session.commit();return view


@router.post('/snapshots/{id}/revoke')
def revoke_snapshot(subject_id:str,id:str,body:Revision,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=resource(session,SealedSnapshot,subject_id,id)
    if not check_revision(row,actor.actor_id,'revoke',body):
        if row.status=='revoked': raise SourceChanged('版本已撤销。')
        row.status='revoked';changed(row,actor.actor_id,'revoke',body)
    view=snapshot_view(row,session,actor.actor_id)
    session.commit();return view


@router.get('')
def overview(subject_id:str,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);subject_exists(session,subject_id)
    view=dict(subject_id=subject_id,role='owner' if is_owner(session,subject_id,actor.actor_id) else 'companion',
        contribution_grants=grants_list(session,subject_id,actor.actor_id),
        contributions=notes_list(session,subject_id,actor.actor_id),
        letters=letters_list(session,subject_id,actor.actor_id),snapshots=snapshots_list(session,subject_id,actor.actor_id))
    session.commit();return view


@spaces_router.get('/spaces')
def companion_spaces(actor=Depends(current_actor),session=Depends(get_session)):
    """Discover only explicit side access; this does not broaden StoryGrant.

    The mobile client merges these with its existing owner/story spaces. A signed
    note share is also discoverable so an explicit recipient can find that text.
    """
    publication_lock(session,'')
    aid=actor.actor_id
    ids=set(session.scalars(select(ContributionGrant.subject_id).where(
        ContributionGrant.actor_id==aid,ContributionGrant.enabled.is_(True))))
    ids.update(session.scalars(select(CompanionLetter.subject_id).where(
        CompanionLetter.recipient_actor_id==aid,CompanionLetter.status=='published')))
    ids.update(row.subject_id for row in session.scalars(select(CompanionContribution).where(
        CompanionContribution.status.in_(['accepted','disagreement']))) if aid in row.recipient_actor_ids)
    possible={row.subject_id for row in session.scalars(select(SealedSnapshot).where(
        SealedSnapshot.status=='sealed')) if aid in row.recipient_actor_ids}
    for subject in possible-ids:
        row=session.get(Subject,subject)
        if row is not None and row.owner_actor_id is not None and snapshots_list(session,subject,aid):
            ids.add(subject)
    view={'items':[dict(subject_id=row.subject_id,display_name=row.display_name,role='companion')
        for row in session.scalars(select(Subject).where(Subject.subject_id.in_(ids),
            Subject.owner_actor_id.is_not(None)).order_by(Subject.display_name,Subject.subject_id))]}
    session.commit();return view

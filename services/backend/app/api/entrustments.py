"""Recipient voice hints, secret verification and bounded evidence conversations."""
import hashlib,hmac,secrets,unicodedata
from datetime import timedelta
from uuid import uuid4
from fastapi import APIRouter,Depends,Request,Header,File,Form,UploadFile
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from ..models import Actor,ConsentScope,Episode,ModelRevision,PersonTrait,utcnow,as_utc
from ..entrust_models import Entrustment,EntrustUnlock,LegacyState,EntrustVisit
from ..voiceprint_models import VoiceIdentity
from ..db import get_session
from ..security import current_actor
from ..access import require_owner,Hidden,source_basis,publication_lock
from ..repositories.consents import ConsentRepository
from ..errors import RequestInvalid
router=APIRouter(tags=['entrusted-memory'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class PlanInput(Strict):
    recipient_actor_id:str|None=Field(default=None,min_length=1,max_length=64)
    recipient_username:str|None=Field(default=None,min_length=1,max_length=64)
    recipient_label:str=Field(min_length=1,max_length=80)
    episode_ids:list[str]=Field(min_length=1,max_length=100)
    secret:str=Field(min_length=4,max_length=200,repr=False)
    handover_consent_id:str
    voice_consent_id:str|None=None
    condition:str='immediate'
class Secret(Strict):phrase:str=Field(min_length=1,max_length=200,repr=False)
class Question(Strict):
    question:str=Field(min_length=1,max_length=1000)
    request_id:str=Field(min_length=1,max_length=64)
    previous_answer_id:str|None=None
class Steward(Strict):
    steward_actor_id:str|None=None
    steward_username:str|None=None
class Verification(Strict):
    verification_ref:str=Field(min_length=1,max_length=256)
    verified:bool

def canonical(s):
    # Preserve alphanumeric/password meaning. Normalize ASR punctuation only;
    # never fuzzy-match a failed password or ask an LLM to judge it.
    s=unicodedata.normalize('NFKC',s).strip()
    return ''.join(c for c in s if c not in '，。！？、,.!?\r\n\t ') # explained in setup

def hash_secret(value):
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(canonical(value).encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    return salt.hex()+':'+digest.hex()
def verify_secret(value,stored):
    salt,digest=stored.split(':')
    candidate=hashlib.scrypt(canonical(value).encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,dklen=32)
    return hmac.compare_digest(candidate.hex(),digest)

def plan_for(session,identifier,actor):
    row=session.get(Entrustment,identifier)
    if not row or actor not in (row.owner_actor_id,row.recipient_actor_id):raise Hidden('此入口不可用。')
    return row

def require_plan(session,row,actor):
    if row.status!='confirmed' or actor!=row.recipient_actor_id:raise Hidden('此入口不可用。')
    ConsentRepository(session).require_active(row.consent_id,subject_id=row.subject_id,actor_id=row.owner_actor_id,scope=ConsentScope.DIGITAL_HANDOVER)
    if row.condition=='after_verified_transition':
        state=session.get(LegacyState,row.subject_id)
        if not state or state.status!='active':raise Hidden('此入口不可用。')
    ids=set(session.scalars(select(Episode.episode_id).where(Episode.episode_id.in_(row.episode_ids),Episode.subject_id==row.subject_id,Episode.status=='ready',Episode.transcript.is_not(None),Episode.transcript!='')))
    if ids!=set(row.episode_ids):raise Hidden('此入口不可用。')
    return ids

def unlock_for(session,plan_id,actor,token,credential):
    row=plan_for(session,plan_id,actor);ids=require_plan(session,row,actor)
    digest=hashlib.sha256((token+'\0'+credential).encode()).hexdigest()
    unlock=session.scalar(select(EntrustUnlock).where(EntrustUnlock.plan_id==plan_id,EntrustUnlock.actor_id==actor,EntrustUnlock.token_hash==digest))
    if not unlock or unlock.revoked_at or as_utc(unlock.expires_at)<=utcnow() or unlock.plan_revision!=row.revision or unlock.source_basis!=source_basis(session,row.subject_id):raise Hidden('专属对话已锁定，请重新解锁。')
    require_visit(session,plan_id,actor,unlock.visit_id or '', 'CLOUD_TWIN')
    return row,unlock,ids

def view(row):return {'plan_id':row.plan_id,'subject_id':row.subject_id,'recipient_actor_id':row.recipient_actor_id,'recipient_label':row.recipient_label,'condition':row.condition,'status':row.status,'revision':row.revision,'episode_count':len(row.episode_ids),'voice_allowed':bool(row.voice_consent_id)}
@router.post('/api/v1/subjects/{subject_id}/entrustments')
def create(subject_id:str,body:PlanInput,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    ConsentRepository(session).require_active(body.handover_consent_id,subject_id=subject_id,actor_id=actor.actor_id,scope=ConsentScope.DIGITAL_HANDOVER)
    from ..models import Account
    if bool(body.recipient_actor_id)==bool(body.recipient_username):raise RequestInvalid('请选择一个实际亲友账号。')
    if body.recipient_username:
        account=session.get(Account,body.recipient_username.strip().lower())
        if not account:raise RequestInvalid('请核对亲友登录账号。')
        body.recipient_actor_id=account.actor_id
    if body.condition not in ('immediate','after_verified_transition') or not session.get(Actor,body.recipient_actor_id) or body.recipient_actor_id==actor.actor_id:raise RequestInvalid('请选择实际的亲友账号和开放条件。')
    ids=set(session.scalars(select(Episode.episode_id).where(Episode.episode_id.in_(body.episode_ids),Episode.subject_id==subject_id,Episode.status=='ready')))
    if len(ids)!=len(body.episode_ids):raise RequestInvalid('请选择仍然有效的完整录音或文字来源。')
    if len(canonical(body.secret))<4:raise RequestInvalid('密语至少保留4个有效字符。')
    if body.condition=='after_verified_transition' and not session.get(LegacyState,subject_id):raise RequestInvalid('请先指定数字照护人。')
    if body.voice_consent_id:ConsentRepository(session).require_active(body.voice_consent_id,subject_id=subject_id,actor_id=actor.actor_id,scope=ConsentScope.VOICE)
    row=Entrustment(voice_consent_id=body.voice_consent_id,plan_id='et_'+uuid4().hex,subject_id=subject_id,owner_actor_id=actor.actor_id,recipient_actor_id=body.recipient_actor_id,recipient_label=body.recipient_label,consent_id=body.handover_consent_id,episode_ids=sorted(ids),secret_hash=hash_secret(body.secret),condition=body.condition)
    session.add(row);session.commit();return view(row)
@router.get('/api/v1/subjects/{subject_id}/entrustments')
def own_plans(subject_id:str,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    return {'items':[view(r) for r in session.scalars(select(Entrustment).where(Entrustment.subject_id==subject_id))]}
@router.get('/api/v1/entrustments')
def received(actor:Actor=Depends(current_actor),session=Depends(get_session)):
    rows=session.scalars(select(Entrustment).where(Entrustment.recipient_actor_id==actor.actor_id,Entrustment.status=='confirmed'))
    items=[]
    for row in rows:
        try:require_plan(session,row,actor.actor_id)
        except Exception:continue
        items.append(view(row))
    return {'items':items}
@router.post('/api/v1/entrustments/{plan_id}/revoke')
def revoke(plan_id:str,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row=plan_for(session,plan_id,actor.actor_id);require_owner(session,row.subject_id,actor.actor_id)
    row.status='revoked';row.revision+=1
    for u in session.scalars(select(EntrustUnlock).where(EntrustUnlock.plan_id==plan_id)):u.revoked_at=utcnow()
    session.commit();return view(row)
@router.post('/api/v1/entrustments/{plan_id}/unlock')
def unlock(plan_id:str,body:Secret,request:Request,actor:Actor=Depends(current_actor),session=Depends(get_session),x_entrust_visit:str=Header(default='')):
    row=plan_for(session,plan_id,actor.actor_id);publication_lock(session,row.subject_id)
    row=plan_for(session,plan_id,actor.actor_id);require_plan(session,row,actor.actor_id)
    visit=require_visit(session,plan_id,actor.actor_id,x_entrust_visit,'CLOUD_TWIN')
    if row.blocked_until and as_utc(row.blocked_until)>utcnow():raise Hidden('暂时无法解锁，请稍后重试。')
    if not verify_secret(body.phrase,row.secret_hash):
        row.failures+=1
        if row.failures>=5:row.blocked_until=utcnow()+timedelta(minutes=10);row.failures=0
        session.commit();raise Hidden('未能解锁，可以再说一遍或直接输入密语。')
    token=secrets.token_urlsafe(32);row.failures=0;row.blocked_until=None
    u=EntrustUnlock(visit_id=visit.visit_id,unlock_id='eu_'+uuid4().hex,plan_id=plan_id,actor_id=actor.actor_id,token_hash=hashlib.sha256((token+'\0'+login_binding(request)).encode()).hexdigest(),plan_revision=row.revision,source_basis=source_basis(session,row.subject_id),expires_at=utcnow()+timedelta(minutes=10),answer_ids=[])
    session.add(u);session.commit();return {'unlock_token':token,'expires_at':as_utc(u.expires_at).isoformat()}
@router.delete('/api/v1/entrustments/{plan_id}/unlock')
def lock(plan_id:str,request:Request,x_entrust_unlock:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row,u,_=unlock_for(session,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request));u.revoked_at=utcnow();session.commit();return {'locked':True}

@router.post('/api/v1/entrustments/{plan_id}/questions')
def question(plan_id:str,body:Question,request:Request,x_entrust_unlock:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row,u,ids=unlock_for(session,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request))
    if body.previous_answer_id and body.previous_answer_id not in u.answer_ids:raise Hidden('此对话不可用。')
    unlock_id=u.unlock_id
    def scope(guard):
        if current_actor(request,guard).actor_id!=actor.actor_id:raise Hidden('登录已结束。')
        current,handle,allowed=unlock_for(guard,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request))
        if handle.unlock_id!=unlock_id:raise Hidden('此对话不可用。')
        return allowed
    from .twin import answer_question,TwinQuestion
    # Separate request namespace and only this unlock's parent chain. No owner
    # profile, historical chat summary or other recipient's answer is supplied.
    result=answer_question(row.subject_id,TwinQuestion(question=body.question,cloud_consent_id=row.consent_id,conversation_mode=True,previous_answer_id=body.previous_answer_id,request_id=hashlib.sha256((unlock_id+'\0'+body.request_id).encode()).hexdigest()),request,actor,session,chat_history_scope='conversation',scope_authorization=scope)
    publication_lock(session,row.subject_id);_,handle,_=unlock_for(session,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request))
    if result['answer_id'] not in handle.answer_ids:handle.answer_ids=[*handle.answer_ids,result['answer_id']][-100:]
    session.commit();return result

@router.post('/api/v1/entrustments/{plan_id}/voice-hint')
async def voice_hint(plan_id:str,request:Request,sample:UploadFile=File(...),x_entrust_visit:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row=plan_for(session,plan_id,actor.actor_id);require_plan(session,row,actor.actor_id)
    require_visit(session,plan_id,actor.actor_id,x_entrust_visit,'SPEAKER_IDENTIFICATION')
    from ..voiceprints import for_app,pcm,match
    engine=for_app(request.app);data=await sample.read(1000001)
    if not data or len(data)>1000000:raise RequestInvalid('声音为空或太长。')
    from starlette.concurrency import run_in_threadpool
    raw=await run_in_threadpool(pcm,data,sample.content_type or 'audio/mp4')
    vector=await run_in_threadpool(engine.extract,raw)
    identity=match(session,row.subject_id,vector,engine.version)
    from ..speaker_identification import _spoken_name
    label=None
    if not identity:
        from starlette.concurrency import run_in_threadpool
        def guard():
            with request.app.state.database.session() as fresh:
                if current_actor(request,fresh).actor_id!=actor.actor_id:raise Hidden('登录已结束。')
                require_visit(fresh,plan_id,actor.actor_id,x_entrust_visit,'RECORDING')
        recognized=await run_in_threadpool(request.app.state.stt_provider.transcribe_authorized,data,sample.content_type or 'audio/mp4',guard)
        label=_spoken_name(recognized.text)
        guard()
        if label==row.recipient_label:
            # A visitor reference is tied to the authenticated designated Actor;
            # it can never become the protagonist's template or grant access.
            vector=await run_in_threadpool(engine.extract,raw)
            old=session.scalar(select(VoiceIdentity).where(VoiceIdentity.subject_id==row.subject_id,VoiceIdentity.person_key=='recipient:'+actor.actor_id))
            if old is None:
                visit=require_visit(session,plan_id,actor.actor_id,x_entrust_visit,'SPEAKER_IDENTIFICATION')
                identity=VoiceIdentity(identity_id='vi_'+uuid4().hex,subject_id=row.subject_id,actor_id=actor.actor_id,person_key='recipient:'+actor.actor_id,label=label,role='contact',consent_id=visit.consent_ids['SPEAKER_IDENTIFICATION'],encoder_version=engine.version,vectors=[vector],sources=[{'kind':'entrust_visit','id':visit.visit_id}])
                session.add(identity);session.commit()
    # Only suggest the designated recipient's own label. Never list other known
    # people or return their vectors, existence or names to a visitor.
    known=bool(identity and identity.role=='contact' and identity.label==row.recipient_label)
    return {'candidate_label':row.recipient_label if known else None,'prompt':f'你是不是{row.recipient_label}？' if known else '怎么称呼你？介绍一下自己，再说密语就可以。','requires_secret':True,'ready_for_secret':label==row.recipient_label}
@router.post('/api/v1/entrustments/{plan_id}/transcribe-secret')
async def spoken_secret(plan_id:str,request:Request,sample:UploadFile=File(...),x_entrust_visit:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row=plan_for(session,plan_id,actor.actor_id);require_plan(session,row,actor.actor_id)
    data=await sample.read(1000001)
    if not data or len(data)>1000000:raise RequestInvalid('声音为空或太长。')
    require_visit(session,plan_id,actor.actor_id,x_entrust_visit,'RECORDING')
    # No Episode, speaker template, chat, question or LLM is created here.
    from starlette.concurrency import run_in_threadpool
    def guard():
        with request.app.state.database.session() as fresh:
            if current_actor(request,fresh).actor_id!=actor.actor_id:raise Hidden('登录已结束。')
            require_plan(fresh,plan_for(fresh,plan_id,actor.actor_id),actor.actor_id)
    text=await run_in_threadpool(request.app.state.stt_provider.transcribe_authorized,data,sample.content_type or 'audio/mp4',guard)
    guard();return unlock(plan_id,Secret(phrase=text.text),request,actor,session,x_entrust_visit)

@router.put('/api/v1/subjects/{subject_id}/legacy/steward')
def steward(subject_id:str,body:Steward,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    from ..models import Account
    if bool(body.steward_actor_id)==bool(body.steward_username):raise RequestInvalid('请指定一个实际照护人账号。')
    if body.steward_username:
        account=session.get(Account,body.steward_username.strip().lower())
        if not account:raise RequestInvalid('请核对照护人登录账号。')
        body.steward_actor_id=account.actor_id
    if body.steward_actor_id==actor.actor_id or not session.get(Actor,body.steward_actor_id):raise RequestInvalid('请指定实际的照护人账号。')
    row=session.get(LegacyState,subject_id)
    if row and row.status!='inactive':raise RequestInvalid('已开始核验，不能替换照护人。')
    if row:row.steward_actor_id=body.steward_actor_id
    else:session.add(LegacyState(subject_id=subject_id,steward_actor_id=body.steward_actor_id))
    session.commit();return {'status':'inactive'}
@router.post('/api/v1/subjects/{subject_id}/legacy/verify')
def legacy(subject_id:str,body:Verification,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);state=session.get(LegacyState,subject_id)
    if not state or state.steward_actor_id!=actor.actor_id:raise Hidden('此入口不可用。')
    # This is a predesignated human verification record, never automatic death
    # detection. A disputed/suspended state closes future-only plans.
    state.verification_history=[*(state.verification_history or []),{'actor_id':actor.actor_id,'verification_ref':body.verification_ref,'verified':body.verified,'at':utcnow().isoformat()}]
    state.verification_ref=body.verification_ref;state.updated_at=utcnow()
    if body.verified:
        if not state.baseline:
            revision=session.get(ModelRevision,subject_id)
            state.baseline={'person_model_version':revision.version if revision else 0,'episode_ids':list(session.scalars(select(Episode.episode_id).where(Episode.subject_id==subject_id,Episode.status=='ready'))),'activated_at':utcnow().isoformat()}
        state.status='active'
    else:state.status='suspended'
    session.commit();return {'status':state.status,'baseline_version':state.baseline.get('person_model_version')}


def require_visit(session,plan_id,actor,visit_id,scope):
    from ..models import Consent
    visit=session.get(EntrustVisit,visit_id)
    if not visit or visit.plan_id!=plan_id or visit.actor_id!=actor or visit.revoked_at or as_utc(visit.expires_at)<=utcnow():raise Hidden('本次对话已结束，请重新进入。')
    grant=session.get(Consent,visit.consent_ids.get(scope,''))
    row=plan_for(session,plan_id,actor);require_plan(session,row,actor)
    if not grant or grant.subject_id!=row.subject_id or grant.granted_by_actor_id!=actor or grant.scope!=scope or grant.status!='granted' or grant.revoked_at:raise Hidden('本次用途未确认。')
    return visit

@router.post('/api/v1/entrustments/{plan_id}/start')
def start_visit(plan_id:str,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row=plan_for(session,plan_id,actor.actor_id);require_plan(session,row,actor.actor_id)
    repo=ConsentRepository(session);scopes=['RECORDING','CLOUD_TWIN','SPEAKER_IDENTIFICATION']
    if row.voice_consent_id:scopes.append('VOICE')
    grants={scope:repo.grant(subject_id=row.subject_id,granted_by_actor_id=actor.actor_id,scope=ConsentScope(scope),evidence_ref='entrustment-start:'+plan_id).consent_id for scope in scopes}
    visit=EntrustVisit(visit_id='visit_'+uuid4().hex,plan_id=plan_id,actor_id=actor.actor_id,consent_ids=grants,expires_at=utcnow()+timedelta(minutes=30))
    session.add(visit);session.commit();return {'visit_id':visit.visit_id,'expires_at':as_utc(visit.expires_at).isoformat(),'prompt':'介绍一下自己，然后说密语，就可以进入专属记忆。'}

@router.get('/api/v1/entrustments/{plan_id}/status')
def status(plan_id:str,request:Request,x_entrust_unlock:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row,u,ids=unlock_for(session,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request))
    return {'unlocked':True,'expires_at':as_utc(u.expires_at).isoformat(),'voice_allowed':bool(row.voice_consent_id)}

@router.post('/api/v1/entrustments/{plan_id}/confirm-identity')
async def spoken_identity(plan_id:str,request:Request,sample:UploadFile=File(...),x_entrust_visit:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    require_visit(session,plan_id,actor.actor_id,x_entrust_visit,'RECORDING');row=plan_for(session,plan_id,actor.actor_id)
    data=await sample.read(1000001)
    if not data or len(data)>1000000:raise RequestInvalid('声音为空或太长。')
    from starlette.concurrency import run_in_threadpool
    def guard():
        with request.app.state.database.session() as fresh:
            if current_actor(request,fresh).actor_id!=actor.actor_id:raise Hidden('登录已结束。')
            require_visit(fresh,plan_id,actor.actor_id,x_entrust_visit,'RECORDING')
    transcript=await run_in_threadpool(request.app.state.stt_provider.transcribe_authorized,data,sample.content_type or 'audio/mp4',guard)
    from ..speaker_identification import _spoken_name
    label=_spoken_name(transcript.text)
    return {'confirmed':label==row.recipient_label or canonical(transcript.text) in ('是','是的','对','对的','没错','我是'), 'prompt':'现在请说出密语。声音确认不代替密语。'}

@router.post('/api/v1/entrustments/{plan_id}/spoken-question')
async def spoken_question(plan_id:str,request:Request,sample:UploadFile=File(...),request_id:str=Form(...),previous_answer_id:str|None=Form(default=None),x_entrust_unlock:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    row,u,_=unlock_for(session,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request));require_visit(session,plan_id,actor.actor_id,u.visit_id,'RECORDING')
    data=await sample.read(1000001)
    if not data or len(data)>1000000:raise RequestInvalid('声音为空或太长。')
    from starlette.concurrency import run_in_threadpool
    def guard():
        with request.app.state.database.session() as fresh:
            if current_actor(request,fresh).actor_id!=actor.actor_id:raise Hidden('登录已结束。')
            unlock_for(fresh,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request))
    transcript=await run_in_threadpool(request.app.state.stt_provider.transcribe_authorized,data,sample.content_type or 'audio/mp4',guard)
    guard();return question(plan_id,Question(question=transcript.text[:1000],request_id=request_id,previous_answer_id=previous_answer_id),request,x_entrust_unlock,actor,session)

@router.get('/api/v1/entrustments/{plan_id}/speech/{answer_id}')
async def speech(plan_id:str,answer_id:str,request:Request,x_entrust_unlock:str=Header(default=''),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    from ..models import TwinAnswer
    from ..realtime_access import profile_for,compatible_voice_policies
    from fastapi import Response
    import io,wave
    row,u,_=unlock_for(session,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request))
    require_visit(session,plan_id,actor.actor_id,u.visit_id,'VOICE')
    if not row.voice_consent_id:raise Hidden('此专属对话未开放本人声音。')
    ConsentRepository(session).require_active(row.voice_consent_id,subject_id=row.subject_id,actor_id=row.owner_actor_id,scope=ConsentScope.VOICE)
    profile=profile_for(session,row.subject_id,row.owner_actor_id);answer=session.get(TwinAnswer,answer_id)
    if not profile or profile.status!='ready' or profile.revoked_at or profile.consent_id!=row.voice_consent_id or profile.accepted_policy not in compatible_voice_policies(request.app.state.settings) or profile.model!=request.app.state.settings.cosyvoice_model or not answer or answer_id not in u.answer_ids or answer.actor_id!=actor.actor_id or answer.invalidated_at or answer.response_type=='UNKNOWN':raise Hidden('此声音不可用。')
    text,voice,model=answer.answer,profile.provider_voice_id,profile.model;session.commit()
    def guard():
        with request.app.state.database.session() as fresh:
            if current_actor(request,fresh).actor_id!=actor.actor_id:raise Hidden('登录已结束。')
            current,handle,_=unlock_for(fresh,plan_id,actor.actor_id,x_entrust_unlock,login_binding(request))
            require_visit(fresh,plan_id,actor.actor_id,handle.visit_id,'VOICE')
            ConsentRepository(fresh).require_active(current.voice_consent_id,subject_id=current.subject_id,actor_id=current.owner_actor_id,scope=ConsentScope.VOICE)
            p=profile_for(fresh,current.subject_id,current.owner_actor_id)
            if not p or p.revoked_at or p.status!='ready' or p.provider_voice_id!=voice:raise Hidden('此声音不可用。')
    from starlette.concurrency import run_in_threadpool
    pcm=bytearray();stream=request.app.state.realtime_provider.speech(text,voice,model)
    try:
        async for chunk in stream:
            await run_in_threadpool(guard)
            if await request.is_disconnected():raise Hidden('对话已结束。')
            if len(pcm)+len(chunk)>3000000:raise RequestInvalid('回答声音太长。')
            pcm.extend(chunk)
    finally:await stream.aclose()
    await run_in_threadpool(guard);buffer=io.BytesIO()
    with wave.open(buffer,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(bytes(pcm))
    return Response(buffer.getvalue(),media_type='audio/wav',headers={'Cache-Control':'no-store'})

@router.get('/api/v1/legacy/reviews')
def legacy_reviews(actor:Actor=Depends(current_actor),session=Depends(get_session)):
    from ..models import Subject
    return {'items':[{'subject_id':r.subject_id,'subject_label':session.get(Subject,r.subject_id).display_name,'status':r.status} for r in session.scalars(select(LegacyState).where(LegacyState.steward_actor_id==actor.actor_id))]}


def login_binding(request):
    # Bind the opaque handle to the current device login without persisting any
    # bearer secret or adding a second authentication mechanism.
    from ..tokens import hash_actor_token
    return hash_actor_token(request.headers.get('Authorization','')[7:].strip() or request.cookies.get('remember_session',''))

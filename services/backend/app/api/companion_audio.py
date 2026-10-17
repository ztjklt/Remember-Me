"""Durable dedicated recordings; contributions never enter subject Episodes."""
import hashlib
from datetime import timedelta
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from ..access import Hidden, require_owner, publication_lock
from ..db import get_session
from ..security import current_actor
from ..errors import RequestInvalid, IdempotencyConflict, AppError
from ..models import utcnow, as_utc
from ..persona_models import CompanionAudio
from ..companion_models import CompanionContribution, CompanionLetter, ContributionGrant
from .twin import SourceChanged

router=APIRouter(prefix='/api/v1/workbench/subjects/{subject_id}/companion/audio',tags=['companion-audio'])


def creation_allowed(session,subject,actor,purpose):
    if purpose=='letter': require_owner(session,subject,actor)
    else:
        grant=session.get(ContributionGrant,(subject,actor))
        if grant is None or not grant.enabled: raise Hidden('暂无补记权限。')


def attached(session,row):
    model=CompanionContribution if row.purpose=='contribution' else CompanionLetter
    return session.scalar(select(model).where(model.audio_id==row.audio_id))


def owned_audio(session,subject,actor,id):
    row=session.get(CompanionAudio,id)
    if row is None or row.subject_id!=subject or row.author_actor_id!=actor: raise Hidden('录音不存在。')
    return row


def visible_audio(session,subject,actor,id):
    from .companion import note_visible,letter_visible
    row=session.get(CompanionAudio,id)
    if row is None or row.subject_id!=subject: raise Hidden('录音不存在。')
    linked=attached(session,row)
    if linked:
        allowed=(note_visible(linked,session,actor) and linked.status!='withdrawn') if row.purpose=='contribution' else (letter_visible(linked,session,actor) and linked.status!='revoked')
    else: allowed=row.author_actor_id==actor
    if not allowed: raise Hidden('录音不可访问。')
    return row


def audio_view(row,settings):
    from ..cloud_asr import cloud_policy,CLOUD_BACKENDS
    return {k:getattr(row,k) for k in ('audio_id','purpose','revision','status','raw_transcript_text','transcript_text','reviewed_text','error','model_version')} | {
        'cloud_asr_policy':cloud_policy(settings) if settings.stt_backend in CLOUD_BACKENDS else 'local-asr',
        'created_at':as_utc(row.created_at).isoformat()}


def validate_attachment(session,subject,actor,id,purpose,text):
    if not id: return None
    row=owned_audio(session,subject,actor,id)
    if row.purpose!=purpose: raise Hidden('请选择单独为这段内容录制的声音。')
    if row.status!='confirmed': raise SourceChanged('请先核对录音文字。')
    if row.reviewed_text!=text: raise RequestInvalid('正文须与核对文字一致；另外补充请另写一条。')
    if attached(session,row): raise SourceChanged('这段录音已用于另一条内容。')
    return row


@router.post('',status_code=201)
def upload(subject_id:str,request:Request,purpose:Literal['contribution','letter']=Form(...),
           idempotency_key:str=Form(...),file:UploadFile=File(...),actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);creation_allowed(session,subject_id,actor.actor_id,purpose)
    if not idempotency_key.strip() or len(idempotency_key)>200: raise RequestInvalid('录音请求标识无效。')
    mime=(file.content_type or '').lower().split(';')[0]
    if not mime.startswith('audio/'): raise RequestInvalid('请选择音频文件。')
    audio=file.file.read(request.app.state.settings.max_upload_bytes+1)
    if not audio or len(audio)>request.app.state.settings.max_upload_bytes: raise RequestInvalid('录音为空或过大。')
    digest=hashlib.sha256(purpose.encode()+b'\0'+mime.encode()+b'\0'+audio).hexdigest()
    row=session.scalar(select(CompanionAudio).where(CompanionAudio.subject_id==subject_id,
        CompanionAudio.author_actor_id==actor.actor_id,CompanionAudio.idempotency_key==idempotency_key))
    if row:
        if row.request_hash!=digest: raise IdempotencyConflict('同一录音请求不能提交不同内容。')
    else:
        id='ca_'+uuid4().hex[:20];key=f'subjects/{subject_id}/companion/{actor.actor_id}/{id}'
        try:
            request.app.state.object_store.put(key,audio,mime)
            row=CompanionAudio(audio_id=id,subject_id=subject_id,author_actor_id=actor.actor_id,purpose=purpose,
                idempotency_key=idempotency_key,request_hash=digest,object_key=key,content_type=mime,status='saved')
            session.add(row);session.commit()
        except Exception:
            session.rollback()
            # A lost commit acknowledgement may still leave a durable row. Keep
            # its bytes so the same idempotency key can recover that successful
            # upload; delete only a new object confirmed to have no saved row.
            with request.app.state.database.session() as recovery:
                persisted=recovery.get(CompanionAudio,id)
                if persisted is None: request.app.state.object_store.delete(key)
            raise
        return audio_view(row,request.app.state.settings)
    session.commit();return audio_view(row,request.app.state.settings)


@router.get('/{id}')
def get_audio(subject_id:str,id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    return audio_view(visible_audio(session,subject_id,actor.actor_id,id),request.app.state.settings)


@router.get('/{id}/content')
def content(subject_id:str,id:str,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    row=visible_audio(session,subject_id,actor.actor_id,id)
    key,mime=row.object_key,row.content_type
    session.commit()
    data=request.app.state.object_store.get(key)
    session.expire_all();publication_lock(session,subject_id)
    current=visible_audio(session,subject_id,actor.actor_id,id)
    if current.object_key!=key: raise SourceChanged('声音已变化，请重新打开。')
    return Response(data,media_type=mime,
        headers={'Cache-Control':'private, no-store'})


class Transcribe(BaseModel):
    model_config=ConfigDict(extra='forbid')
    cloud_asr_policy:str=Field(min_length=1,max_length=300)


@router.post('/{id}/transcribe')
def transcribe(subject_id:str,id:str,body:Transcribe,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    from ..cloud_asr import CLOUD_BACKENDS,cloud_policy
    from ..stt import build_stt_provider
    from ..chinese_text import simplified_transcript
    publication_lock(session,subject_id);row=owned_audio(session,subject_id,actor.actor_id,id)
    creation_allowed(session,subject_id,actor.actor_id,row.purpose)
    if attached(session,row): raise SourceChanged('已提交的录音不能重新转写。')
    settings=request.app.state.settings
    if settings.stt_backend in CLOUD_BACKENDS and body.cloud_asr_policy!=cloud_policy(settings):
        raise RequestInvalid('请确认将这段原音交给当前语音识别服务。')
    if row.status in {'reviewing','confirmed'}: return audio_view(row,settings)
    if row.status=='transcribing' and as_utc(row.updated_at)>utcnow()-timedelta(minutes=5):
        raise SourceChanged('录音正在转文字，请稍后刷新。')
    row.status='transcribing';row.error='';row.revision+=1;row.updated_at=utcnow()
    version=row.revision;key=row.object_key;mime=row.content_type;purpose=row.purpose;actor_id=actor.actor_id
    session.commit()
    def authorize():
        with request.app.state.database.session() as guard:
            current=owned_audio(guard,subject_id,actor_id,id)
            creation_allowed(guard,subject_id,actor_id,purpose)
            if current.revision!=version or attached(guard,current): raise SourceChanged('录音状态已变化。')
    try:
        provider=build_stt_provider(settings) if settings.stt_backend in CLOUD_BACKENDS else request.app.state.stt_provider
        audio=request.app.state.object_store.get(key)
        authorize()
        transcript=(provider.transcribe_authorized(audio,mime,authorize) if hasattr(provider,'transcribe_authorized')
                    else provider.transcribe(audio,mime))
        publication_lock(session,subject_id);row=owned_audio(session,subject_id,actor_id,id)
        creation_allowed(session,subject_id,actor_id,purpose)
        if row.revision!=version: raise SourceChanged('录音状态已变化。')
        row.raw_transcript_text=transcript.text
        row.transcript_text=simplified_transcript(transcript.text);row.model_version=transcript.model_version
        row.status='reviewing';row.revision+=1;row.updated_at=utcnow();session.commit()
        return audio_view(row,settings)
    except Exception as exc:
        session.rollback();row=session.get(CompanionAudio,id)
        if row and row.revision==version:
            row.status='failed';row.error='转文字未完成，原音已保留。';row.revision+=1;row.updated_at=utcnow();session.commit()
        if isinstance(exc,AppError): raise
        raise RequestInvalid('转文字未完成，原音已保留，可以重试。') from exc


class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    text:str=Field(min_length=1,max_length=10000)


@router.put('/{id}/review')
def review(subject_id:str,id:str,body:Review,request:Request,actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);row=owned_audio(session,subject_id,actor.actor_id,id)
    creation_allowed(session,subject_id,actor.actor_id,row.purpose)
    if attached(session,row): raise SourceChanged('已提交的录音请通过新的补记更正。')
    if row.status=='confirmed' and row.reviewed_text==body.text and row.revision==body.revision+1:
        return audio_view(row,request.app.state.settings)
    if row.revision!=body.revision or row.status not in {'reviewing','confirmed'}:
        raise SourceChanged('录音状态已变化，请刷新后核对。')
    if not body.text.strip(): raise RequestInvalid('请填写核对文字。')
    row.reviewed_text=body.text;row.status='confirmed';row.revision+=1;row.updated_at=utcnow()
    session.commit();return audio_view(row,request.app.state.settings)

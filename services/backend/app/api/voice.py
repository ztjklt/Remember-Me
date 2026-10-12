"""Separately authorized voice profiles and current saved-answer playback."""
from __future__ import annotations
import hashlib
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..access import is_owner, publication_lock, require_owner, visible_episodes
from ..db import get_session
from ..errors import AppError
from ..models import Actor, ConsentScope, Subject, TwinAnswer, VoiceAsset, VoiceProfile, utcnow
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from ..voice_client import VoiceSampleInvalid, VoiceUnavailable, load_synthetic_reference
from ..voice_models import SyntheticVoiceProfile, VoiceRecipientGrant
from .twin import require_subject

router = APIRouter(prefix='/api/v1/subjects/{subject_id}', tags=['voice'])

class VoiceNotFound(AppError):
    code = 'NOT_FOUND'
    http_status = 404

class VoiceFailed(AppError):
    code = 'VOICE_UNAVAILABLE'
    http_status = 503

class VoiceInvalid(AppError):
    code = 'VOICE_SAMPLE_INVALID'
    http_status = 422

class SyntheticEnrollment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preset: Literal['a01']
    voice_consent_id: str = Field(min_length=1, max_length=64)

class VoiceGrantInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool

class SavedSpeechInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

def _profile(session, subject_id, actor_id):
    return session.scalar(select(VoiceProfile).where(
        VoiceProfile.subject_id == subject_id, VoiceProfile.actor_id == actor_id,
        VoiceProfile.revoked_at.is_(None)).order_by(VoiceProfile.created_at.desc()))

def _retire_profile(session, profile):
    """Stage database changes; replacement must keep old bytes until commit."""
    keys = []
    for asset in list(session.scalars(select(VoiceAsset).where(VoiceAsset.profile_id == profile.profile_id))):
        keys.append(asset.object_key)
        session.delete(asset)
    if profile.sample_object_key:
        keys.append(profile.sample_object_key)
    profile.sample_object_key = profile.sample_transcript = profile.model_version = ''
    profile.revoked_at = utcnow()
    return keys

def discard_profile(session, store, profile):
    for key in _retire_profile(session, profile):
        store.delete(key)

def _recover_voice_write(request, model, identifier, key, retired_keys=()):
    """A failed commit acknowledgement does not prove the write rolled back."""
    try:
        with request.app.state.database.session() as recovery:
            persisted = recovery.get(model, identifier) is not None
    except Exception:
        # If confirmation itself is unavailable, preserve both generations.
        # Never turn an uncertain database outcome into irreversible audio loss.
        return
    store = request.app.state.object_store
    for obsolete in retired_keys if persisted else (key,):
        store.delete(obsolete)

def _discard_answer_assets(session, store, subject_id, actor_id, answer_id=None):
    query = select(VoiceAsset).join(TwinAnswer).where(
        TwinAnswer.subject_id == subject_id, TwinAnswer.actor_id == actor_id)
    if answer_id:
        query = query.where(TwinAnswer.answer_id == answer_id)
    for asset in list(session.scalars(query)):
        store.delete(asset.object_key)
        session.delete(asset)

def _synthetic_reference(request, subject_id):
    try:
        if getattr(request.app.state, 'synthetic_voice_client', None) is None:
            raise VoiceUnavailable('合成声音未配置。')
        return load_synthetic_reference(request.app.state.settings, subject_id)
    except VoiceUnavailable as exc:
        raise VoiceNotFound('当前人物未配置可用的虚构合成声音。') from exc

def _voice_state(session, request, subject_id, actor_id):
    subject = session.get(Subject, subject_id)
    if subject is None or not subject.owner_actor_id:
        raise VoiceNotFound('人物空间不可用。')
    profile = _profile(session, subject_id, subject.owner_actor_id)
    if profile is None:
        raise VoiceNotFound('请由本人单独授权并设置声音。')
    try:
        ConsentRepository(session).require_active(profile.voice_consent_id, subject_id=subject_id,
            scope=ConsentScope.VOICE, actor_id=subject.owner_actor_id)
    except AppError:
        # A reader never receives the owner's private consent identifier.
        raise VoiceNotFound('本人声音授权已失效。') from None
    grant_revision = None
    if actor_id != subject.owner_actor_id:
        visible_episodes(session, subject_id, actor_id, cloud=True)
        grant = session.get(VoiceRecipientGrant, (subject_id, actor_id))
        if grant is None or not grant.enabled or grant.granted_by_actor_id != subject.owner_actor_id:
            raise VoiceNotFound('本人尚未向此亲友开放合成声音。')
        grant_revision = grant.revision
    synthetic = session.get(SyntheticVoiceProfile, profile.profile_id)
    reference_hash = None
    if synthetic:
        reference_hash = hashlib.sha256(_synthetic_reference(request, subject_id)).hexdigest()
        if (synthetic.preset != 'a01' or synthetic.provider != 'xiaomi'
                or reference_hash != synthetic.reference_sha256
                or profile.model_version != request.app.state.settings.xiaomi_voice_model):
            raise VoiceNotFound('声音参考已变化，请由本人重新设置。')
    signature = (profile.profile_id, profile.voice_consent_id, profile.sample_object_key,
        profile.sample_transcript, profile.model_version, reference_hash, grant_revision)
    return profile, synthetic, signature

def _current_pair(session, request, subject_id, actor_id, answer_id):
    from ..twin_validity import get_current_answer
    try:
        answer = get_current_answer(session, subject_id, actor_id, answer_id)
        if answer.response_type == 'UNKNOWN' or not answer.answer.strip():
            raise VoiceNotFound('这条回答没有可朗读的答案。')
        profile, synthetic, signature = _voice_state(session, request, subject_id, actor_id)
        return answer, profile, synthetic, signature
    except AppError:
        _discard_answer_assets(session, request.app.state.object_store, subject_id, actor_id, answer_id)
        session.commit()
        raise

def _profile_view(profile, synthetic=None, *, owner=True):
    return {'ready': profile is not None, 'profile_id':profile.profile_id if profile else None,
        'model_version':profile.model_version if profile else None,
        'voice_consent_id':profile.voice_consent_id if profile and owner else None,
        'synthetic':synthetic is not None, 'preset':synthetic.preset if synthetic else None}

@router.get('/voice/profile')
def read_profile(subject_id: str, request: Request, actor: Actor = Depends(current_actor),
                 session: Session = Depends(get_session)):
    owner = is_owner(session, subject_id, actor.actor_id)
    if owner:
        require_subject(session, subject_id, actor)
    else:
        visible_episodes(session, subject_id, actor.actor_id)
    try:
        profile, synthetic, _ = _voice_state(session, request, subject_id, actor.actor_id)
    except AppError:
        profile = synthetic = None
    presets = []
    if owner:
        try:
            _synthetic_reference(request, subject_id)
            presets = ['a01']
        except AppError:
            pass
    return _profile_view(profile, synthetic, owner=owner) | {
        'can_enroll':owner, 'can_synthesize':profile is not None, 'synthetic_presets':presets}

@router.post('/voice/profile/synthetic')
def enroll_synthetic(subject_id: str, body: SyntheticEnrollment, request: Request,
                     actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    actor_id = actor.actor_id
    publication_lock(session, subject_id)
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(body.voice_consent_id, subject_id=subject_id,
        scope=ConsentScope.VOICE, actor_id=actor_id)
    audio = _synthetic_reference(request, subject_id)
    profile_id = 'vp_' + uuid4().hex[:16]
    key = f'subjects/{subject_id}/voice/samples/{profile_id}.wav'
    existing = _profile(session, subject_id, actor_id)
    retired_keys = _retire_profile(session, existing) if existing else []
    profile = VoiceProfile(profile_id=profile_id, subject_id=subject_id, actor_id=actor_id,
        voice_consent_id=body.voice_consent_id, sample_object_key=key, sample_transcript='',
        model_version=request.app.state.settings.xiaomi_voice_model, created_at=utcnow())
    synthetic = SyntheticVoiceProfile(profile_id=profile_id, preset='a01', provider='xiaomi',
        reference_sha256=hashlib.sha256(audio).hexdigest())
    store = request.app.state.object_store
    try:
        store.put(key, audio, 'audio/wav')
        session.add(profile); session.flush(); session.add(synthetic); session.commit()
    except Exception:
        session.rollback()
        _recover_voice_write(request, VoiceProfile, profile_id, key, retired_keys)
        raise
    for obsolete in retired_keys:
        store.delete(obsolete)
    return _profile_view(profile, synthetic)

@router.post('/voice/profile')
def enroll(subject_id: str, request: Request, voice_consent_id: str = Form(...),
           transcript: str = Form(...), own_voice_confirmed: bool = Form(...),
           sample: UploadFile = File(...), actor: Actor = Depends(current_actor),
           session: Session = Depends(get_session)):
    actor_id = actor.actor_id
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(voice_consent_id, subject_id=subject_id,
        scope=ConsentScope.VOICE, actor_id=actor_id)
    text = transcript.strip()
    if not own_voice_confirmed or not text or len(text)>1000:
        raise VoiceNotFound('请确认样本只包含自己的声音，并核对样本文字。')
    audio = sample.file.read(8*1024*1024+1)
    if not audio or len(audio)>8*1024*1024:
        raise VoiceNotFound('声音样本为空或过大。')
    session.commit()
    try:
        details = request.app.state.voice_client.validate(audio)
    except VoiceSampleInvalid as exc:
        raise VoiceInvalid(str(exc)) from exc
    except VoiceUnavailable as exc:
        raise VoiceFailed('本机声音样本检查失败，请稍后重试。') from exc
    model_version = details.get('model_version')
    if not isinstance(model_version,str) or not model_version or len(model_version)>128:
        raise VoiceFailed('声音服务没有返回有效模型版本。')
    publication_lock(session, subject_id)
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(voice_consent_id, subject_id=subject_id,
        scope=ConsentScope.VOICE, actor_id=actor_id)
    existing = _profile(session, subject_id, actor_id)
    retired_keys = _retire_profile(session, existing) if existing else []
    profile_id = 'vp_' + uuid4().hex[:16]
    key = f'subjects/{subject_id}/voice/samples/{profile_id}.m4a'
    profile = VoiceProfile(profile_id=profile_id, subject_id=subject_id, actor_id=actor_id,
        voice_consent_id=voice_consent_id, sample_object_key=key,
        sample_transcript=text, model_version=model_version, created_at=utcnow())
    store = request.app.state.object_store
    try:
        store.put(key,audio,'audio/mp4'); session.add(profile); session.commit()
    except Exception:
        session.rollback()
        _recover_voice_write(request, VoiceProfile, profile_id, key, retired_keys)
        raise
    for obsolete in retired_keys:
        store.delete(obsolete)
    return _profile_view(profile)

def _grant_view(row, actor_id):
    return {'actor_id':actor_id, 'enabled':bool(row and row.enabled), 'revision':row.revision if row else 0}

@router.get('/voice/recipients/{actor_id}')
def read_recipient(subject_id: str, actor_id: str, actor: Actor = Depends(current_actor),
                   session: Session = Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    return _grant_view(session.get(VoiceRecipientGrant,(subject_id,actor_id)),actor_id)

@router.put('/voice/recipients/{actor_id}')
def set_recipient(subject_id: str, actor_id: str, body: VoiceGrantInput, request: Request,
                  actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    owner_id=actor.actor_id
    publication_lock(session,subject_id)
    require_owner(session,subject_id,owner_id)
    if actor_id==owner_id or session.get(Actor,actor_id) is None:
        raise VoiceNotFound('请指定已有故事授权的亲友。')
    if body.enabled:
        visible_episodes(session,subject_id,actor_id,cloud=True)
    row=session.get(VoiceRecipientGrant,(subject_id,actor_id))
    if row is None:
        row=VoiceRecipientGrant(subject_id=subject_id,actor_id=actor_id,granted_by_actor_id=owner_id,
            enabled=body.enabled,revision=1,created_at=utcnow(),updated_at=utcnow())
        session.add(row)
    elif row.enabled!=body.enabled or row.granted_by_actor_id!=owner_id:
        row.enabled=body.enabled;row.revision+=1;row.updated_at=utcnow();row.granted_by_actor_id=owner_id
    if not body.enabled:
        _discard_answer_assets(session,request.app.state.object_store,subject_id,actor_id)
    session.commit()
    return _grant_view(row,actor_id)

@router.post('/twin/answers/{answer_id}/speech')
def create_speech(subject_id: str, answer_id: str, request: Request,
                  body: SavedSpeechInput | None = None,
                  actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    actor_id=actor.actor_id
    publication_lock(session,subject_id)
    answer,profile,synthetic,signature=_current_pair(session,request,subject_id,actor_id,answer_id)
    cached=session.scalar(select(VoiceAsset).where(VoiceAsset.answer_id==answer_id,VoiceAsset.profile_id==profile.profile_id))
    if cached:
        result={'status':'ready','asset_id':cached.asset_id,'model_version':cached.model_version}
        session.commit();return result
    answer_text=answer.answer
    profile_id=profile.profile_id
    sample_key=profile.sample_object_key
    sample_transcript=profile.sample_transcript
    provider=request.app.state.synthetic_voice_client if synthetic else request.app.state.voice_client
    session.commit()
    try:
        reference=request.app.state.object_store.get(sample_key)
        audio,model_version=provider.synthesize(answer_text,reference,sample_transcript)
        if not audio or not isinstance(model_version,str) or not model_version or len(model_version)>128:
            raise VoiceUnavailable('Invalid audio metadata')
    except (VoiceUnavailable,OSError) as exc:
        raise VoiceFailed('声音生成暂时失败，可以重试。') from exc
    publication_lock(session,subject_id)
    current,_,_,current_signature=_current_pair(session,request,subject_id,actor_id,answer_id)
    if signature!=current_signature or answer_text!=current.answer:
        raise VoiceNotFound('声音授权或回答已变化，请重新开始。')
    cached=session.scalar(select(VoiceAsset).where(VoiceAsset.answer_id==answer_id,VoiceAsset.profile_id==profile_id))
    if cached:
        result={'status':'ready','asset_id':cached.asset_id,'model_version':cached.model_version}
        session.commit();return result
    asset_id='va_'+uuid4().hex[:16]
    key=f'subjects/{subject_id}/voice/answers/{asset_id}.wav'
    store=request.app.state.object_store
    try:
        store.put(key,audio,'audio/wav')
        session.add(VoiceAsset(asset_id=asset_id,answer_id=answer_id,profile_id=profile_id,
            object_key=key,model_version=model_version,created_at=utcnow()))
        session.commit()
    except Exception:
        session.rollback()
        _recover_voice_write(request, VoiceAsset, asset_id, key)
        raise
    return {'status':'ready','asset_id':asset_id,'model_version':model_version}

@router.get('/voice/assets/{asset_id}/audio')
def read_speech(subject_id: str, asset_id: str, request: Request,
                actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    actor_id=actor.actor_id
    publication_lock(session,subject_id)
    asset=session.scalar(select(VoiceAsset).join(TwinAnswer).where(VoiceAsset.asset_id==asset_id,
        TwinAnswer.subject_id==subject_id,TwinAnswer.actor_id==actor_id))
    if asset is None:
        raise VoiceNotFound('声音文件不存在或已失效。')
    _,profile,_,_=_current_pair(session,request,subject_id,actor_id,asset.answer_id)
    if profile.profile_id!=asset.profile_id:
        request.app.state.object_store.delete(asset.object_key);session.delete(asset);session.commit()
        raise VoiceNotFound('声音设置已变化。')
    try:
        audio=request.app.state.object_store.get(asset.object_key)
    except OSError as exc:
        session.delete(asset);session.commit()
        raise VoiceNotFound('声音文件不可用，请重新生成。') from exc
    session.commit()
    return Response(content=audio,media_type='audio/wav',headers={'Cache-Control':'no-store'})

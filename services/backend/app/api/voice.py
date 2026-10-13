"""A separately consented local voice profile and server-authorized answer playback."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import AppError
from ..models import Actor, ConsentScope, TwinAnswer, VoiceAsset, VoiceProfile, utcnow
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from ..voice_client import VoiceSampleInvalid, VoiceUnavailable
from .twin import require_subject

router = APIRouter(prefix="/api/v1/subjects/{subject_id}", tags=["voice"])


class VoiceNotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404


class VoiceFailed(AppError):
    code = "VOICE_UNAVAILABLE"
    http_status = 503


class VoiceInvalid(AppError):
    code = "VOICE_SAMPLE_INVALID"
    http_status = 422


def _profile(session: Session, subject_id: str, actor_id: str) -> VoiceProfile | None:
    return session.scalar(select(VoiceProfile).where(
        VoiceProfile.subject_id == subject_id, VoiceProfile.actor_id == actor_id,
        VoiceProfile.revoked_at.is_(None)).order_by(VoiceProfile.created_at.desc()))


def discard_profile(session: Session, store, profile: VoiceProfile) -> None:
    for asset in list(session.scalars(select(VoiceAsset).where(VoiceAsset.profile_id == profile.profile_id))):
        store.delete(asset.object_key)
        session.delete(asset)
    store.delete(profile.sample_object_key)
    profile.sample_object_key = ""
    profile.sample_transcript = ""
    profile.model_version = ""
    profile.revoked_at = utcnow()


@router.get("/voice/profile")
def read_profile(subject_id: str, actor: Actor = Depends(current_actor),
                 session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    profile = _profile(session, subject_id, actor.actor_id)
    return {"ready": profile is not None, "profile_id": profile.profile_id if profile else None,
            "model_version": profile.model_version if profile else None,
            "voice_consent_id": profile.voice_consent_id if profile else None}


@router.post("/voice/profile")
def enroll(subject_id: str, request: Request, voice_consent_id: str = Form(...),
           transcript: str = Form(...), own_voice_confirmed: bool = Form(...),
           sample: UploadFile = File(...), actor: Actor = Depends(current_actor),
           session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(voice_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.VOICE, actor_id=actor.actor_id)
    text = transcript.strip()
    if not own_voice_confirmed or not text or len(text) > 1000:
        raise VoiceNotFound("请确认样本只包含自己的声音，并核对样本文字。")
    audio = sample.file.read(8 * 1024 * 1024 + 1)
    if not audio or len(audio) > 8 * 1024 * 1024:
        raise VoiceNotFound("声音样本为空或过大。")
    try:
        details = request.app.state.voice_client.validate(audio)
    except VoiceSampleInvalid as exc:
        raise VoiceInvalid(str(exc)) from exc
    except VoiceUnavailable as exc:
        raise VoiceFailed(str(exc)) from exc
    model_version = details.get("model_version")
    if not isinstance(model_version, str) or not model_version:
        raise VoiceFailed("声音服务没有返回模型版本。")
    existing = _profile(session, subject_id, actor.actor_id)
    if existing is not None:
        discard_profile(session, request.app.state.object_store, existing)
    profile_id = "vp_" + uuid4().hex[:16]
    key = f"subjects/{subject_id}/voice/samples/{profile_id}.m4a"
    request.app.state.object_store.put(key, audio, "audio/mp4")
    session.add(VoiceProfile(profile_id=profile_id, subject_id=subject_id, actor_id=actor.actor_id,
                             voice_consent_id=voice_consent_id, sample_object_key=key,
                             sample_transcript=text, model_version=model_version,
                             created_at=utcnow()))
    session.commit()
    return {"ready": True, "profile_id": profile_id, "model_version": model_version,
            "voice_consent_id": voice_consent_id}


@router.post("/twin/answers/{answer_id}/speech")
def create_speech(subject_id: str, answer_id: str, request: Request,
                  actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    profile = _profile(session, subject_id, actor.actor_id)
    if profile is None:
        raise VoiceNotFound("请先单独授权并录制自己的声音样本。")
    ConsentRepository(session).require_active(profile.voice_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.VOICE, actor_id=actor.actor_id)
    answer = session.scalar(select(TwinAnswer).where(
        TwinAnswer.answer_id == answer_id, TwinAnswer.subject_id == subject_id,
        TwinAnswer.actor_id == actor.actor_id, TwinAnswer.invalidated_at.is_(None)))
    if answer is None or answer.response_type == "UNKNOWN":
        raise VoiceNotFound("这条回答已过期或没有可朗读的答案。")
    cached = session.scalar(select(VoiceAsset).where(
        VoiceAsset.answer_id == answer_id, VoiceAsset.profile_id == profile.profile_id))
    if cached is not None:
        return {"status": "ready", "asset_id": cached.asset_id, "model_version": cached.model_version}
    profile_id = profile.profile_id
    consent_id = profile.voice_consent_id
    sample_key = profile.sample_object_key
    sample_transcript = profile.sample_transcript
    answer_text = answer.answer
    session.commit()
    try:
        reference = request.app.state.object_store.get(sample_key)
        audio, model_version = request.app.state.voice_client.synthesize(
            answer_text, reference, sample_transcript)
    except (VoiceUnavailable, OSError) as exc:
        raise VoiceFailed("本机声音生成暂时失败，可以重试。") from exc
    # A revocation or memory edit can land while the local model generates.
    # Discard that output instead of resurrecting an invalid voice asset.
    session.expire_all()
    current_profile = session.get(VoiceProfile, profile_id)
    current_answer = session.get(TwinAnswer, answer_id)
    if (current_profile is None or current_profile.revoked_at is not None or
            current_answer is None or current_answer.invalidated_at is not None):
        raise VoiceNotFound("声音授权或回答已变化，请重新开始。")
    ConsentRepository(session).require_active(consent_id, subject_id=subject_id,
                                               scope=ConsentScope.VOICE, actor_id=actor.actor_id)
    asset_id = "va_" + uuid4().hex[:16]
    key = f"subjects/{subject_id}/voice/answers/{asset_id}.wav"
    request.app.state.object_store.put(key, audio, "audio/wav")
    session.add(VoiceAsset(asset_id=asset_id, answer_id=answer_id,
                           profile_id=profile_id, object_key=key,
                           model_version=model_version, created_at=utcnow()))
    session.commit()
    return {"status": "ready", "asset_id": asset_id, "model_version": model_version}


@router.get("/voice/assets/{asset_id}/audio")
def read_speech(subject_id: str, asset_id: str, request: Request,
                actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> Response:
    require_subject(session, subject_id, actor)
    row = session.execute(select(VoiceAsset, VoiceProfile, TwinAnswer)
                          .join(VoiceProfile, VoiceAsset.profile_id == VoiceProfile.profile_id)
                          .join(TwinAnswer, VoiceAsset.answer_id == TwinAnswer.answer_id)
                          .where(VoiceAsset.asset_id == asset_id,
                                 VoiceProfile.subject_id == subject_id,
                                 VoiceProfile.actor_id == actor.actor_id,
                                 VoiceProfile.revoked_at.is_(None),
                                 TwinAnswer.invalidated_at.is_(None))).first()
    if row is None:
        raise VoiceNotFound("声音文件不存在或已失效。")
    asset, profile, _ = row
    ConsentRepository(session).require_active(profile.voice_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.VOICE, actor_id=actor.actor_id)
    return Response(content=request.app.state.object_store.get(asset.object_key), media_type="audio/wav")

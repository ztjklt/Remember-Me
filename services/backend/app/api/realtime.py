"""Public scoped call tickets; service-only audio and answer operations."""
import asyncio
import hashlib
import hmac
import json
import io
import wave
import secrets
from datetime import timedelta
from uuid import uuid4
from urllib.parse import quote
from typing import Literal
from fastapi import APIRouter, Depends, Request, Response, Form, File, UploadFile, WebSocket
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from livekit import api
from ..db import get_session
from ..models import Actor, ConsentScope, TwinAnswer, as_utc, utcnow
from ..realtime_models import RealtimeVoiceProfile, VoiceCall
from ..realtime_access import check_call, configured, policy, profile_for, default_voice
from ..realtime_provider import RealtimeUnavailable, validate_sample, enrollment_prefix
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from ..errors import AppError
from ..tokens import hash_actor_token
from .twin import require_subject, TwinNotFound, answer_question, read_answer, TwinQuestion

router = APIRouter(tags=['realtime-voice'])
PREFIX = '/api/v1/subjects/{subject_id}/twin/voice'
# Room cleanup must not delay a durable hang-up behind network retries.
_ROOM_DELETE_TIMEOUT_SECONDS = 3.0


class CallRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cloud_consent_id: str = Field(min_length=1)
    voice_consent_id: str = Field(min_length=1)
    policy: str
    voice_mode: Literal['personal', 'default'] = 'personal'
    recording_consent_id: str | None = None
    speaker_consent_id: str | None = None
    enroll_owner_voice: bool = False


class InterruptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str = Field(min_length=1, max_length=64)


class SpokenQuestion(InterruptRequest):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=1000)


def worker_authorization(request):
    expected = request.app.state.settings.realtime_worker_secret.get_secret_value()
    if len(expected) < 32 or not hmac.compare_digest(request.headers.get('Authorization', '').encode(), ('Bearer '+expected).encode()):
        raise TwinNotFound('Not found')


def profile_view(profile):
    return {'ready': bool(profile and profile.status == 'ready'),
            'profile_id': profile.profile_id if profile else None,
            'status': profile.status if profile else 'missing',
            'model_version': profile.model if profile else None,
            'voice_consent_id': profile.consent_id if profile else None}


@router.get(PREFIX + '/capabilities')
def capabilities(subject_id: str, request: Request, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_subject(session, subject_id, actor)
    s = request.app.state.settings
    profile = profile_for(session, subject_id, actor.actor_id)
    return {'available': configured(s, request.app.state.realtime_provider),
            'default_voice_available': bool(configured(s, request.app.state.realtime_provider) and default_voice(s)), 'policy': policy(s),
            'notice': '通话期间，麦克风原音发送到百炼实时识别；问题和相关记忆由现有孪生模型处理，开启旧聊天记忆时也会参考同账号空间以前的电话和文字聊天；专用声音样本发送到百炼复刻音色，回答文字由 CosyVoice 生成语音，音频通过实时通话服务传输。点击开始即确认本次云端语音对话；启用自然采集的客户端会保存你的原话为待核对资料，先通过自然介绍记住本人声音，再从匹配本人的清晰聊天片段准备本人音色和自动更新记忆。声音未匹配时继续聊天，不作为本人资料更新。你可以继续聊天，稍后查看、更正、删除或撤销授权。',
            'voiceprint_available':__import__('app.voiceprints',fromlist=['available']).available(s), 'owner_voice_registered':__import__('app.voiceprints',fromlist=['owner_registered']).owner_registered(session,subject_id,s), 'profile': profile_view(profile), 'dialogue_capture_available':True, 'natural_voice_preparation':__import__('app.speaker_identification',fromlist=['available']).available(s)}


@router.get(PREFIX + '/profile')
async def read_profile(subject_id: str, request: Request, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_subject(session, subject_id, actor)
    profile = profile_for(session, subject_id, actor.actor_id)
    if profile:
        ConsentRepository(session).require_active(profile.consent_id, subject_id=subject_id, scope=ConsentScope.VOICE, actor_id=actor.actor_id)
        if profile.status == 'enrollment_unknown' and not profile.provider_voice_id:
            known=await run_in_threadpool(request.app.state.realtime_provider.operation, 'list_voice',
                prefix=enrollment_prefix(profile.profile_id),page_index=0,page_size=100)
            voices=known.get('voice_list',[])
            if len(voices)==1:
                profile.provider_voice_id=voices[0]['voice_id'];profile.status='enrolling';session.commit()
        if profile.status == 'enrolling' and profile.provider_voice_id:
            info = await run_in_threadpool(request.app.state.realtime_provider.operation, 'query_voice', voice_id=profile.provider_voice_id)
            session.expire_all()
            if profile.revoked_at: raise TwinNotFound('声音授权已撤销。')
            if info.get('target_model') != profile.model: raise RealtimeUnavailable('音色与当前合成模型不匹配。')
            profile.status = {'OK':'ready','UNDEPLOYED':'failed'}.get(info.get('status'), 'enrolling')
            session.commit()
    return profile_view(profile)


@router.post(PREFIX + '/profile')
async def enroll_profile(subject_id: str, request: Request,
                         voice_consent_id: str = Form(...), transcript: str = Form(...),
                         own_voice_confirmed: bool = Form(...), accepted_policy: str = Form(...),
                         sample: UploadFile = File(...), actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_subject(session, subject_id, actor)
    s = request.app.state.settings
    if not configured(s, request.app.state.realtime_provider): raise RealtimeUnavailable('实时声音服务尚未配置。')
    ConsentRepository(session).require_active(voice_consent_id, subject_id=subject_id, scope=ConsentScope.VOICE, actor_id=actor.actor_id)
    if not own_voice_confirmed or not transcript.strip() or len(transcript) > 1000 or accepted_policy != policy(s):
        raise TwinNotFound('请确认只有本人声音、核对样本文字并同意当前声音用途。')
    if profile_for(session, subject_id, actor.actor_id): raise RealtimeUnavailable('已有声音样本，请先撤销旧声音授权再重新录制。')
    data = await sample.read(8*1024*1024+1)
    await run_in_threadpool(validate_sample, data)
    session.expire_all()
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(voice_consent_id, subject_id=subject_id, scope=ConsentScope.VOICE, actor_id=actor.actor_id)
    from .twin import publication_lock
    publication_lock(session, subject_id)
    if profile_for(session,subject_id,actor.actor_id):raise RealtimeUnavailable('已有本人音色，继续正常通话即可。')
    if guard := request.scope.get('source_authorization'):guard()
    identifier = 'rvp_' + uuid4().hex
    ticket = secrets.token_urlsafe(32)
    key = f'subjects/{subject_id}/realtime-voice/{identifier}.m4a'
    request.app.state.object_store.put(key, data, 'audio/mp4')
    profile = RealtimeVoiceProfile(profile_id=identifier, subject_id=subject_id, actor_id=actor.actor_id,
        consent_id=voice_consent_id, accepted_policy=accepted_policy, sample_key=key, reference_text=transcript.strip(), model=s.cosyvoice_model,
        status='enrolling', provider_voice_id='', fetch_digest=hashlib.sha256(ticket.encode()).hexdigest(),
        fetch_expires_at=utcnow()+timedelta(minutes=3), created_at=utcnow())
    session.add(profile); session.commit()
    url = s.realtime_public_url.rstrip('/') + '/api/v1/realtime-samples/' + identifier + '?ticket=' + quote(ticket)
    try:
        if on_created := request.scope.get('on_profile_created'):on_created(identifier)
        result = await run_in_threadpool(request.app.state.realtime_provider.operation, 'create_voice',
                    target_model=s.cosyvoice_model, prefix=enrollment_prefix(identifier), url=url, language_hints=['zh'])
        voice_id = result.get('voice_id')
        if not isinstance(voice_id, str) or not voice_id: raise RealtimeUnavailable('声音模型没有返回音色编号。')
        session.expire_all()
        profile.provider_voice_id = voice_id
        # A concurrent revocation must never resurrect the remote voice.
        if profile.revoked_at:
            profile.status='delete_pending'; session.commit()
            await run_in_threadpool(delete_remote_profiles, request.app)
            raise TwinNotFound('声音授权已撤销。')
        ConsentRepository(session).require_active(voice_consent_id, subject_id=subject_id, scope=ConsentScope.VOICE, actor_id=actor.actor_id)
        if guard := request.scope.get('source_authorization'):guard()
        session.commit()
        return profile_view(profile)
    except AppError:
        session.expire_all()
        if guard := request.scope.get('source_authorization'):
            try:guard()
            except AppError:
                profile.revoked_at=utcnow();profile.status='delete_pending';profile.fetch_digest='';session.commit()
                await run_in_threadpool(delete_remote_profiles,request.app)
        if not profile.revoked_at: profile.status='enrollment_unknown' if not profile.provider_voice_id else 'failed'
        session.commit()
        raise


@router.get(PREFIX + '/profile/preview')
async def preview_profile(subject_id: str, request: Request, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_subject(session, subject_id, actor)
    s = request.app.state.settings
    profile = profile_for(session, subject_id, actor.actor_id)
    if not configured(s, request.app.state.realtime_provider):
        raise RealtimeUnavailable('声音服务尚未配置。')
    from ..realtime_access import compatible_voice_policies
    if not profile or profile.status != 'ready' or profile.model != s.cosyvoice_model or profile.accepted_policy not in compatible_voice_policies(s):
        raise TwinNotFound('请等待本人音色就绪并确认当前声音用途。')
    profile_id, voice_id, model, consent_id = profile.profile_id, profile.provider_voice_id, profile.model, profile.consent_id
    actor_id = actor.actor_id
    ConsentRepository(session).require_active(consent_id, subject_id=subject_id, scope=ConsentScope.VOICE, actor_id=actor_id)
    session.commit()

    def still_authorized():
        with request.app.state.database.session() as guard:
            require_subject(guard, subject_id, current_actor(request, guard))
            ConsentRepository(guard).require_active(consent_id, subject_id=subject_id, scope=ConsentScope.VOICE, actor_id=actor_id)
            current = profile_for(guard, subject_id, actor_id)
            if not current or current.profile_id != profile_id or current.status != 'ready' or current.provider_voice_id != voice_id or current.accepted_policy not in compatible_voice_policies(s):
                raise TwinNotFound('声音状态已变化，请刷新后重试。')

    pcm = bytearray()
    stream = request.app.state.realtime_provider.speech('你好，这是合成音色试听。你可以听听这段声音是否像自己。', voice_id, model)
    try:
        async for chunk in stream:
            if await request.is_disconnected(): raise TwinNotFound('试听已取消。')
            await run_in_threadpool(still_authorized)
            pcm.extend(chunk)
            if len(pcm) > 1024 * 1024: raise RealtimeUnavailable('音色试听超过长度限制。')
    finally:
        await stream.aclose()
    await run_in_threadpool(still_authorized)
    if not pcm or len(pcm) % 2: raise RealtimeUnavailable('音色试听未能生成，请稍后重试。')
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000); output.writeframes(pcm)
    return Response(audio.getvalue(), media_type='audio/wav', headers={'Cache-Control': 'no-store'})


@router.get('/api/v1/realtime-samples/{profile_id}', include_in_schema=False)
def sample_fetch(profile_id: str, ticket: str, request: Request, session: Session = Depends(get_session)):
    profile = session.get(RealtimeVoiceProfile, profile_id)
    if (not profile or profile.revoked_at or profile.status != 'enrolling' or
        as_utc(profile.fetch_expires_at) <= utcnow() or
        not hmac.compare_digest(hashlib.sha256(ticket.encode()).hexdigest(), profile.fetch_digest)):
        raise TwinNotFound('Not found')
    ConsentRepository(session).require_active(profile.consent_id, subject_id=profile.subject_id, scope=ConsentScope.VOICE, actor_id=profile.actor_id)
    return Response(request.app.state.object_store.get(profile.sample_key), media_type='audio/mp4', headers={'Cache-Control':'no-store'})


@router.post(PREFIX + '/calls')
async def start_call(subject_id: str, payload: CallRequest, request: Request, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_subject(session, subject_id, actor)
    s = request.app.state.settings
    if not configured(s, request.app.state.realtime_provider): raise RealtimeUnavailable('实时通话服务尚未配置，文字孪生仍可使用。')
    if payload.policy != policy(s): raise RealtimeUnavailable('实时通话用途已更新，请重新确认。')
    for scope, identifier in [(ConsentScope.CLOUD_TWIN,payload.cloud_consent_id),(ConsentScope.VOICE,payload.voice_consent_id)]:
        ConsentRepository(session).require_active(identifier, subject_id=subject_id, scope=scope, actor_id=actor.actor_id)
    profile = profile_for(session, subject_id, actor.actor_id)
    if payload.voice_mode == 'default':
        preset = default_voice(s)
        if not preset: raise RealtimeUnavailable('当前服务尚未提供默认声音通话。')
        profile = session.scalar(select(RealtimeVoiceProfile).where(
            RealtimeVoiceProfile.profile_id.startswith('rvp_default_'), RealtimeVoiceProfile.subject_id == subject_id,
            RealtimeVoiceProfile.actor_id == actor.actor_id, RealtimeVoiceProfile.consent_id == payload.voice_consent_id,
            RealtimeVoiceProfile.revoked_at.is_(None), RealtimeVoiceProfile.accepted_policy == policy(s),
            RealtimeVoiceProfile.model == s.cosyvoice_model, RealtimeVoiceProfile.status == 'ready'))
        if not profile:
            profile = RealtimeVoiceProfile(profile_id='rvp_default_'+uuid4().hex, subject_id=subject_id,
                actor_id=actor.actor_id, consent_id=payload.voice_consent_id, accepted_policy=policy(s),
                sample_key='', reference_text='', provider_voice_id=preset, model=s.cosyvoice_model,
                status='ready', fetch_digest='', fetch_expires_at=utcnow())
            session.add(profile); session.flush()
    elif not profile or profile.status != 'ready' or profile.consent_id != payload.voice_consent_id or profile.model != s.cosyvoice_model:
        raise TwinNotFound('请先完成本人声音设置并等待音色就绪，或选用默认声音通话。')
    if payload.recording_consent_id:
        from ..dialogue_capture import consent
        consent(session, VoiceCall(subject_id=subject_id,actor_id=actor.actor_id,recording_consent_id=payload.recording_consent_id,speaker_consent_id=payload.speaker_consent_id,voice_consent_id=payload.voice_consent_id))
    elif payload.speaker_consent_id:raise TwinNotFound('对话采集许可不完整。')
    active = list(session.scalars(select(VoiceCall).where(VoiceCall.actor_id==actor.actor_id,VoiceCall.ended_at.is_(None))))
    for old in active: old.ended_at=utcnow()
    identifier='vc_'+uuid4().hex
    row=VoiceCall(enroll_owner_voice=payload.enroll_owner_voice,call_id=identifier,subject_id=subject_id,actor_id=actor.actor_id,profile_id=profile.profile_id,
        cloud_consent_id=payload.cloud_consent_id,voice_consent_id=payload.voice_consent_id,policy=payload.policy,
        recording_consent_id=payload.recording_consent_id,speaker_consent_id=payload.speaker_consent_id,
        credential_digest=hash_actor_token(request.headers.get('Authorization','')[7:].strip() or request.cookies.get('remember_session','')),
        room=identifier,participant='user_'+identifier,created_at=utcnow(),expires_at=utcnow()+timedelta(minutes=30))
    session.add(row); session.commit()
    token = (api.AccessToken(s.livekit_api_key.get_secret_value(),s.livekit_api_secret.get_secret_value())
        .with_identity(row.participant).with_ttl(timedelta(minutes=2))
        .with_grants(api.VideoGrants(room_join=True,room=row.room,can_publish=True,can_subscribe=True,
                                    can_publish_data=True,can_publish_sources=['microphone'],can_update_own_metadata=False))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=s.livekit_agent_name,metadata=json.dumps({'call_id':identifier}))])).to_jwt())
    return {'call_id':identifier,'room':row.room,'participant_identity':row.participant,
            'livekit_url':s.livekit_url,'token':token,'expires_at':row.expires_at.isoformat(), 'voice_mode': payload.voice_mode}


async def remove_room(app, room):
    s=app.state.settings
    async with api.LiveKitAPI(s.livekit_api_url,s.livekit_api_key.get_secret_value(),s.livekit_api_secret.get_secret_value()) as control:
        await control.room.delete_room(api.DeleteRoomRequest(room=room))


@router.delete(PREFIX + '/calls/{call_id}')
async def end_call(subject_id: str, call_id: str, request: Request, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    row=session.get(VoiceCall,call_id)
    if not row or row.actor_id!=actor.actor_id or row.subject_id!=subject_id: raise TwinNotFound('Not found')
    row.ended_at=utcnow();session.commit()
    try: await asyncio.wait_for(remove_room(request.app,row.room),timeout=_ROOM_DELETE_TIMEOUT_SECONDS)
    except Exception: pass  # Durable end denies all worker operations; its watchdog disconnects.
    return {'ended':True}


@router.get('/internal/voice-calls/{call_id}/authorize', include_in_schema=False)
def authorize_call(call_id: str, request: Request, session: Session = Depends(get_session)):
    worker_authorization(request)
    row, profile, actor=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    return {'call_id':row.call_id,'subject_id':row.subject_id,'room':row.room,'participant_identity':row.participant,'expires_at':row.expires_at.isoformat(), 'capture_voice_identity':bool(row.recording_consent_id and row.speaker_consent_id and __import__('app.voiceprints',fromlist=['available']).available(request.app.state.settings)), 'capture_voice_sample':bool(row.recording_consent_id and row.speaker_consent_id and __import__('app.speaker_identification',fromlist=['available']).available(request.app.state.settings))}


@router.post('/internal/voice-calls/{call_id}/answers', include_in_schema=False)
def answer_call(call_id: str,payload: SpokenQuestion,request: Request,session: Session=Depends(get_session)):
    worker_authorization(request)
    row,profile,actor=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    row.active_turn=payload.turn_id; row.active_answer_id=""; session.commit()
    if row.recording_consent_id:
        from ..dialogue_capture import remember_turn
        try:remember_turn(session,row,payload.turn_id,payload.question.strip())
        except Exception:session.rollback() # Capture must not prevent the conversation.
    # Reuse the final validated, source-versioned Twin operation, not a generic voice LLM.
    # A repeated worker turn ID from another call is a different request. Do
    # not let text's global request-id deduplication return an old call's answer.
    request_id=hashlib.sha256((call_id+'\0'+payload.turn_id).encode()).hexdigest()
    def current_turn(guard_session):
        current,_,_=check_call(guard_session,call_id,request.app.state.settings,request.app.state.realtime_provider)
        if current.active_turn!=payload.turn_id:
            raise TwinNotFound('回答已被打断。')
    # Historical recall shares the owner's text/phone memory; the parent chain
    # and publication guard still belong only to this active call and turn.
    result=answer_question(row.subject_id,TwinQuestion(question=payload.question,cloud_consent_id=row.cloud_consent_id,
        conversation_mode=True,previous_answer_id=row.previous_answer_id or None,request_id=request_id),
        request,actor,session,chat_history_scope='actor',publication_guard=current_turn,carry_latest_conversation=True)
    session.expire_all(); row,_,_=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    if row.active_turn != payload.turn_id: raise TwinNotFound("回答已被打断。")
    saved=session.get(TwinAnswer,result['answer_id'])
    if saved:saved.voice_call_id=call_id;saved.voice_turn_id=payload.turn_id
    row.active_answer_id=result["answer_id"]; row.previous_answer_id=result["answer_id"]; session.commit()
    return result


@router.get('/internal/voice-calls/{call_id}/speech/{answer_id}', include_in_schema=False)
async def speech_call(call_id: str,answer_id: str,turn_id: str,request: Request,session: Session=Depends(get_session)):
    worker_authorization(request)
    row,profile,actor=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    if row.active_turn != turn_id or row.active_answer_id != answer_id: raise TwinNotFound("回答已被打断。")
    result=read_answer(row.subject_id,answer_id,actor,session)
    if result['stale'] or result['response_type']=='UNKNOWN': raise TwinNotFound('回答已过期或没有可朗读的内容。')
    text=result['answer']  # Expression is used only if independently checked by the existing API.
    if result['response_type']=='SIMULATION' and result.get('expression') and result['expression'].get('status')=='available': text=result['expression']['text']
    voice_id,model=profile.provider_voice_id,profile.model
    session.commit()
    def still_authorized():
        with request.app.state.database.session() as guard:
            call,_,owner=check_call(guard,call_id,request.app.state.settings,request.app.state.realtime_provider)
            current=read_answer(call.subject_id,answer_id,owner,guard)
            return not current['stale'] and call.active_turn==turn_id and call.active_answer_id==answer_id
    async def audio():
        stream=request.app.state.realtime_provider.speech(text,voice_id,model)
        try:
            async for chunk in stream:
                if await request.is_disconnected(): return
                # Recheck before each audio packet; don't retain a transaction across a network wait.
                if not await run_in_threadpool(still_authorized): return
                yield chunk
        finally: await stream.aclose()
    return StreamingResponse(audio(),media_type='audio/pcm',headers={'X-Audio-Sample-Rate':'24000','X-Audio-Channels':'1','Cache-Control':'no-store'})


def revoke_realtime(app, session, consent_id):
    for call in session.scalars(select(VoiceCall).where(VoiceCall.ended_at.is_(None),
        (VoiceCall.voice_consent_id==consent_id)|(VoiceCall.cloud_consent_id==consent_id))): call.ended_at=utcnow()
    for profile in session.scalars(select(RealtimeVoiceProfile).where(RealtimeVoiceProfile.consent_id==consent_id,RealtimeVoiceProfile.revoked_at.is_(None))):
        if profile.sample_key: app.state.object_store.delete(profile.sample_key)
        profile.sample_key='';profile.reference_text='';profile.fetch_digest='';profile.revoked_at=utcnow()
        if profile.profile_id.startswith('rvp_default_'):
            profile.provider_voice_id=''; profile.status='deleted'
        else: profile.status='delete_pending'


def delete_remote_profiles(app):
    with app.state.database.session() as session:
        for profile in session.scalars(select(RealtimeVoiceProfile).where(RealtimeVoiceProfile.status=='delete_pending').limit(2)):
            if profile.profile_id.startswith('rvp_default_'):
                profile.provider_voice_id=''; profile.status='deleted'; continue
            try:
                identifiers=[profile.provider_voice_id] if profile.provider_voice_id else [
                    v['voice_id'] for v in app.state.realtime_provider.operation('list_voice',
                        prefix=enrollment_prefix(profile.profile_id),page_index=0,page_size=100,timeout_seconds=10).get('voice_list',[])]
                if not identifiers: continue  # An unknown enrollment may still finish later.
                for voice_id in identifiers: app.state.realtime_provider.operation('delete_voice',voice_id=voice_id,timeout_seconds=10)
            except RealtimeUnavailable: continue
            profile.provider_voice_id='';profile.status='deleted'
        session.commit()


@router.post('/internal/realtime/maintenance', include_in_schema=False)
def maintenance(request: Request):
    worker_authorization(request);delete_remote_profiles(request.app)
    return {'maintenance_completed':True}


@router.websocket('/internal/voice-calls/{call_id}/listen')
async def listen_call(websocket: WebSocket,call_id: str):
    from ..realtime_listen import proxy_listen
    await proxy_listen(websocket,call_id)


@router.post('/internal/voice-calls/{call_id}/interrupt', include_in_schema=False)
def interrupt_call(call_id: str, payload: InterruptRequest, request: Request, session: Session=Depends(get_session)):
    worker_authorization(request)
    row,_,_=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    if row.active_turn==payload.turn_id:
        row.active_turn='';row.active_answer_id='';session.commit()
    return {'interrupted':True}


@router.post('/internal/voice-calls/{call_id}/end', include_in_schema=False)
def worker_end(call_id: str, request: Request, session: Session=Depends(get_session)):
    worker_authorization(request)
    row=session.get(VoiceCall,call_id)
    if row: row.ended_at=utcnow();session.commit()
    return {'ended':True}


@router.post('/internal/voice-calls/{call_id}/samples',include_in_schema=False)
async def dialogue_sample(call_id:str,request:Request,turn_id:str=Form(...),sample:UploadFile=File(...),session:Session=Depends(get_session)):
    worker_authorization(request)
    row,_,_=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    from ..dialogue_capture import consent,validate_wave
    from ..dialogue_models import DialogueSample
    consent(session,row)
    if not 1<=len(turn_id)<=64:raise TwinNotFound('样本编号不正确。')
    data=await sample.read(500000+1)
    if len(data)>500000:raise TwinNotFound('对话样本太长。')
    try:duration=validate_wave(data)
    except Exception:return {'status':'skipped'}
    existing=session.scalar(select(DialogueSample).where(DialogueSample.call_id==call_id,DialogueSample.turn_id==turn_id))
    if existing:
        if existing.checksum!=hashlib.sha256(data).hexdigest():raise TwinNotFound('同一发言已有另一份原音。')
        return {'status':existing.status}
    if profile_for(session,row.subject_id,row.actor_id):return {'status':'prepared'}
    count=len(list(session.scalars(select(DialogueSample).where(DialogueSample.call_id==call_id))))
    if count>=3:return {'status':'skipped'}
    identifier='ds_'+uuid4().hex;key='dialogue-samples/'+identifier+'/original.wav'
    request.app.state.object_store.put(key,data,'audio/wav')
    session.add(DialogueSample(sample_id=identifier,call_id=call_id,turn_id=turn_id,audio_key=key,checksum=hashlib.sha256(data).hexdigest(),duration_ms=duration))
    try:session.commit()
    except Exception:session.rollback();request.app.state.object_store.delete(key);raise
    return {'status':'uploaded'}


@router.post('/internal/voice-calls/{call_id}/utterances',include_in_schema=False)
async def utterance(call_id:str,request:Request,turn_id:str=Form(...),sample:UploadFile=File(...),session:Session=Depends(get_session)):
    worker_authorization(request)
    row,_,_=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    from ..dialogue_capture import consent
    from ..voiceprint_models import VoiceUtterance
    consent(session,row)
    if not 1<=len(turn_id)<=64:raise TwinNotFound('发言编号不正确。')
    data=await sample.read(960000+45)
    if len(data)>960000+44:raise TwinNotFound('发言原音太长。')
    try:
        with wave.open(io.BytesIO(data),'rb') as w:
            if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getframerate()!=16000 or not 8000<=w.getnframes()<=480000:return {'status':'skipped'}
    except (wave.Error,EOFError):return {'status':'skipped'}
    digest=hashlib.sha256(data).hexdigest()
    old=session.scalar(select(VoiceUtterance).where(VoiceUtterance.call_id==call_id,VoiceUtterance.turn_id==turn_id))
    if old:
        if old.checksum!=digest:raise TwinNotFound('发言编号已使用。')
        return {'status':old.status}
    from sqlalchemy import func
    if session.scalar(select(func.count()).select_from(VoiceUtterance).where(VoiceUtterance.call_id==call_id))>=120:return {'status':'skipped'}
    identifier='vu_'+uuid4().hex;key='voice-utterances/'+identifier+'/original.wav'
    request.app.state.object_store.put(key,data,'audio/wav')
    try:
        session.add(VoiceUtterance(utterance_id=identifier,call_id=call_id,turn_id=turn_id,audio_key=key,checksum=digest));session.commit()
    except Exception:
        session.rollback();request.app.state.object_store.delete(key);raise
    return {'status':'uploaded'}

@router.get('/internal/voice-calls/{call_id}/utterances/{turn_id}',include_in_schema=False)
def utterance_status(call_id:str,turn_id:str,request:Request,session:Session=Depends(get_session)):
    worker_authorization(request)
    check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    from ..voiceprint_models import VoiceUtterance
    row=session.scalar(select(VoiceUtterance).where(VoiceUtterance.call_id==call_id,VoiceUtterance.turn_id==turn_id))
    if not row:raise TwinNotFound('此发言不存在。')
    report=row.report or {};speakers=report.get('speakers',[])
    if report.get('owner_enrollment')=='registered':message='已经记住你的声音。之后匹配到你的发言会自动更新记忆。'
    elif any(s.get('is_subject') for s in speakers):message='匹配到本人声音，正在整理本人发言。'
    elif row.status=='ready':
        names=sorted({s['name'] for s in speakers if s.get('name')})
        message=('刚才听到'+ '、'.join(names)+'的发言；没有作为本人记忆更新。') if names else '这轮声音暂未匹配本人，继续聊天即可。'
    else:message=None
    return {'status':row.status,'message':message,'failure_code':report.get('failure_code')}


@router.post('/internal/voice-calls/{call_id}/turn-complete',include_in_schema=False)
def complete_turn(call_id:str,payload:InterruptRequest,request:Request,session:Session=Depends(get_session)):
    worker_authorization(request)
    row,_,_=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    if row.active_turn==payload.turn_id:row.completed_turn_id=payload.turn_id;session.commit()
    return {'completed':True}

"""Public scoped call tickets; service-only audio and answer operations."""
import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from uuid import uuid4
from urllib.parse import quote
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
from ..realtime_access import check_call, configured, policy, profile_for
from ..realtime_provider import RealtimeUnavailable, validate_sample, enrollment_prefix
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from ..errors import AppError
from ..tokens import hash_actor_token
from .twin import require_subject, TwinNotFound, ask, read_answer, TwinQuestion

router = APIRouter(tags=['realtime-voice'])
PREFIX = '/api/v1/subjects/{subject_id}/twin/voice'
# Room cleanup must not delay a durable hang-up behind network retries.
_ROOM_DELETE_TIMEOUT_SECONDS = 3.0


class CallRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cloud_consent_id: str = Field(min_length=1)
    voice_consent_id: str = Field(min_length=1)
    policy: str


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
    return {'available': configured(s, request.app.state.realtime_provider), 'policy': policy(s),
            'notice': '通话期间，麦克风原音发送到百炼实时识别；问题和相关记忆由现有孪生模型处理；专用声音样本发送到百炼复刻音色，回答文字由 CosyVoice 生成语音，音频通过实时通话服务传输。通话不会自动保存为记忆，可随时静音、结束或撤销声音授权。',
            'profile': profile_view(profile)}


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
        session.commit()
        return profile_view(profile)
    except AppError:
        session.expire_all()
        if not profile.revoked_at: profile.status='enrollment_unknown' if not profile.provider_voice_id else 'failed'
        session.commit()
        raise


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
    if not profile or profile.status != 'ready' or profile.consent_id != payload.voice_consent_id or profile.model != s.cosyvoice_model:
        raise TwinNotFound('请先完成本人声音设置并等待音色就绪。')
    active = list(session.scalars(select(VoiceCall).where(VoiceCall.actor_id==actor.actor_id,VoiceCall.ended_at.is_(None))))
    for old in active: old.ended_at=utcnow()
    identifier='vc_'+uuid4().hex
    row=VoiceCall(call_id=identifier,subject_id=subject_id,actor_id=actor.actor_id,profile_id=profile.profile_id,
        cloud_consent_id=payload.cloud_consent_id,voice_consent_id=payload.voice_consent_id,policy=payload.policy,
        credential_digest=hash_actor_token(request.headers.get('Authorization','')[7:].strip() or request.cookies.get('remember_session','')),
        room=identifier,participant='user_'+identifier,created_at=utcnow(),expires_at=utcnow()+timedelta(minutes=30))
    session.add(row); session.commit()
    token = (api.AccessToken(s.livekit_api_key.get_secret_value(),s.livekit_api_secret.get_secret_value())
        .with_identity(row.participant).with_ttl(timedelta(minutes=2))
        .with_grants(api.VideoGrants(room_join=True,room=row.room,can_publish=True,can_subscribe=True,
                                    can_publish_data=True,can_publish_sources=['microphone'],can_update_own_metadata=False))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=s.livekit_agent_name,metadata=json.dumps({'call_id':identifier}))])).to_jwt())
    return {'call_id':identifier,'room':row.room,'participant_identity':row.participant,
            'livekit_url':s.livekit_url,'token':token,'expires_at':row.expires_at.isoformat()}


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
    return {'call_id':row.call_id,'subject_id':row.subject_id,'room':row.room,'participant_identity':row.participant,'expires_at':row.expires_at.isoformat()}


@router.post('/internal/voice-calls/{call_id}/answers', include_in_schema=False)
def answer_call(call_id: str,payload: SpokenQuestion,request: Request,session: Session=Depends(get_session)):
    worker_authorization(request)
    row,profile,actor=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    row.active_turn=payload.turn_id; row.active_answer_id=""; session.commit()
    # Reuse the final validated, source-versioned Twin operation, not a generic voice LLM.
    result=ask(row.subject_id,TwinQuestion(question=payload.question,cloud_consent_id=row.cloud_consent_id,
        conversation_mode=True,previous_answer_id=row.previous_answer_id or None,request_id=payload.turn_id),request,actor,session)
    session.expire_all(); row,_,_=check_call(session,call_id,request.app.state.settings,request.app.state.realtime_provider)
    if row.active_turn != payload.turn_id: raise TwinNotFound("回答已被打断。")
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
    if result['response_type']=='SIMULATION': text='根据现有记录推测，'+text
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
        app.state.object_store.delete(profile.sample_key)
        profile.sample_key='';profile.reference_text='';profile.fetch_digest='';profile.revoked_at=utcnow()
        profile.status='delete_pending'


def delete_remote_profiles(app):
    with app.state.database.session() as session:
        for profile in session.scalars(select(RealtimeVoiceProfile).where(RealtimeVoiceProfile.status=='delete_pending').limit(2)):
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

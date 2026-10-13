"""Opt-in ephemeral continuous calls; database remains the permission authority."""
from __future__ import annotations
import asyncio
import contextlib
import json
import threading
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from ..access import require_cloud, visible_episodes, source_basis, Hidden
from ..db import get_session
from ..errors import AppError
from ..models import Actor
from ..repositories.actors import ActorRepository
from ..security import current_actor
from ..realtime_providers import ParaformerRealtime, XiaomiRealtime, RealtimeFailure
from ..voice_turns import VoiceTurns
from ..twin_client import TwinUnavailable
from ..twin_validity import get_current_answer
from .twin import TwinQuestion, generate_answer, SourceChanged

router=APIRouter(tags=['continuous-voice'])
POLICY='continuous-voice-v1'


class CallInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    cloud_consent_id: str=Field(min_length=1,max_length=128)
    mode: Literal['evidence','persona']='evidence'
    policy: Literal['continuous-voice-v1']
    cloud_asr_allowed: Literal[True]
    cloud_tts_allowed: Literal[True]
    simple_mode: bool=False
    purpose: Literal['dialogue','calibration_report']='dialogue'
    calibration_id: str | None=Field(default=None,max_length=128)


@dataclass
class Call:
    id: str
    subject: str
    actor: str
    payload: CallInput
    created: float=field(default_factory=time.monotonic)
    connected: bool=False
    stop: asyncio.Event=field(default_factory=asyncio.Event)


def enabled(settings, actor):
    return settings.realtime_voice_enabled and actor.actor_id in settings.realtime_voice_actor_ids


@router.get('/api/v1/voice-capabilities')
def capabilities(request:Request,actor:Actor=Depends(current_actor)):
    settings=request.app.state.settings
    return {'enabled':enabled(settings,actor),'protocol':POLICY,
        'input':{'format':'pcm16le','sample_rate':16000,'channels':1},
        'output':{'format':'pcm16le','sample_rate':24000,'channels':1},
        'max_seconds':settings.realtime_voice_max_seconds}


@router.post('/api/v1/subjects/{subject_id}/voice-sessions',status_code=201)
async def create(subject_id:str,body:CallInput,request:Request,
                 actor:Actor=Depends(current_actor),session=Depends(get_session)):
    settings=request.app.state.settings
    if not enabled(settings,actor): raise Hidden('语音聊聊暂未开放。')
    require_cloud(session,subject_id,actor.actor_id,body.cloud_consent_id)
    visible_episodes(session,subject_id,actor.actor_id,cloud=True)
    if body.purpose=='calibration_report':
        from .calibration import _run,_check_source,require_subject
        require_subject(session,subject_id,actor)
        row=_run(session,subject_id,actor,body.calibration_id or '')
        if row.status!='complete' or not _check_source(session,row): raise Hidden('请先完成这次对照。')
    elif body.calibration_id is not None:
        raise Hidden('通话用途不匹配。')
    registry=request.app.state.voice_sessions
    for key,call in list(registry.items()):
        if call.stop.is_set() or time.monotonic()-call.created>settings.realtime_voice_max_seconds:
            call.stop.set(); registry.pop(key,None)
    if len(registry)>=settings.realtime_voice_max_sessions:
        raise RealtimeBusy('当前通话较多，请稍后再试。')
    # Starting a fresh call retires the old one for this account.
    for call in registry.values():
        if call.actor==actor.actor_id: call.stop.set()
    identifier='vc_'+uuid4().hex
    registry[identifier]=Call(identifier,subject_id,actor.actor_id,body)
    return {'session_id':identifier,'websocket_path':f'/api/v1/voice-sessions/{identifier}/stream',
            'protocol':POLICY,'expires_in':settings.realtime_voice_max_seconds}


class RealtimeBusy(AppError):
    code='VOICE_BUSY'; http_status=503


@router.delete('/api/v1/voice-sessions/{session_id}')
async def end(session_id:str,request:Request,actor:Actor=Depends(current_actor)):
    call=request.app.state.voice_sessions.get(session_id)
    if not call or call.actor!=actor.actor_id: raise Hidden('通话不存在。')
    call.stop.set()
    return {'ended':True}


class AsyncTwinBridge:
    """Synchronous orchestration, cancellable async transport on the call loop."""
    def __init__(self,loop,settings,history,cancelled):
        self.loop=loop; self.settings=settings; self.history=history; self.cancelled=cancelled
        self.futures=set()

    def check(self):
        if self.cancelled.is_set(): raise RealtimeFailure('TURN_CANCELLED')

    async def _request(self,path,payload):
        async with httpx.AsyncClient(timeout=110,trust_env=False,follow_redirects=False) as client:
            response=await client.post(self.settings.ai_core_url.rstrip('/')+path,json=payload)
            if response.is_error:
                raise TwinUnavailable('本轮回答暂未完成。')
            if len(response.content)>100_000: raise TwinUnavailable('回答过长。')
            return response.json()

    def request(self,path,payload):
        self.check()
        future=asyncio.run_coroutine_threadsafe(self._request(path,payload),self.loop)
        self.futures.add(future)
        try:
            result=future.result(timeout=115); self.check(); return result
        finally: self.futures.discard(future)

    def persona(self,payload): return self.request('/persona',payload)
    def answer(self,question,candidates):
        return self.request('/twin',dict(question=question,candidates=candidates,
            dialogue_context=self.history,voice_response=True))
    def cancel(self):
        self.cancelled.set()
        for future in tuple(self.futures): future.cancel()


@router.websocket('/api/v1/voice-sessions/{session_id}/stream')
async def stream(websocket:WebSocket,session_id:str):
    app=websocket.app; settings=app.state.settings
    call=app.state.voice_sessions.get(session_id)
    authorization=websocket.headers.get('authorization','')
    token=authorization[7:] if authorization.startswith('Bearer ') else ''
    if websocket.query_params or not call or call.connected or not token:
        await websocket.close(code=4403); return

    def guard_sync(answer=None):
        with app.state.database.session() as session:
            actor=ActorRepository(session).find_by_token(token)
            if not actor or actor.actor_id!=call.actor or not enabled(settings,actor):
                raise Hidden('通话已结束，请重新登录。')
            require_cloud(session,call.subject,call.actor,call.payload.cloud_consent_id)
            visible_episodes(session,call.subject,call.actor,cloud=True)
            if call.payload.purpose=='calibration_report':
                from .calibration import _run,_check_source,require_subject
                require_subject(session,call.subject,actor)
                row=_run(session,call.subject,actor,call.payload.calibration_id)
                if row.status!='complete' or not _check_source(session,row): raise SourceChanged('对照依据已变化。')
                if answer and answer['answer']!=row.summary: raise SourceChanged('对照已变化。')
            elif answer:
                get_current_answer(session,call.subject,call.actor,answer['answer_id'])
            return source_basis(session,call.subject)
    try:
        initial_basis=await asyncio.to_thread(guard_sync)
        if call.stop.is_set() or time.monotonic()-call.created>settings.realtime_voice_max_seconds:
            raise Hidden('通话已过期。')
    except AppError:
        await websocket.close(code=4403); return
    call.connected=True
    await websocket.accept()
    send_lock=asyncio.Lock()
    async def send(event):
        async with send_lock: await websocket.send_json(event)
    async def guard(answer=None):
        basis=await asyncio.to_thread(guard_sync,answer)
        if basis!=initial_basis: raise SourceChanged('资料或授权已变化，请重新进入语音聊聊。')
        if call.stop.is_set(): raise RealtimeFailure('CALL_ENDED')

    async def answer(question,history):
        if call.payload.purpose=='calibration_report':
            def report():
                from .calibration import _run
                with app.state.database.session() as session:
                    actor=ActorRepository(session).find_by_token(token)
                    if not actor: raise Hidden('身份已变化。')
                    row=_run(session,call.subject,actor,call.payload.calibration_id)
                    return {'answer':row.summary,'answer_id':'cal:'+row.calibration_id,
                            'source_version':initial_basis,'response_type':'SIMULATION','evidence':[]}
            return await asyncio.to_thread(report)
        loop=asyncio.get_running_loop(); cancelled=threading.Event()
        bridge=AsyncTwinBridge(loop,settings,history,cancelled)
        def generate():
            with app.state.database.session() as session:
                actor=ActorRepository(session).find_by_token(token)
                if not actor or actor.actor_id!=call.actor: raise Hidden('身份已变化。')
                request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
                    settings=settings,twin_client=bridge,embedding_encoder=app.state.embedding_encoder)))
                return generate_answer(call.subject,TwinQuestion(question=question,
                    cloud_consent_id=call.payload.cloud_consent_id,mode=call.payload.mode,retrieval_mode='local'),
                    request,actor,session,voice_context=history,cancel_check=bridge.check)
        try: return await asyncio.to_thread(generate)
        finally: bridge.cancel()

    async def tts(text):
        async for pcm in XiaomiRealtime(settings).stream(text): yield pcm
    turns=VoiceTurns(call.id,send,answer,tts,guard)
    asr=None; asr_task=None; paused=False; tasks=[]
    async def stop_asr():
        nonlocal asr,asr_task
        if asr_task:
            asr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await asr_task
            asr_task=None
        if asr:
            await asr.__aexit__(None,None,None); asr=None
    async def start_asr():
        nonlocal asr,asr_task
        asr=await ParaformerRealtime(settings,1400 if call.payload.simple_mode else 800).__aenter__()
        async def read():
            try:
                async for event in asr.events():
                    if paused or call.stop.is_set(): continue
                    if event['type']!='transcript': continue
                    await guard()
                    await turns.emit('transcript',text=event['text'],final=event['final'])
                    if event['final']:
                        await turns.submit(event['text'])
                    elif turns.current is not None:
                        # ASR confirms speech if local VAD missed it.
                        await turns.interrupt()
            except asyncio.CancelledError: raise
            except Exception as exc:
                await turns.emit('error',code=getattr(exc,'code','ASR_CONNECTION_FAILED'),
                                 message='语音识别连接中断，请重新进入。',stop_playback=True)
                call.stop.set()
        asr_task=asyncio.create_task(read())

    async def receive():
        nonlocal paused
        window=time.monotonic(); byte_count=0
        while not call.stop.is_set():
            message=await websocket.receive()
            if message['type']=='websocket.disconnect': break
            pcm=message.get('bytes')
            if pcm is not None:
                now=time.monotonic()
                if now-window>5: window=now; byte_count=0
                byte_count+=len(pcm)
                if byte_count>32_000*7: raise RealtimeFailure('AUDIO_RATE_LIMIT')
                if asr is not None and not paused: await asr.send(pcm)
                continue
            raw=message.get('text','')
            if len(raw)>2048: raise RealtimeFailure('EVENT_TOO_LARGE')
            event=json.loads(raw); kind=event.get('type')
            if kind=='interrupt':
                if turns.current is not None: await turns.interrupt()
            elif kind=='playback':
                turns.playback(event.get('turn_id'),event.get('samples'))
            elif kind in {'pause','resume'}:
                want=kind=='pause'
                if paused!=want:
                    paused=want
                    if paused:
                        await turns.interrupt(); await stop_asr()
                    else:
                        await guard()
                        if call.payload.purpose=='dialogue': await start_asr()
                    await turns.emit('paused',paused=paused)
            elif kind=='end': break
            else: raise RealtimeFailure('EVENT_INVALID')
        call.stop.set()

    async def monitor():
        while not call.stop.is_set():
            if time.monotonic()-call.created>settings.realtime_voice_max_seconds: break
            await guard(turns.current.get('answer') if turns.current else None)
            await asyncio.sleep(1)
        call.stop.set()

    try:
        if call.payload.purpose=='dialogue': await start_asr()
        await turns.emit('ready',protocol=POLICY,input_enabled=call.payload.purpose=='dialogue')
        if call.payload.purpose=='calibration_report': await turns.submit('这次对照有哪些不同？')
        tasks=[asyncio.create_task(receive()),asyncio.create_task(monitor()),asyncio.create_task(call.stop.wait())]
        done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if not task.cancelled(): task.result()
    except WebSocketDisconnect: pass
    except Exception as exc:
        with contextlib.suppress(Exception):
            await turns.emit('error',code=getattr(exc,'code','VOICE_CONNECTION_FAILED'),
                             message='通话已暂停，请重新进入。',stop_playback=True)
    finally:
        call.stop.set()
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await turns.close()
        with contextlib.suppress(Exception): await stop_asr()
        app.state.voice_sessions.pop(call.id,None)
        with contextlib.suppress(Exception): await websocket.close(code=1000)

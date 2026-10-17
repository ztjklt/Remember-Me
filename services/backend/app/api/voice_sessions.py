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
from ..realtime_providers import ParaformerRealtime, XiaomiRealtime, RealtimeFailure, endpoint_silence
from ..voice_material_cache import VoiceMaterialCache
from ..voice_prefetch import VoicePrefetch, SelectionCache
from ..voice_turns import VoiceTurns, conversation_control, UtteranceBuffer
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
    response_speed: Literal['reviewed','fast','streamed']='reviewed'
    engine: Literal['pipeline','step_realtime']='pipeline'
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
    claim_lock: threading.Lock=field(default_factory=threading.Lock)

    def claim(self):
        with self.claim_lock:
            if self.connected or self.stop.is_set(): return False
            self.connected=True
            return True


def enabled(settings, actor):
    return settings.realtime_voice_enabled and actor.actor_id in settings.realtime_voice_actor_ids


def step_enabled(settings):
    return (settings.step_realtime_enabled and settings.realtime_voice_fast_enabled
        and bool(settings.step_realtime_api_key and settings.step_realtime_api_key.get_secret_value()))


def check_engine(settings, payload):
    if payload.engine=='step_realtime' and (not step_enabled(settings)
            or payload.purpose!='dialogue' or payload.response_speed!='fast'):
        raise Hidden('实时试用暂未开放。')


@router.get('/api/v1/voice-capabilities')
def capabilities(request:Request,actor:Actor=Depends(current_actor)):
    settings=request.app.state.settings
    return {'enabled':enabled(settings,actor),'protocol':POLICY,
        'engines':['pipeline']+(['step_realtime'] if enabled(settings,actor) and step_enabled(settings) else []),
        'response_speeds':['reviewed']+(['fast'] if enabled(settings,actor) and settings.realtime_voice_fast_enabled else [])
            +(['streamed'] if enabled(settings,actor) and settings.realtime_voice_fast_enabled and settings.realtime_voice_streamed_enabled else []),
        'input':{'format':'pcm16le','sample_rate':16000,'channels':1},
        'output':{'format':'pcm16le','sample_rate':24000,'channels':1},
        'max_seconds':settings.realtime_voice_max_seconds}


@router.post('/api/v1/subjects/{subject_id}/voice-sessions',status_code=201)
async def create(subject_id:str,body:CallInput,request:Request,
                 actor:Actor=Depends(current_actor),session=Depends(get_session)):
    settings=request.app.state.settings
    if not enabled(settings,actor): raise Hidden('语音聊聊暂未开放。')
    check_engine(settings,body)
    if body.response_speed!='reviewed' and (not settings.realtime_voice_fast_enabled or body.purpose!='dialogue'
            or (body.response_speed=='streamed' and not settings.realtime_voice_streamed_enabled)):
        raise Hidden('快速语音暂未开放。')
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
    def __init__(self,loop,settings,history,cancelled,on_draft=None,*,response_speed='reviewed'):
        self.loop=loop; self.settings=settings; self.history=history; self.cancelled=cancelled
        self.futures=set()
        self.lock=threading.Lock()
        self.on_draft=on_draft
        self.response_speed=response_speed

    def check(self):
        if self.cancelled.is_set(): raise RealtimeFailure('TURN_CANCELLED')

    async def _request(self,path,payload):
        self.check()
        async with httpx.AsyncClient(timeout=110,trust_env=False,follow_redirects=False) as client:
            self.check()
            if self.on_draft is not None or self.response_speed!='reviewed':
                route={'streamed':'/voice-live','fast':'/voice-fast'}.get(self.response_speed,'/voice-stream')
                async with client.stream('POST',self.settings.ai_core_url.rstrip('/')+path+route,json=payload) as response:
                    if response.is_error:raise TwinUnavailable('本轮回答暂未完成。')
                    size=0;drafts=0
                    async for line in response.aiter_lines():
                        self.check();size+=len(line)
                        if size>100_000:raise TwinUnavailable('回答过长。')
                        event=json.loads(line)
                        if event.get('type')=='draft':
                            text=event.get('text');drafts+=1
                            if drafts>2 or not isinstance(text,str) or not 0<len(text)<=500:
                                raise TwinUnavailable('声音准备内容无效。')
                            if self.on_draft is not None:await self.on_draft(text)
                        elif event.get('type')=='final':
                            if not isinstance(event.get('result'),dict):raise TwinUnavailable('回答无效。')
                            if self.response_speed!='reviewed' and event.get('semantic_review')!='skipped':
                                raise TwinUnavailable('快速语音模式不匹配。')
                            return dict(event['result'],semantic_review=event.get('semantic_review','performed'))
                        else:raise TwinUnavailable('本轮回答未通过核对。')
                    raise TwinUnavailable('回答传输中断。')
            response=await client.post(self.settings.ai_core_url.rstrip('/')+path,json=payload)
            if response.is_error:
                raise TwinUnavailable('本轮回答暂未完成。')
            if len(response.content)>100_000: raise TwinUnavailable('回答过长。')
            return response.json()

    def _blocking(self,function,*args):
        with self.lock:
            self.check()
            future=asyncio.run_coroutine_threadsafe(function(*args),self.loop)
            self.futures.add(future)
        try:
            result=future.result(timeout=115); self.check(); return result
        finally:
            with self.lock: self.futures.discard(future)

    def request(self,path,payload):return self._blocking(self._request,path,payload)

    def persona(self,payload): return self.request('/persona',payload)
    def answer(self,question,candidates):
        return self.request('/twin',dict(question=question,candidates=candidates,
            dialogue_context=self.history,voice_response=True))
    def cancel(self):
        with self.lock:
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

    def guard_sync(answer=None, *, prepare_sources=False):
        with app.state.database.session() as session:
            if prepare_sources:
                from ..access import publication_lock
                publication_lock(session,call.subject)
            actor=ActorRepository(session).find_by_token(token)
            if not actor or actor.actor_id!=call.actor or not enabled(settings,actor):
                raise Hidden('通话已结束，请重新登录。')
            check_engine(settings,call.payload)
            if call.payload.response_speed!='reviewed' and (not settings.realtime_voice_fast_enabled
                    or (call.payload.response_speed=='streamed' and not settings.realtime_voice_streamed_enabled)):
                raise Hidden('快速语音已关闭。')
            require_cloud(session,call.subject,call.actor,call.payload.cloud_consent_id)
            ids=visible_episodes(session,call.subject,call.actor,cloud=True)
            if prepare_sources and call.payload.purpose=='dialogue':
                # Register deterministic spans of ALREADY reviewed recordings
                # before freezing the call version. No ASR interim or model
                # output enters the archive, and future preparation is read-only.
                from ..materials import effective_materials
                from ..access import is_owner,altered_story_ids
                if not is_owner(session,call.subject,call.actor):ids-=altered_story_ids(session,ids)
                effective_materials(session,call.subject,ids,enforce_budget=False)
            if call.payload.purpose=='calibration_report':
                from .calibration import _run,_check_source,require_subject
                require_subject(session,call.subject,actor)
                row=_run(session,call.subject,actor,call.payload.calibration_id)
                if row.status!='complete' or not _check_source(session,row): raise SourceChanged('对照依据已变化。')
                if answer and answer['answer']!=row.summary: raise SourceChanged('对照已变化。')
            elif answer and answer.get('interaction'):
                if not conversation_control(answer.get('question','')) or answer.get('response_type')!='CONVERSATION':
                    raise SourceChanged('通话状态已变化。')
            elif answer:
                get_current_answer(session,call.subject,call.actor,answer['answer_id'])
            basis=source_basis(session,call.subject)
            if prepare_sources:session.commit()
            return basis
    try:
        initial_basis=await asyncio.to_thread(guard_sync,prepare_sources=True)
        if call.stop.is_set() or time.monotonic()-call.created>settings.realtime_voice_max_seconds:
            raise Hidden('通话已过期。')
    except AppError:
        await websocket.close(code=4403); return
    # Authentication awaited above; claim on the event loop with no await
    # between the second check and assignment.
    if not call.claim():
        await websocket.close(code=4409);return
    await websocket.accept()
    send_lock=asyncio.Lock()
    async def send(event):
        async with send_lock: await websocket.send_json(event)
    async def guard(answer=None):
        basis=await asyncio.to_thread(guard_sync,answer)
        if basis!=initial_basis: raise SourceChanged('资料或授权已变化，请重新进入语音聊聊。')
        if call.stop.is_set(): raise RealtimeFailure('CALL_ENDED')

    material_cache=VoiceMaterialCache()
    selection_cache=SelectionCache()
    prepare_lock=threading.Lock()
    async def prefetch(question,history,cancel_check):
        cancel_check()
        await guard()
        def prepare():
            # Serialize preparatory workers; a final query never waits for this lock.
            with prepare_lock, app.state.database.session() as session:
                cancel_check()
                actor=ActorRepository(session).find_by_token(token)
                if not actor or actor.actor_id!=call.actor:raise Hidden('身份已变化。')
                request=SimpleNamespace(app=app)
                return generate_answer(call.subject,TwinQuestion(question=question,
                    cloud_consent_id=call.payload.cloud_consent_id,mode=call.payload.mode,retrieval_mode='local'),
                    request,actor,session,voice_context=history,material_cache=material_cache,
                    selection_cache=selection_cache,prepare_only=True,cancel_check=cancel_check)
        await asyncio.to_thread(prepare)
    prefetcher=VoicePrefetch(prefetch)
    async def answer(question,history,on_draft=None):
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
        control=conversation_control(question)
        if control:
            started=time.monotonic()
            async with httpx.AsyncClient(timeout=12,trust_env=False,follow_redirects=False) as client:
                response=await client.post(settings.ai_core_url.rstrip('/')+'/conversation',
                    json={'question':question,'intent':control})
                if response.is_error: raise TwinUnavailable('本轮回应暂未完成。')
                result=response.json()
            if result.get('response_type')!='CONVERSATION' or not isinstance(result.get('answer'),str) or not 0<len(result['answer'])<=60:
                raise TwinUnavailable('对话回应无效。')
            return dict(result,question=question,interaction=True,source_version=initial_basis,evidence=[],
                voice_timing={'retrieval_ms':0,'conversation_generation_ms':round((time.monotonic()-started)*1000)})
        loop=asyncio.get_running_loop(); cancelled=threading.Event()
        bridge=AsyncTwinBridge(loop,settings,history,cancelled,on_draft,response_speed=call.payload.response_speed)
        timing={};started=time.monotonic()
        def generate():
            with app.state.database.session() as session:
                actor=ActorRepository(session).find_by_token(token)
                if not actor or actor.actor_id!=call.actor: raise Hidden('身份已变化。')
                request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
                    settings=settings,twin_client=bridge,embedding_encoder=app.state.embedding_encoder)))
                result=generate_answer(call.subject,TwinQuestion(question=question,
                    cloud_consent_id=call.payload.cloud_consent_id,mode=call.payload.mode,retrieval_mode='local'),
                    request,actor,session,voice_context=history,cancel_check=bridge.check,
                    on_retrieved=lambda:timing.update(retrieval_ms=round((time.monotonic()-started)*1000)),
                    # Preparation is local retrieval only. Reviewed answers keep
                    # the same model/review path and fresh authorization checks.
                    material_cache=material_cache if call.payload.response_speed in {'reviewed','streamed'} else None,
                    selection_cache=selection_cache if call.payload.response_speed in {'reviewed','streamed'} and settings.realtime_voice_prefetch_enabled else None,
                    on_source_prepared=(lambda text:bridge._blocking(on_draft,text))
                        if call.payload.response_speed=='streamed' and on_draft is not None else None)
                return dict(result,voice_timing=timing,response_speed=call.payload.response_speed)
        try:return await asyncio.to_thread(generate)
        finally:bridge.cancel()

    tts_provider=None
    async def tts(text):
        nonlocal tts_provider
        if tts_provider is None:
            tts_provider=XiaomiRealtime(settings)
            tts_provider.cache_enabled=call.payload.response_speed=='streamed'
        async for pcm in tts_provider.stream(text): yield pcm
    if call.payload.engine=='step_realtime':
        from ..step_realtime import RealtimeVoiceTurns, StepRealtimeSpeech
        async def context(question,history):
            cancelled=threading.Event()
            def check():
                if cancelled.is_set():raise RealtimeFailure('TURN_CANCELLED')
            def prepare():
                with app.state.database.session() as session:
                    check()
                    actor=ActorRepository(session).find_by_token(token)
                    if not actor or actor.actor_id!=call.actor:raise Hidden('身份已变化。')
                    return generate_answer(call.subject,TwinQuestion(question=question,
                        cloud_consent_id=call.payload.cloud_consent_id,mode=call.payload.mode,retrieval_mode='local'),
                        SimpleNamespace(app=app),actor,session,voice_context=history,
                        material_cache=material_cache,selection_cache=selection_cache,
                        context_only=True,cancel_check=check)
            try:return await asyncio.to_thread(prepare)
            finally:cancelled.set()
        turns=RealtimeVoiceTurns(call.id,send,context,StepRealtimeSpeech(settings),guard)
    else:
        turns=VoiceTurns(call.id,send,answer,tts,guard,prepare_audio=True)
    asr=None; asr_task=None; paused=False; tasks=[]; utterance=UtteranceBuffer()
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
        asr=await ParaformerRealtime(settings,endpoint_silence(call.payload.simple_mode,call.payload.response_speed)).__aenter__()
        async def read():
            try:
                async for event in asr.events():
                    if paused or call.stop.is_set(): continue
                    if event['type']!='transcript': continue
                    await guard()
                    displayed=utterance.display(event['text'])
                    question=utterance.final(event['text']) if event['final'] else None
                    await turns.emit('transcript',text=displayed,final=event['final'] and question is not None,
                        begin_ms=event.get('begin_ms'),end_ms=event.get('end_ms'))
                    if event['final']:
                        prefetcher.finish()
                        if question: await turns.submit(question)
                    else:
                        if turns.current is not None:
                            # ASR confirms speech if local VAD missed it.
                            await turns.interrupt()
                        if call.payload.engine=='step_realtime' or (call.payload.response_speed in {'reviewed','streamed'} and settings.realtime_voice_prefetch_enabled):
                            prefetcher.offer(displayed,list(turns.history))
            except asyncio.CancelledError: raise
            except Exception as exc:
                await turns.emit('error',code=getattr(exc,'code','ASR_CONNECTION_FAILED'),
                                 message='语音识别连接中断，请重新进入。',stop_playback=True)
                call.stop.set()
        asr_task=asyncio.create_task(read())

    async def receive():
        nonlocal paused
        from ..pcm_rate import PcmRateLimiter
        rate=PcmRateLimiter()
        while not call.stop.is_set():
            message=await websocket.receive()
            if message['type']=='websocket.disconnect': break
            pcm=message.get('bytes')
            if pcm is not None:
                rate.consume(len(pcm))
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
                        prefetcher.finish()
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
        await turns.emit('ready',protocol=POLICY,input_enabled=call.payload.purpose=='dialogue',response_speed=call.payload.response_speed)
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
        await prefetcher.close()
        selection_cache.close()
        material_cache.clear()
        if tts_provider is not None:
            with contextlib.suppress(Exception): await tts_provider.close()
        with contextlib.suppress(Exception): await stop_asr()
        app.state.voice_sessions.pop(call.id,None)
        with contextlib.suppress(Exception): await websocket.close(code=1000)

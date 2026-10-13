"""LiveKit transport/turn handling around Remember Me's validated Twin API.

No generic voice LLM, provider key, sample or actor credential in this worker.
"""
import asyncio
import json
import os
import logging
from urllib.parse import urlsplit
from uuid import uuid4
import aiohttp
import httpx
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, stt, APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, room_io
from livekit.plugins import silero

TOPIC='remember.twin.voice.v1'


class PrivateLogFilter(logging.Filter):
    def filter(self,record):
        # Disabling session recording does not remove SDK warning extras.
        for key in list(vars(record)):
            if key.startswith('lk.pii.') or key in {'transcript','user_input','question','answer'}:
                record.__dict__[key]='[redacted]'
        return True


def private_logs():
    guard=PrivateLogFilter()
    logging.getLogger('livekit.agents').addFilter(guard)
    for name in ['', 'livekit', 'livekit.agents']:
        for handler in logging.getLogger(name).handlers:handler.addFilter(guard)


class Backend:
    def __init__(self, url, secret, call_id):
        parsed=urlsplit(url)
        if not (parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost'}):
            raise ValueError('Backend must use HTTPS or local loopback HTTP')
        if len(secret)<32: raise ValueError('Service credential is required')
        self.url=url.rstrip('/'); self.call_id=call_id
        self.headers={'Authorization':'Bearer '+secret}
        self.client=httpx.AsyncClient(timeout=120,follow_redirects=False,trust_env=False)

    async def request(self,method,path,**kwargs):
        response=await self.client.request(method,self.url+'/internal/voice-calls/'+self.call_id+path,headers=self.headers,**kwargs)
        response.raise_for_status();return response.json()

    async def frames(self,answer_id,turn_id):
        url=self.url+'/internal/voice-calls/'+self.call_id+'/speech/'+answer_id
        async with self.client.stream('GET',url,params={'turn_id':turn_id},headers=self.headers) as response:
            response.raise_for_status()
            if response.headers.get('content-type','').split(';')[0]!='audio/pcm' or response.headers.get('X-Audio-Sample-Rate')!='24000':
                raise ValueError('Invalid audio format')
            buffer=bytearray()
            async for chunk in response.aiter_bytes():
                buffer.extend(chunk)
                while len(buffer)>=960:  # 20 ms PCM16 mono packets
                    data=bytes(buffer[:960]);del buffer[:960]
                    yield rtc.AudioFrame(data=data,sample_rate=24000,num_channels=1,samples_per_channel=480)
            if len(buffer)%2: raise ValueError('Truncated PCM')
            if buffer: yield rtc.AudioFrame(data=bytes(buffer),sample_rate=24000,num_channels=1,samples_per_channel=len(buffer)//2)


class ProxySTT(stt.STT):
    def __init__(self,backend):
        super().__init__(capabilities=stt.STTCapabilities(streaming=True,interim_results=True))
        self.backend=backend
        self.on_final=None
    async def _recognize_impl(self,buffer,*,language=None,conn_options):
        raise NotImplementedError('Streaming only')
    def stream(self,*,language=None,conn_options=DEFAULT_API_CONNECT_OPTIONS):
        return ProxyStream(stt=self,conn_options=conn_options,sample_rate=16000)


async def pcm_chunks(source):
    buffer=bytearray()
    async for frame in source:
        if isinstance(frame,rtc.AudioFrame):
            if frame.num_channels!=1 or frame.sample_rate!=16000:raise ValueError('ASR requires 16 kHz mono')
            buffer.extend(bytes(frame.data))
            while len(buffer)>=3200:  # 100 ms, preserving every PCM sample
                yield bytes(buffer[:3200]);del buffer[:3200]
        elif buffer:  # RecognizeStream flush marker
            yield bytes(buffer);buffer.clear()
    if buffer:yield bytes(buffer)


async def clocked_pcm(source):
    """Preserve input and advance ASR time through Opus DTX/muted gaps."""
    buffer=bytearray();ended=False
    async def collect():
        nonlocal ended
        async for frame in source:
            if not isinstance(frame,rtc.AudioFrame):continue
            if frame.num_channels!=1 or frame.sample_rate!=16000:raise ValueError('ASR requires 16 kHz mono')
            buffer.extend(bytes(frame.data))
            if len(buffer)>64000:raise RuntimeError('ASR input fell behind by over two seconds')
        ended=True
    producer=asyncio.create_task(collect());loop=asyncio.get_running_loop();deadline=loop.time()+.1
    try:
        while True:
            await asyncio.sleep(max(0,deadline-loop.time()))
            if producer.done():producer.result()
            if ended and not buffer:return
            packet=bytes(buffer[:3200]);del buffer[:len(packet)]
            yield packet.ljust(3200,b'\0')
            deadline=max(deadline+.1,loop.time())
    finally:
        producer.cancel();await asyncio.gather(producer,return_exceptions=True)


class ProxyStream(stt.RecognizeStream):
    async def _run(self):
        backend=self._stt.backend
        url=backend.url.replace('https://','wss://',1).replace('http://','ws://',1)+'/internal/voice-calls/'+backend.call_id+'/listen'
        tasks=[]
        async with aiohttp.ClientSession(trust_env=False) as client:
            async with client.ws_connect(url,headers=backend.headers,heartbeat=10,max_msg_size=128*1024) as ws:
                ready=await asyncio.wait_for(ws.receive_json(),20)
                if ready.get('type')!='ready': raise RuntimeError('ASR unavailable')
                async def send():
                    async for data in clocked_pcm(self._input_ch):await ws.send_bytes(data)
                async def receive():
                    seen=set()
                    async for message in ws:
                        if message.type!=aiohttp.WSMsgType.TEXT: raise RuntimeError('ASR disconnected')
                        data=json.loads(message.data);kind=data.get('type')
                        if kind=='error': raise RuntimeError('ASR connection ended')
                        if kind not in {'interim','final'}: continue
                        text=data.get('text','')
                        identifier=data.get('sentence_id','')
                        if kind=='final':
                            if identifier in seen: continue
                            seen.add(identifier)
                            if len(seen)>10000: raise RuntimeError('ASR turn limit')
                            if self._stt.on_final:self._stt.on_final(text)
                        self._event_ch.send_nowait(stt.SpeechEvent(
                            type=stt.SpeechEventType.FINAL_TRANSCRIPT if kind=='final' else stt.SpeechEventType.INTERIM_TRANSCRIPT,
                            alternatives=[stt.SpeechData(language='zh',text=text)]))
                tasks=[asyncio.create_task(send()),asyncio.create_task(receive())]
                try:
                    done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                    for task in done:task.result()
                finally:
                    for task in tasks:task.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)


class CallController:
    """One active response. Late network results cannot speak after a barge-in."""
    def __init__(self,backend,session,publish):
        self.backend=backend;self.session=session;self.publish=publish
        self.turn_id='';self.task=None;self.closed=False
        self.interrupt_tasks=set()
        self.cancelled_tasks=set()

    def interrupt(self):
        old=self.turn_id;self.turn_id=''
        if self.task:
            old_task=self.task;old_task.cancel();self.task=None
            self.cancelled_tasks.add(old_task)
            old_task.add_done_callback(self.cancelled_tasks.discard)
        try:self.session.interrupt(force=True)
        except RuntimeError:
            if not self.closed:raise
        if old:
            async def cancel_remote():
                try:await self.backend.request('POST','/interrupt',json={'turn_id':old})
                except httpx.HTTPError:pass
            task=asyncio.create_task(cancel_remote());self.interrupt_tasks.add(task)
            task.add_done_callback(self.interrupt_tasks.discard)

    def question(self,text):
        if self.closed or not text.strip():return
        self.interrupt();turn=uuid4().hex;self.turn_id=turn
        self.task=asyncio.create_task(self.respond(text,turn))

    def manual_interrupt(self,turn_id):
        if self.closed or not turn_id or turn_id != self.turn_id:return False
        self.interrupt();return True

    async def respond(self,text,turn):
        try:
            await self.publish({'type':'question','turn_id':turn,'text':text})
            await self.publish({'type':'state','turn_id':turn,'state':'thinking'})
            answer=await self.backend.request('POST','/answers',json={'question':text,'turn_id':turn})
            if self.closed or self.turn_id!=turn:return
            await self.publish({'type':'answer','turn_id':turn,'answer':answer})
            if answer['stale'] or answer['response_type']=='UNKNOWN':
                await self.publish({'type':'state','turn_id':turn,'state':'listening'});return
            await self.publish({'type':'state','turn_id':turn,'state':'speaking'})
            audio=self.backend.frames(answer['answer_id'],turn)
            try:
                handle=self.session.say(answer['answer'],audio=audio,allow_interruptions=True,add_to_chat_ctx=False)
            except Exception:
                await audio.aclose();raise
            # LiveKit's forwarding task owns and closes this iterator, including
            # on interruption. Closing it here races that task while it is reading.
            await handle
            if handle.exception() is not None:raise RuntimeError('Validated answer audio failed')
            if self.turn_id==turn:
                await self.publish({'type':'state','turn_id':turn,'state':'listening'})
        except asyncio.CancelledError:raise
        except Exception:
            if not self.closed and self.turn_id==turn:
                await self.publish({'type':'error','turn_id':turn,'message':'本轮语音回答未完成，可以重新说或结束通话。'})

    async def close(self):
        self.closed=True;self.interrupt()
        await asyncio.gather(*self.interrupt_tasks,*self.cancelled_tasks,return_exceptions=True)


server=AgentServer()


@server.rtc_session(agent_name='remember-twin')
async def entrypoint(ctx: JobContext):
    private_logs()
    metadata=json.loads(ctx.job.metadata)
    call_id=metadata['call_id']
    if not isinstance(call_id,str) or not call_id.startswith('vc_') or len(call_id)>64:raise ValueError('Invalid call')
    backend=Backend(os.environ['REMEMBER_REALTIME_BACKEND_URL'],os.environ['REMEMBER_REALTIME_WORKER_SECRET'],call_id)
    authorized=await backend.request('GET','/authorize')
    if ctx.job.room.name!=authorized['room']:raise ValueError('Room mismatch')
    await ctx.connect()
    # Manual turn submission prevents any generic LLM from bypassing Backend validation.
    # VAD still emits speaking events: those immediately clear LiveKit's audio queue.
    recognizer=ProxySTT(backend)
    session=AgentSession(stt=recognizer,vad=silero.VAD.load(),
        turn_handling={'turn_detection':'manual','interruption':{'enabled':True,'mode':'vad','resume_false_interruption':False}})
    async def publish(data):
        await ctx.room.local_participant.publish_data(json.dumps(data,ensure_ascii=False).encode(),reliable=True,
            destination_identities=[authorized['participant_identity']],topic=TOPIC)
    controller=CallController(backend,session,publish)
    # Manual SDK turns can suppress later transcript events after speech. Consume
    # the authenticated final transcript directly; SDK retains its VAD/audio role.
    recognizer.on_final=controller.question
    @session.on('user_state_changed')
    def user_state(event):
        if event.new_state=='speaking':controller.interrupt()
    @ctx.room.on('data_received')
    def command(packet):
        if packet.topic!=TOPIC or not packet.participant or packet.participant.identity!=authorized['participant_identity']:return
        try: data=json.loads(packet.data)
        except (ValueError,UnicodeError):return
        if data.get('type')=='interrupt':controller.manual_interrupt(data.get('turn_id'))
    @session.on('error')
    def error(event):
        if not event.error.recoverable:asyncio.create_task(session.aclose())
    @session.on('close')
    def closed(event):
        controller.closed=True
    await session.start(room=ctx.room,agent=Agent(instructions='只播放 Remember Me 后端已校验的孪生回答。'),
        room_options=room_io.RoomOptions(participant_identity=authorized['participant_identity'],text_input=False,text_output=False,delete_room_on_close=True),record=False)
    await publish({'type':'state','state':'listening'})
    async def monitor():
        try:
            while True:
                await asyncio.sleep(1)
                await backend.request('GET','/authorize')
        except httpx.HTTPError:
            controller.interrupt()
            await publish({'type':'ended','message':'授权已变化、服务不可用或通话已到期。'})
            await session.aclose()
            await ctx.room.disconnect()
    watchdog=asyncio.create_task(monitor())
    async def shutdown():
        watchdog.cancel();await asyncio.gather(watchdog,return_exceptions=True)
        await controller.close()
        try:await backend.request('POST','/end')
        except httpx.HTTPError:pass
        await backend.client.aclose()
    ctx.add_shutdown_callback(shutdown)


if __name__=='__main__':cli.run_app(server)

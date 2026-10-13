"""LiveKit transport/turn handling around Remember Me's validated Twin API.

No generic voice LLM, provider key, sample or actor credential in this worker.
"""
import asyncio
import json
import os
import logging
import re
import array
import socket
import ssl
import ipaddress
from urllib.parse import urlsplit
from uuid import uuid4
import aiohttp
import httpx
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, stt, APIConnectionError, APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, room_io
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
        self.client=httpx.AsyncClient(timeout=httpx.Timeout(120,connect=8),follow_redirects=False,trust_env=False)
        self.diagnostic_requests=0

    async def connection_trace(self):
        """Opt-in transport stages only; never log headers, URLs or payloads."""
        if os.environ.get('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS')!='1' or self.diagnostic_requests>=2:
            return None
        self.diagnostic_requests+=1
        loop=asyncio.get_running_loop();started=loop.time()
        logger=logging.getLogger(__name__);host=urlsplit(self.url).hostname
        def record(phase,**safe):
            logger.info('Realtime connection diagnostic',extra={'phase':phase,
                'elapsed_ms':round((loop.time()-started)*1000),'target_host':host,**safe})
        try:
            addresses=await asyncio.wait_for(loop.getaddrinfo(host,443,type=socket.SOCK_STREAM),1)
            record('dns.complete',addresses=sorted({item[4][0] for item in addresses})[:8])
        except Exception as exc:record('dns.failed',error_type=type(exc).__name__)
        async def trace(event,info):
            if not any(part in event for part in ('connect_tcp','start_tls','send_request_headers','receive_response_headers')):
                return
            safe={}
            if event.endswith('.failed'):safe['error_type']=type(info.get('exception')).__name__
            stream=info.get('return_value')
            if event in {'connection.connect_tcp.complete','connection.start_tls.complete'} and hasattr(stream,'get_extra_info'):
                peer=stream.get_extra_info('server_addr')
                if peer:safe['peer_address']=str(peer[0])
            record(event,**safe)
        return trace

    async def request(self,method,path,**kwargs):
        if path=='/authorize':
            trace=await self.connection_trace()
            if trace:kwargs['extensions']={**kwargs.get('extensions',{}),'trace':trace}
        response=await self.client.request(method,self.url+'/internal/voice-calls/'+self.call_id+path,headers=self.headers,**kwargs)
        response.raise_for_status();return response.json()

    async def authorize_startup(self):
        # Only the read-only startup authorization may retry a failed connection.
        # Bound the whole attempt as well as HTTPX's individual I/O phases.
        for attempt in range(2):
            try:
                return await asyncio.wait_for(self.request('GET','/authorize',
                    timeout=httpx.Timeout(10,connect=8)),10)
            except (httpx.ConnectTimeout,httpx.ConnectError):
                if attempt==1:raise

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
        super().__init__(capabilities=stt.STTCapabilities(streaming=True,interim_results=False))
        self.backend=backend
        self.on_final=None
        self.ready=asyncio.Event()
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


async def clocked_pcm(source, *, live_after=None):
    """Batch incoming PCM promptly; advance ASR time only during input gaps.

    RTC can deliver a queued burst while the ASR socket is opening. Pacing that
    burst a second time grows the queue and can terminate an otherwise healthy
    call. Keep one pending read, preserving partial frames across normal jitter.
    """
    buffer=bytearray();iterator=source.__aiter__();pending=None
    loop=asyncio.get_running_loop();deadline=loop.time()+.1
    try:
        while True:
            if pending is None:pending=asyncio.create_task(iterator.__anext__())
            done,_=await asyncio.wait({pending},timeout=max(0,deadline-loop.time()))
            if done:
                try:frame=pending.result()
                except StopAsyncIteration:
                    if buffer:yield bytes(buffer).ljust(3200,b'\0')
                    return
                pending=None
                if isinstance(frame,rtc.AudioFrame):
                    if frame.num_channels!=1 or frame.sample_rate!=16000:raise ValueError('ASR requires 16 kHz mono')
                    captured=frame.userdata.get('remember_received_at')
                    if live_after is not None and captured is not None and captured>=live_after and loop.time()-captured>2:
                        raise ValueError('Realtime microphone audio fell behind')
                    buffer.extend(bytes(frame.data))
                    while len(buffer)>=3200:
                        packet=bytes(buffer[:3200]);del buffer[:3200]
                        deadline=loop.time()+.1
                        yield packet
                elif buffer:
                    packet=bytes(buffer).ljust(3200,b'\0');buffer.clear();deadline=loop.time()+.1
                    yield packet
            else:
                packet=bytes(buffer).ljust(3200,b'\0');buffer.clear();deadline=loop.time()+.1
                yield packet
    finally:
        if pending:
            pending.cancel();await asyncio.gather(pending,return_exceptions=True)


async def send_pcm(ws, data, *, timeout=2):
    try:await asyncio.wait_for(ws.send_bytes(data),timeout)
    except asyncio.TimeoutError:
        # Ending this call is safer than eventually submitting stale queued speech.
        raise ValueError('Realtime microphone transport fell behind') from None


def pcm_has_speech(data):
    samples=array.array('h',data)
    return bool(samples) and sum(value*value for value in samples)/len(samples)>200*200


async def wait_recognition_ready(recognizer,recognition,*,timeout=20):
    waiting=asyncio.create_task(recognizer.ready.wait())
    try:
        done,_=await asyncio.wait({waiting,recognition},timeout=timeout,return_when=asyncio.FIRST_COMPLETED)
        if recognition in done:
            await recognition
            raise RuntimeError('Microphone recognition ended before ready')
        if waiting not in done:raise TimeoutError('Realtime recognition startup timed out')
    finally:
        waiting.cancel();await asyncio.gather(waiting,return_exceptions=True)


class ProxyStream(stt.RecognizeStream):
    async def _run(self):
        try:await self._connection()
        except (aiohttp.ClientError,asyncio.TimeoutError,RuntimeError):
            # Recheck the live owner/grants before the SDK's bounded reconnect.
            # Consumed PCM is never replayed; only subsequent live input remains.
            await self._stt.backend.request('GET','/authorize')
            raise APIConnectionError('Realtime recognition transport unavailable') from None

    async def _connection(self):
        backend=self._stt.backend
        url=backend.url.replace('https://','wss://',1).replace('http://','ws://',1)+'/internal/voice-calls/'+backend.call_id+'/listen'
        diagnostic=os.environ.get('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS')=='1'
        loop=asyncio.get_running_loop();started=loop.time()
        def handshake(phase):
            if diagnostic:logging.getLogger(__name__).info('Realtime ASR handshake',extra={
                'phase':phase,'elapsed_ms':round((loop.time()-started)*1000)})
        tasks=[]
        handshake('connecting')
        async with aiohttp.ClientSession(trust_env=False) as client:
            async with client.ws_connect(url,headers=backend.headers,heartbeat=10,max_msg_size=128*1024,compress=15) as ws:
                handshake('connected')
                ready=await asyncio.wait_for(ws.receive_json(),20)
                if ready.get('type')!='ready': raise RuntimeError('ASR unavailable')
                self._stt.ready.set();handshake('ready')
                if not hasattr(self,'_audio_live_after'):self._audio_live_after=asyncio.get_running_loop().time()
                counters={'pcm_bytes':0,'heartbeat_count':0,'final_count':0,'final_events':0,'send_stall_max_ms':0,'compression_bits':ws.compress};opened=asyncio.get_running_loop().time()
                if diagnostic:counters['speech_packet_count']=0
                async def send():
                    async for data in clocked_pcm(self._input_ch,live_after=self._audio_live_after):
                        before=asyncio.get_running_loop().time()
                        await send_pcm(ws,data);counters['pcm_bytes']+=len(data)
                        if diagnostic and pcm_has_speech(data):counters['speech_packet_count']+=1
                        counters['send_stall_max_ms']=max(counters['send_stall_max_ms'],round((asyncio.get_running_loop().time()-before)*1000))
                async def receive():
                    seen=set()
                    async for message in ws:
                        if message.type!=aiohttp.WSMsgType.TEXT: raise RuntimeError('ASR disconnected')
                        data=json.loads(message.data);kind=data.get('type')
                        if kind=='error': raise RuntimeError('ASR connection ended')
                        if kind=='heartbeat':counters['heartbeat_count']+=1
                        if kind not in {'interim','final'}: continue
                        text=data.get('text','')
                        identifier=data.get('sentence_id','')
                        if kind=='final':
                            counters['final_events']+=1
                            if identifier in seen: continue
                            seen.add(identifier);counters['final_count']+=1
                            if len(seen)>10000: raise RuntimeError('ASR turn limit')
                            if self._stt.on_final:self._stt.on_final(text)
                        self._event_ch.send_nowait(stt.SpeechEvent(
                            type=stt.SpeechEventType.FINAL_TRANSCRIPT if kind=='final' else stt.SpeechEventType.INTERIM_TRANSCRIPT,
                            alternatives=[stt.SpeechData(language='zh',text=text)]))
                    raise RuntimeError('ASR socket closed code='+str(ws.close_code))
                tasks=[asyncio.create_task(send(),name='asr-send'),asyncio.create_task(receive(),name='asr-receive')]
                try:
                    done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                    for task in done:task.result()
                finally:
                    for task in tasks:task.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
                    logging.getLogger(__name__).info('Realtime ASR transport summary',extra={
                        **counters,'audio_seconds':round(counters['pcm_bytes']/32000,1),
                        'wall_seconds':round(asyncio.get_running_loop().time()-opened,1),'close_code':ws.close_code})


async def listen_microphone(recognizer, participant):
    """Keep recognition on the owner's RTC microphone across playout/interrupts."""
    audio=rtc.AudioStream.from_participant(participant=participant,
        track_source=rtc.TrackSource.SOURCE_MICROPHONE,sample_rate=16000,num_channels=1)
    stream=recognizer.stream()
    diagnostic=os.environ.get('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS')=='1'
    counts={'mic_input_frame_count':0,'mic_input_speech_frame_count':0}
    async def feed():
        async for event in audio:
            if diagnostic:
                counts['mic_input_frame_count']+=1
                if pcm_has_speech(bytes(event.frame.data)):counts['mic_input_speech_frame_count']+=1
            event.frame.userdata['remember_received_at']=asyncio.get_running_loop().time()
            stream.push_frame(event.frame)
        stream.end_input()
    async def drain():
        async for _ in stream:pass  # ProxyStream submits authenticated finals directly.
    tasks=[asyncio.create_task(feed()),asyncio.create_task(drain())]
    try:
        done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done:task.result()
        raise RuntimeError('Microphone recognition ended')
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if diagnostic:logging.getLogger(__name__).info('Realtime microphone input summary',extra=counts)
        await stream.aclose();await audio.aclose()


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


async def connect_authorized(ctx,backend):
    try:
        authorized=await backend.authorize_startup()
        if ctx.job.room.name!=authorized['room']:raise ValueError('Room mismatch')
        await ctx.connect()
        return authorized
    except BaseException:
        try:await backend.client.aclose()
        except Exception:pass
        raise


async def probe_backend_endpoints(url):
    """Operator-only empty-room diagnostic. No credential is sent on probes."""
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname:raise ValueError('HTTPS diagnostic target required')
    host=parsed.hostname;loop=asyncio.get_running_loop()
    records=await asyncio.wait_for(loop.getaddrinfo(host,443,family=socket.AF_INET,type=socket.SOCK_STREAM),5)
    resolved=sorted({item[4][0] for item in records})
    controls=os.environ.get('REMEMBER_REALTIME_DIAGNOSTIC_IPS','').split(',')
    addresses=list(dict.fromkeys(resolved+[value for value in controls if value]))[:6]
    logger=logging.getLogger(__name__)
    for address in addresses:
        ip=ipaddress.ip_address(address)
        if ip.version!=4 or not ip.is_global:raise ValueError('Only public IPv4 diagnostic addresses are allowed')
        began=loop.time();phase='tcp';sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM);sock.setblocking(False);writer=None
        result={'target_host':host,'address':address,'from_dns':address in resolved}
        try:
            await asyncio.wait_for(loop.sock_connect(sock,(address,443)),5)
            result['tcp_ms']=round((loop.time()-began)*1000);phase='tls'
            reader,writer=await asyncio.wait_for(asyncio.open_connection(sock=sock,
                ssl=ssl.create_default_context(),server_hostname=host),5)
            result['tls_ms']=round((loop.time()-began)*1000);phase='http'
            writer.write(('GET /health HTTP/1.1\r\nHost: '+host+'\r\nConnection: close\r\n\r\n').encode())
            await writer.drain()
            header=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),8)
            result['status']=int(header.split(b' ',2)[1])
        except Exception as exc:result.update(failure_phase=phase,error_type=type(exc).__name__)
        finally:
            if writer:
                writer.close()
                try:await asyncio.wait_for(writer.wait_closed(),1)
                except Exception:pass
            else:sock.close()
        result['elapsed_ms']=round((loop.time()-began)*1000)
        logger.info('Realtime endpoint diagnostic',extra=result)


def agent_name():
    name=os.environ.get('REMEMBER_LIVEKIT_AGENT_NAME','remember-twin')
    if len(name)>64 or re.fullmatch(r'[A-Za-z0-9_.-]+',name) is None:
        raise ValueError('Invalid LiveKit agent name')
    return name


server=AgentServer()


@server.rtc_session(agent_name=agent_name())
async def entrypoint(ctx: JobContext):
    private_logs()
    metadata=json.loads(ctx.job.metadata)
    call_id=metadata['call_id']
    if not isinstance(call_id,str) or not call_id.startswith('vc_') or len(call_id)>64:raise ValueError('Invalid call')
    if os.environ.get('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS')=='1' and metadata.get('network_probe') is True:
        await asyncio.wait_for(probe_backend_endpoints(os.environ['REMEMBER_REALTIME_BACKEND_URL']),55)
        return
    backend=Backend(os.environ['REMEMBER_REALTIME_BACKEND_URL'],os.environ['REMEMBER_REALTIME_WORKER_SECRET'],call_id)
    authorized=await connect_authorized(ctx,backend)
    # Manual turn submission prevents any generic LLM from bypassing Backend validation.
    # VAD still emits speaking events: those immediately clear LiveKit's audio queue.
    recognizer=ProxySTT(backend)
    session=AgentSession(vad=silero.VAD.load(),
        turn_handling={'turn_detection':'manual','interruption':{'enabled':True,'mode':'vad','resume_false_interruption':False}})
    async def publish(data):
        await ctx.room.local_participant.publish_data(json.dumps(data,ensure_ascii=False).encode(),reliable=True,
            destination_identities=[authorized['participant_identity']],topic=TOPIC)
    controller=CallController(backend,session,publish)
    # Recognition owns a separate microphone reader. SDK manual turn/playout
    # lifecycle must not gate the next user utterance; SDK retains VAD/playout.
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
    participant=await ctx.wait_for_participant(identity=authorized['participant_identity'])
    async def recognize():
        try:await listen_microphone(recognizer,participant)
        except asyncio.CancelledError:raise
        except Exception as exc:
            reason=str(exc) if str(exc) in {'ASR unavailable','ASR disconnected','ASR connection ended','Microphone recognition ended'} or str(exc).startswith('ASR socket closed code=') else type(exc).__name__
            logging.getLogger(__name__).warning('Realtime recognition stopped: %s',reason)
            controller.interrupt()
            await publish({'type':'ended','message':'实时识别连接已结束，请重新发起通话。'})
            await session.aclose()
    recognition=asyncio.create_task(recognize())
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
    cleanup_task=None
    async def cleanup():
        watchdog.cancel();recognition.cancel()
        await asyncio.gather(watchdog,recognition,return_exceptions=True)
        try:
            await controller.close()
            try:await backend.request('POST','/end')
            except httpx.HTTPError:pass
        finally:await backend.client.aclose()
    async def shutdown():
        nonlocal cleanup_task
        if cleanup_task is None:cleanup_task=asyncio.create_task(cleanup())
        await asyncio.shield(cleanup_task)
    ctx.add_shutdown_callback(shutdown)
    try:
        await wait_recognition_ready(recognizer,recognition)
        if controller.closed:raise RuntimeError('Microphone recognition ended before ready')
        await publish({'type':'state','state':'listening'})
    except BaseException:
        try:
            if not controller.closed:
                controller.interrupt()
                await publish({'type':'ended','message':'实时识别尚未就绪，请重新发起通话。'})
            await session.aclose()
        finally:await shutdown()
        raise


if __name__=='__main__':cli.run_app(server)

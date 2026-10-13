import asyncio
import httpx
import pytest
from agent import Backend, CallController, ProxySTT


class Session:
    def __init__(self):self.spoken=[];self.interruptions=0
    def interrupt(self,**kwargs):self.interruptions+=1
    def say(self,text,**kwargs):
        self.spoken.append(text)
        future=asyncio.get_running_loop().create_future();future.set_result(None);return future


class API:
    def __init__(self):self.pending={};self.cancelled=[];self.audio=[]
    async def request(self,method,path,**kwargs):
        payload=kwargs.get('json',{})
        if path=='/interrupt':self.cancelled.append(payload['turn_id']);return {}
        future=asyncio.get_running_loop().create_future();self.pending[payload['question']]=future
        # Deliberately emulate an upstream that completes even after cancellation.
        try:return await asyncio.shield(future)
        except asyncio.CancelledError:return await future
    async def frames(self,answer_id,turn_id):
        self.audio.append((answer_id,turn_id))
        if False:yield None


def answer(text,kind='SIMULATION'):
    return {'answer_id':'answer-'+text,'answer':text,'response_type':kind,'stale':False}


async def settle():
    for _ in range(4):await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_barge_in_discards_late_reply_even_when_upstream_ignores_cancel():
    api=API();session=Session();events=[]
    async def publish(data):events.append(data)
    controller=CallController(api,session,publish)
    controller.question('old');await settle();old_turn=controller.turn_id
    controller.interrupt();controller.question('new');await settle()
    api.pending['old'].set_result(answer('old'));api.pending['new'].set_result(answer('new'));await settle()
    assert session.spoken==['new']
    assert old_turn in api.cancelled
    assert [e['answer']['answer'] for e in events if e['type']=='answer']==['new']
    await controller.close()


@pytest.mark.asyncio
async def test_unknown_answer_is_visible_but_never_impersonated():
    api=API();session=Session();events=[]
    async def publish(data):events.append(data)
    controller=CallController(api,session,publish)
    controller.question('unknown');await settle();api.pending['unknown'].set_result(answer('unknown','UNKNOWN'));await settle()
    assert not session.spoken and not api.audio
    assert any(e['type']=='answer' for e in events)
    await controller.close()


@pytest.mark.asyncio
async def test_hangup_discards_inflight_answer_and_blocks_new_questions():
    api=API();session=Session();events=[]
    async def publish(data):events.append(data)
    controller=CallController(api,session,publish)
    controller.question('old');await settle()
    closing=asyncio.create_task(controller.close());await settle()
    api.pending['old'].set_result(answer('old'));await closing
    controller.question('new');await settle()
    assert not session.spoken and 'new' not in api.pending


@pytest.mark.asyncio
async def test_pcm_packets_preserve_odd_network_boundaries_and_reject_truncation():
    backend=Backend('https://fixture.invalid','x'*32,'vc_fixture')
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'\x01';yield b'\x00'*959;yield b'\x02\x00'
    def reply(request):return httpx.Response(200,headers={'content-type':'audio/pcm','X-Audio-Sample-Rate':'24000'},stream=Stream())
    await backend.client.aclose();backend.client=httpx.AsyncClient(transport=httpx.MockTransport(reply))
    frames=[frame async for frame in backend.frames('ta_fixture','turn')]
    assert [f.samples_per_channel for f in frames]==[480,1]
    assert bytes(frames[0].data).startswith(b'\x01\x00')
    await backend.client.aclose()


def test_worker_refuses_remote_plain_http_or_missing_service_key():
    with pytest.raises(ValueError):Backend('http://public.invalid','x'*32,'vc_fixture')
    with pytest.raises(ValueError):Backend('https://fixture.invalid','short','vc_fixture')


@pytest.mark.asyncio
async def test_network_diagnostics_are_opt_in_bounded_and_exclude_http_contents(monkeypatch,caplog):
    import logging,json
    backend=Backend('https://fixture.invalid','diagnostic-secret-not-for-logs'*2,'vc_fixture')
    assert await backend.connection_trace() is None
    monkeypatch.setenv('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS','1')
    async def addresses(*args,**kwargs):return [(None,None,None,None,('192.0.2.1',443))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',addresses)
    with caplog.at_level(logging.INFO):
        trace=await backend.connection_trace()
        await trace('http11.receive_response_headers.complete',{'return_value':(b'HTTP/1.1',403,b'Forbidden',
            [(b'authorization',b'diagnostic-secret-not-for-logs'),(b'set-cookie',b'private-cookie')])})
        await trace('http11.send_request_body.complete',{'body':'private-transcript'})
        assert await backend.connection_trace() is not None
        assert await backend.connection_trace() is None
    serialized=json.dumps([vars(record) for record in caplog.records],default=str)
    assert 'dns.complete' in serialized and 'receive_response_headers.complete' in serialized
    assert all(secret not in serialized for secret in ['diagnostic-secret-not-for-logs','private-cookie','private-transcript'])
    await backend.client.aclose()


def test_worker_agent_name_defaults_without_configuration(monkeypatch):
    from agent import agent_name
    monkeypatch.delenv('REMEMBER_LIVEKIT_AGENT_NAME',raising=False)
    assert agent_name()=='remember-twin'


@pytest.mark.parametrize('name',['remember-twin-us','Agent_0.'+'-'*56])
def test_worker_agent_name_reads_valid_dispatch_configuration(name,monkeypatch):
    from agent import agent_name
    monkeypatch.setenv('REMEMBER_LIVEKIT_AGENT_NAME',name)
    assert agent_name()==name


@pytest.mark.parametrize('name',['','has space','name/route','中文','a'*65,'name\n'])
def test_worker_agent_name_rejects_invalid_configuration(name,monkeypatch):
    from agent import agent_name
    monkeypatch.setenv('REMEMBER_LIVEKIT_AGENT_NAME',name)
    with pytest.raises(ValueError,match='Invalid LiveKit agent name'):agent_name()


@pytest.mark.asyncio
@pytest.mark.parametrize('connection_error',[httpx.ConnectTimeout,httpx.ConnectError])
async def test_startup_authorization_retries_only_connection_failures_before_rtc(connection_error):
    from types import SimpleNamespace
    from agent import connect_authorized
    backend=Backend('https://fixture.invalid','x'*32,'vc_fixture')
    assert backend.client.timeout.connect==8 and backend.client.timeout.read==120
    await backend.client.aclose()
    events=[]
    async def reply(request):
        assert request.method=='GET' and request.url.path.endswith('/authorize')
        assert request.extensions['timeout']['connect']==8
        assert request.extensions['timeout']['read']==10
        events.append('authorize')
        if len(events)==1:raise connection_error('fixture connection failure',request=request)
        return httpx.Response(200,json={'room':'fixture-room'})
    backend.client=httpx.AsyncClient(transport=httpx.MockTransport(reply))
    async def connect():events.append('connect')
    ctx=SimpleNamespace(job=SimpleNamespace(room=SimpleNamespace(name='fixture-room')),connect=connect)
    try:
        assert await connect_authorized(ctx,backend)=={'room':'fixture-room'}
        assert events==['authorize','authorize','connect'] and not backend.client.is_closed
    finally:await backend.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[401,403])
async def test_startup_authorization_denial_is_not_retried_and_releases_client(status):
    from types import SimpleNamespace
    from agent import connect_authorized
    backend=Backend('https://fixture.invalid','x'*32,'vc_fixture');await backend.client.aclose()
    attempts=[];connections=[]
    def reply(request):
        attempts.append(request.method)
        return httpx.Response(status)
    backend.client=httpx.AsyncClient(transport=httpx.MockTransport(reply))
    async def connect():connections.append(True)
    ctx=SimpleNamespace(job=SimpleNamespace(room=SimpleNamespace(name='fixture-room')),connect=connect)
    with pytest.raises(httpx.HTTPStatusError) as error:await connect_authorized(ctx,backend)
    assert error.value.response.status_code==status
    assert attempts==['GET'] and not connections and backend.client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,expected_attempts',[(httpx.ConnectTimeout,2),(httpx.ReadTimeout,1)])
async def test_startup_transport_failure_is_bounded_and_releases_client(failure,expected_attempts):
    from types import SimpleNamespace
    from agent import connect_authorized
    backend=Backend('https://fixture.invalid','x'*32,'vc_fixture');await backend.client.aclose()
    attempts=[];connections=[]
    def reply(request):
        attempts.append(request.method)
        raise failure('fixture transport failure',request=request)
    backend.client=httpx.AsyncClient(transport=httpx.MockTransport(reply))
    async def connect():connections.append(True)
    ctx=SimpleNamespace(job=SimpleNamespace(room=SimpleNamespace(name='fixture-room')),connect=connect)
    with pytest.raises(failure):await connect_authorized(ctx,backend)
    assert len(attempts)==expected_attempts and not connections and backend.client.is_closed


@pytest.mark.asyncio
async def test_startup_whole_attempt_timeout_is_not_retried_and_releases_client(monkeypatch):
    from types import SimpleNamespace
    import agent
    backend=Backend('https://fixture.invalid','x'*32,'vc_fixture');await backend.client.aclose()
    attempts=[];connections=[];budgets=[]
    async def reply(request):
        attempts.append(request.method)
        await asyncio.Event().wait()
    backend.client=httpx.AsyncClient(transport=httpx.MockTransport(reply))
    wait_for=asyncio.wait_for
    async def short_fixture_budget(operation,timeout):
        budgets.append(timeout)
        return await wait_for(operation,.01)
    monkeypatch.setattr(agent.asyncio,'wait_for',short_fixture_budget)
    async def connect():connections.append(True)
    ctx=SimpleNamespace(job=SimpleNamespace(room=SimpleNamespace(name='fixture-room')),connect=connect)
    with pytest.raises(TimeoutError):await agent.connect_authorized(ctx,backend)
    assert attempts==['GET'] and budgets==[10] and not connections and backend.client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['room_mismatch','rtc_connect'])
async def test_startup_room_or_rtc_failure_releases_client_after_authorization(failure):
    from types import SimpleNamespace
    from agent import connect_authorized
    backend=Backend('https://fixture.invalid','x'*32,'vc_fixture');await backend.client.aclose()
    events=[]
    def reply(request):
        events.append('authorize')
        return httpx.Response(200,json={'room':'fixture-room'})
    backend.client=httpx.AsyncClient(transport=httpx.MockTransport(reply))
    async def connect():
        events.append('connect')
        raise RuntimeError('fixture RTC failure')
    room='wrong-room' if failure=='room_mismatch' else 'fixture-room'
    ctx=SimpleNamespace(job=SimpleNamespace(room=SimpleNamespace(name=room)),connect=connect)
    expected=ValueError if failure=='room_mismatch' else RuntimeError
    with pytest.raises(expected):await connect_authorized(ctx,backend)
    assert events==(['authorize'] if failure=='room_mismatch' else ['authorize','connect'])
    assert backend.client.is_closed


@pytest.mark.asyncio
async def test_delayed_manual_interrupt_cannot_cancel_the_new_turn():
    api=API();session=Session();events=[]
    async def publish(data):events.append(data)
    controller=CallController(api,session,publish)
    controller.question('old');await settle();old=controller.turn_id
    controller.question('new');await settle();new=controller.turn_id;count=session.interruptions
    assert not controller.manual_interrupt(old)
    assert not controller.manual_interrupt(None)
    assert controller.turn_id==new and session.interruptions==count
    api.pending['old'].set_result(answer('old'));api.pending['new'].set_result(answer('new'));await settle()
    assert session.spoken==['new']
    assert controller.manual_interrupt(new)
    await controller.close()


@pytest.mark.asyncio
async def test_shutdown_still_cleans_up_after_livekit_already_stopped():
    class Stopped(Session):
        def interrupt(self,**kwargs):raise RuntimeError('AgentSession is not running')
    api=API()
    async def publish(data):pass
    controller=CallController(api,Stopped(),publish);controller.turn_id='completed-turn'
    await controller.close()
    assert controller.closed and api.cancelled==['completed-turn']


@pytest.mark.asyncio
async def test_asr_batches_preserve_samples_and_flush_partial_audio():
    from agent import pcm_chunks
    from livekit import rtc
    original=b''.join(bytes([i,0])*320 for i in range(7))
    async def source():
        for i in range(7):
            yield rtc.AudioFrame(data=original[i*640:(i+1)*640],sample_rate=16000,num_channels=1,samples_per_channel=320)
    chunks=[data async for data in pcm_chunks(source())]
    assert [len(data) for data in chunks]==[3200,1280]
    assert b''.join(chunks)==original


@pytest.mark.asyncio
async def test_audio_failure_hidden_by_speech_handle_is_visible_to_user():
    class FailedHandle:
        def __await__(self):
            async def done():return self
            return done().__await__()
        def exception(self):return RuntimeError('fixture audio failed')
    class FailedAudio(Session):
        def say(self,*args,**kwargs):return FailedHandle()
    api=API();events=[]
    async def publish(data):events.append(data)
    controller=CallController(api,FailedAudio(),publish)
    controller.question('test');await settle();api.pending['test'].set_result(answer('test'));await settle()
    assert any(e['type']=='error' for e in events)
    assert not any(e.get('state')=='listening' for e in events)
    await controller.close()


def test_sdk_warning_extras_do_not_persist_private_transcripts():
    import logging
    from agent import PrivateLogFilter
    record=logging.makeLogRecord({'msg':'transcript timeout','levelno':logging.WARNING,
        'lk.pii.interim_transcript':'private user sentence','lk.pii.user_input':'another private sentence',
        'lk.pii.participant_identity':'private participant','region':'ap-south'})
    assert PrivateLogFilter().filter(record)
    assert all(v=='[redacted]' for k,v in vars(record).items() if k.startswith('lk.pii.'))
    assert record.region=='ap-south' and record.getMessage()=='transcript timeout'


@pytest.mark.asyncio
async def test_clocked_asr_advances_silence_without_losing_partial_frames():
    from agent import clocked_pcm
    from livekit import rtc
    original=b'\x03\x00'*160
    async def source():
        yield rtc.AudioFrame(data=original,sample_rate=16000,num_channels=1,samples_per_channel=160)
        await asyncio.sleep(.35)
    packets=[data async for data in clocked_pcm(source())]
    assert len(packets)>=3 and all(len(p)==3200 for p in packets)
    assert packets[0].startswith(original) and packets[0][len(original):]==b'\0'*(3200-len(original))
    assert all(p==b'\0'*3200 for p in packets[1:])


@pytest.mark.asyncio
async def test_asr_startup_burst_is_drained_without_retiming_or_dropping_samples():
    from agent import clocked_pcm
    from livekit import rtc
    original=b''.join(bytes([i % 120 + 1,0])*320 for i in range(160))
    async def source():
        for pos in range(0,len(original),640):
            yield rtc.AudioFrame(data=original[pos:pos+640],sample_rate=16000,num_channels=1,samples_per_channel=320)
    async with asyncio.timeout(1):
        packets=[packet async for packet in clocked_pcm(source())]
    assert b''.join(packets)==original and all(len(p)==3200 for p in packets)


@pytest.mark.asyncio
async def test_independent_microphone_reader_releases_both_streams_on_asr_failure(monkeypatch):
    from types import SimpleNamespace
    from agent import listen_microphone
    from livekit import rtc
    arrived=asyncio.Event();closed=[]
    class Microphone:
        def __aiter__(self):return self.frames()
        async def frames(self):
            yield SimpleNamespace(frame=rtc.AudioFrame(data=b'\0'*640,sample_rate=16000,num_channels=1,samples_per_channel=320))
            await asyncio.Event().wait()
        async def aclose(self):closed.append('microphone')
    class Recognition:
        def push_frame(self,frame):arrived.set()
        def __aiter__(self):return self.events()
        async def events(self):
            await arrived.wait()
            raise RuntimeError('fixture service disconnect')
            yield
        async def aclose(self):closed.append('recognition')
    monkeypatch.setattr(rtc.AudioStream,'from_participant',lambda **kwargs:Microphone())
    async with asyncio.timeout(1):
        with pytest.raises(RuntimeError,match='fixture service disconnect'):
            await listen_microphone(SimpleNamespace(stream=lambda:Recognition()),object())
    assert sorted(closed)==['microphone','recognition']


@pytest.mark.asyncio
async def test_asr_transport_failure_is_nonretryable_and_clears_ready(monkeypatch):
    from types import SimpleNamespace
    from agent import ProxyStream
    from livekit.agents import APIConnectionError
    checks=[]
    async def dropped(self):raise RuntimeError('ASR socket closed code=1000')
    async def authorized(method,path):checks.append((method,path));return {}
    monkeypatch.setattr(ProxyStream,'_connection',dropped)
    ready=asyncio.Event();ready.set()
    stream=object.__new__(ProxyStream);stream._stt=SimpleNamespace(backend=SimpleNamespace(request=authorized),ready=ready)
    with pytest.raises(APIConnectionError,match='transport unavailable') as error:await stream._run()
    assert checks==[] and not ready.is_set() and not error.value.retryable


@pytest.mark.asyncio
async def test_revoked_call_is_not_reconnected(monkeypatch):
    from types import SimpleNamespace
    from agent import ProxyStream
    from livekit.agents import APIConnectionError
    async def dropped(self):raise RuntimeError('ASR connection ended')
    async def denied(method,path):
        response=httpx.Response(403,request=httpx.Request('GET','https://fixture.invalid/authorize'))
        response.raise_for_status()
    monkeypatch.setattr(ProxyStream,'_connection',dropped)
    stream=object.__new__(ProxyStream);stream._stt=SimpleNamespace(backend=SimpleNamespace(request=denied),ready=asyncio.Event())
    with pytest.raises(APIConnectionError) as error:await stream._run()
    assert not error.value.retryable


@pytest.mark.asyncio
async def test_silence_clock_does_not_add_transport_wait_to_each_audio_interval():
    from agent import clocked_pcm
    from livekit import rtc
    async def source():
        yield rtc.AudioFrame(data=b'\0'*320,sample_rate=16000,num_channels=1,samples_per_channel=160)
        await asyncio.sleep(.55)
    count=0
    async for packet in clocked_pcm(source()):
        count+=1
        await asyncio.sleep(.12)  # Model a transport send that takes over 100 ms.
    assert count>=4  # A second 100 ms sleep after every send only emits three.


@pytest.mark.asyncio
async def test_stalled_audio_send_ends_instead_of_reconnecting_with_a_backlog():
    from agent import send_pcm
    class StalledSocket:
        async def send_bytes(self,data):await asyncio.Event().wait()
    with pytest.raises(ValueError,match='transport fell behind'):
        await send_pcm(StalledSocket(),b'\0'*3200,timeout=.01)


@pytest.mark.asyncio
async def test_old_live_microphone_frames_are_not_submitted_after_a_stall():
    from agent import clocked_pcm
    from livekit import rtc
    now=asyncio.get_running_loop().time()
    async def source():
        yield rtc.AudioFrame(data=b'\0'*3200,sample_rate=16000,num_channels=1,samples_per_channel=1600,
            userdata={'remember_received_at':now-3})
    with pytest.raises(ValueError,match='audio fell behind'):
        async for _ in clocked_pcm(source(),live_after=now-10):pytest.fail('Stale audio forwarded')


@pytest.mark.asyncio
async def test_listening_gate_waits_for_delayed_asr_ready():
    from types import SimpleNamespace
    from agent import wait_recognition_ready
    recognizer=SimpleNamespace(ready=asyncio.Event())
    recognition=asyncio.create_task(asyncio.Event().wait())
    waiting=asyncio.create_task(wait_recognition_ready(recognizer,recognition,timeout=.2))
    try:
        await settle();assert not waiting.done()
        recognizer.ready.set();await waiting
        assert not recognition.done()
    finally:
        recognition.cancel();await asyncio.gather(recognition,return_exceptions=True)


@pytest.mark.asyncio
async def test_recognition_failure_wins_over_ready_signal():
    from types import SimpleNamespace
    from agent import wait_recognition_ready
    recognizer=SimpleNamespace(ready=asyncio.Event())
    async def stopped():
        recognizer.ready.set()
        raise ValueError('fixture ASR failure')
    recognition=asyncio.create_task(stopped())
    with pytest.raises(ValueError,match='fixture ASR failure'):
        await wait_recognition_ready(recognizer,recognition,timeout=.2)


@pytest.mark.asyncio
async def test_recognition_ready_timeout_preserves_reader_for_caller_cleanup():
    from types import SimpleNamespace
    from agent import wait_recognition_ready
    recognizer=SimpleNamespace(ready=asyncio.Event())
    recognition=asyncio.create_task(asyncio.Event().wait())
    try:
        with pytest.raises(TimeoutError,match='startup timed out'):
            await wait_recognition_ready(recognizer,recognition,timeout=.01)
        assert not recognizer.ready.is_set() and not recognition.done()
    finally:
        recognition.cancel();await asyncio.gather(recognition,return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('response_kind',['ready','error'])
async def test_backend_handshake_controls_ready_and_logs_only_stages_and_speech_counts(response_kind,monkeypatch,caplog):
    import json,logging
    from types import SimpleNamespace
    import agent
    from livekit import rtc
    monkeypatch.setenv('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS','1')
    gate=asyncio.Event();connected=asyncio.Event();sent=asyncio.Event();packets=[]
    class Socket:
        compress=15;close_code=1000
        async def receive_json(self):
            connected.set();await gate.wait();return {'type':response_kind}
        async def send_bytes(self,data):
            packets.append(len(data))
            if len(packets)>=2:sent.set()
        def __aiter__(self):return self.messages()
        async def messages(self):
            await sent.wait()
            if False:yield None
    class SocketContext:
        async def __aenter__(self):return Socket()
        async def __aexit__(self,*args):return False
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        def ws_connect(self,*args,**kwargs):return SocketContext()
    async def frames():
        for value in [300,0]:
            data=value.to_bytes(2,'little',signed=True)*1600
            yield rtc.AudioFrame(data=data,sample_rate=16000,num_channels=1,samples_per_channel=1600)
        await asyncio.Event().wait()
    backend=SimpleNamespace(url='https://fixture.invalid',call_id='vc_private_fixture',headers={'Authorization':'Bearer private-fixture'})
    recognizer=SimpleNamespace(backend=backend,ready=asyncio.Event())
    stream=object.__new__(agent.ProxyStream);stream._stt=recognizer;stream._input_ch=frames()
    monkeypatch.setattr(agent.aiohttp,'ClientSession',Client)
    caplog.set_level(logging.INFO,logger='agent')
    running=asyncio.create_task(stream._connection())
    await connected.wait();assert not recognizer.ready.is_set()
    gate.set()
    with pytest.raises(RuntimeError):await running
    phases=[record.phase for record in caplog.records if record.getMessage()=='Realtime ASR handshake']
    assert phases==(['connecting','connected','ready'] if response_kind=='ready' else ['connecting','connected'])
    assert not recognizer.ready.is_set()  # A closed socket is never ready.
    if response_kind=='ready':
        summary=next(record for record in caplog.records if record.getMessage()=='Realtime ASR transport summary')
        assert summary.speech_packet_count==1 and summary.pcm_bytes==6400
    serialized=json.dumps([vars(record) for record in caplog.records],default=str)
    assert 'private-fixture' not in serialized and 'vc_private_fixture' not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize('diagnostic',[False,True])
async def test_microphone_diagnostics_count_speech_without_recording_audio(diagnostic,monkeypatch,caplog):
    import logging
    from types import SimpleNamespace
    from agent import listen_microphone
    from livekit import rtc
    monkeypatch.setenv('REMEMBER_REALTIME_NETWORK_DIAGNOSTICS','1' if diagnostic else '0')
    arrived=asyncio.Event();closed=[]
    class Microphone:
        def __aiter__(self):return self.frames()
        async def frames(self):
            for value in [0,300]:
                frame=rtc.AudioFrame(data=value.to_bytes(2,'little',signed=True)*320,sample_rate=16000,num_channels=1,samples_per_channel=320)
                yield SimpleNamespace(frame=frame)
            arrived.set();await asyncio.Event().wait()
        async def aclose(self):closed.append('microphone')
    class Recognition:
        def push_frame(self,frame):pass
        def __aiter__(self):return self.events()
        async def events(self):
            await arrived.wait();raise RuntimeError('fixture disconnect')
            yield
        async def aclose(self):closed.append('recognition')
    monkeypatch.setattr(rtc.AudioStream,'from_participant',lambda **kwargs:Microphone())
    caplog.set_level(logging.INFO,logger='agent')
    with pytest.raises(RuntimeError,match='fixture disconnect'):
        await listen_microphone(SimpleNamespace(stream=lambda:Recognition()),object())
    summaries=[record for record in caplog.records if record.getMessage()=='Realtime microphone input summary']
    assert len(summaries)==int(diagnostic)
    if diagnostic:assert summaries[0].mic_input_frame_count==2 and summaries[0].mic_input_speech_frame_count==1
    assert sorted(closed)==['microphone','recognition']


def test_diagnostic_pcm_threshold_excludes_silence_and_boundary_level():
    from agent import pcm_has_speech
    assert not pcm_has_speech(b'') and not pcm_has_speech(b'\0'*640)
    assert not pcm_has_speech((200).to_bytes(2,'little',signed=True)*320)
    assert pcm_has_speech((-201).to_bytes(2,'little',signed=True)*320)


@pytest.mark.asyncio
async def test_entrypoint_ready_timeout_has_registered_cleanup_and_never_publishes_false_listening(monkeypatch):
    import json
    from types import SimpleNamespace
    import agent
    callbacks=[];published=[];ended=[];closed=[];reader_stopped=[]
    class Client:
        async def aclose(self):closed.append(True)
    class BackendFixture:
        def __init__(self,*args):self.client=Client()
        async def authorize_startup(self):return {'room':'fixture-room','participant_identity':'fixture-owner'}
        async def request(self,method,path,**kwargs):
            if path=='/end':ended.append(True)
            return {}
    class Recognizer:
        def __init__(self,backend):self.ready=asyncio.Event();self.on_final=None
    class NativeSession:
        def __init__(self,**kwargs):self.handlers={}
        def on(self,event):
            def register(callback):self.handlers[event]=callback;return callback
            return register
        async def start(self,**kwargs):pass
        def interrupt(self,**kwargs):pass
        async def aclose(self):self.handlers['close'](None)
    class Room:
        def __init__(self):self.local_participant=self
        def on(self,event):return lambda callback:callback
        async def publish_data(self,value,**kwargs):published.append(json.loads(value))
    class Context:
        def __init__(self):self.room=Room();self.job=SimpleNamespace(metadata='{"call_id":"vc_fixture"}',room=SimpleNamespace(name='fixture-room'))
        async def connect(self):pass
        async def wait_for_participant(self,**kwargs):return object()
        def add_shutdown_callback(self,callback):callbacks.append(callback)
    async def microphone(*args):
        try:await asyncio.Event().wait()
        finally:reader_stopped.append(True)
    original_wait=agent.wait_recognition_ready
    async def short_startup(recognizer,recognition):
        assert len(callbacks)==1 and not recognition.done()
        await original_wait(recognizer,recognition,timeout=.01)
    monkeypatch.setenv('REMEMBER_REALTIME_BACKEND_URL','https://fixture.invalid')
    monkeypatch.setenv('REMEMBER_REALTIME_WORKER_SECRET','x'*32)
    monkeypatch.setattr(agent,'Backend',BackendFixture);monkeypatch.setattr(agent,'ProxySTT',Recognizer)
    monkeypatch.setattr(agent,'AgentSession',NativeSession);monkeypatch.setattr(agent.silero.VAD,'load',lambda:None)
    monkeypatch.setattr(agent,'listen_microphone',microphone);monkeypatch.setattr(agent,'wait_recognition_ready',short_startup)
    with pytest.raises(TimeoutError):await agent.entrypoint(Context())
    assert published==[{'type':'ended','message':'实时识别尚未就绪，请重新发起通话。'}]
    assert reader_stopped==[True] and ended==[True] and closed==[True]
    await callbacks[0]()
    assert ended==[True] and closed==[True]  # SDK shutdown cannot clean up twice.


def test_segment_diagnostics_observe_third_burst_after_65_seconds(caplog):
    import logging,json
    from agent import SegmentDiagnostics
    now=[0.0];trace=SegmentDiagnostics(True,clock=lambda:now[0])
    caplog.set_level(logging.INFO,logger='agent')
    speech=(300).to_bytes(2,'little',signed=True)*1600
    for at in [0,2,69]:
        now[0]=at
        trace.observe('rtc_worker_receive',speech)
        trace.observe('asr_send',speech)
        now[0]=at+.7
        trace.observe('rtc_worker_receive',b'\0'*3200)
        trace.observe('asr_send',b'\0'*3200)
    records=[record for record in caplog.records if record.getMessage()=='Realtime segment diagnostic']
    for stage in ['rtc_worker_receive','asr_send']:
        assert [r.segment for r in records if r.stage==stage+'.start']==[1,2,3]
        third=next(r for r in records if r.stage==stage+'.end' and r.segment==3)
        assert third.packets==1 and third.pcm_bytes==3200 and third.elapsed_ms==69700
    trace.mark('twin_answer',turn_number=3,transcript='private text',token='private-token',pcm=speech)
    assert all(value not in json.dumps([vars(r) for r in caplog.records],default=str)
               for value in ['private text','private-token'])


def test_disabled_segment_diagnostics_never_read_energy_or_log(monkeypatch,caplog):
    import agent
    monkeypatch.setattr(agent,'pcm_has_speech',lambda data:pytest.fail('Disabled diagnostics read audio'))
    trace=agent.SegmentDiagnostics(False)
    trace.observe('asr_send',b'private-pcm');trace.mark('twin_answer',turn_number=1)
    assert not trace.stages and not caplog.records


@pytest.mark.asyncio
async def test_proxy_stt_disables_sdk_reconnect_and_attempts_only_once(monkeypatch):
    from types import SimpleNamespace
    from agent import ProxySTT,ProxyStream
    from livekit.agents import APIConnectOptions,APIConnectionError
    attempts=[]
    async def disconnected(self):
        attempts.append(1);raise RuntimeError('ASR disconnected')
    recognizer=ProxySTT(SimpleNamespace());recognizer.ready.set()
    monkeypatch.setattr(ProxyStream,'_connection',disconnected)
    stream=recognizer.stream(conn_options=APIConnectOptions(max_retry=5,timeout=.01))
    stream.push_frame(__import__('livekit').rtc.AudioFrame.create(sample_rate=16000,num_channels=1,samples_per_channel=320))
    with pytest.raises(APIConnectionError):
        async for _ in stream:pass
    assert attempts==[1] and stream._conn_options.max_retry==0 and not recognizer.ready.is_set()
    await stream.aclose()

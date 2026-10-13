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
async def test_asr_transport_reconnect_requires_fresh_authorization(monkeypatch):
    from types import SimpleNamespace
    from agent import ProxyStream
    from livekit.agents import APIConnectionError
    checks=[]
    async def dropped(self):raise RuntimeError('ASR socket closed code=1000')
    async def authorized(method,path):checks.append((method,path));return {}
    monkeypatch.setattr(ProxyStream,'_connection',dropped)
    stream=object.__new__(ProxyStream);stream._stt=SimpleNamespace(backend=SimpleNamespace(request=authorized))
    with pytest.raises(APIConnectionError,match='transport unavailable'):await stream._run()
    assert checks==[('GET','/authorize')]


@pytest.mark.asyncio
async def test_revoked_call_is_not_reconnected(monkeypatch):
    from types import SimpleNamespace
    from agent import ProxyStream
    async def dropped(self):raise RuntimeError('ASR connection ended')
    async def denied(method,path):
        response=httpx.Response(403,request=httpx.Request('GET','https://fixture.invalid/authorize'))
        response.raise_for_status()
    monkeypatch.setattr(ProxyStream,'_connection',dropped)
    stream=object.__new__(ProxyStream);stream._stt=SimpleNamespace(backend=SimpleNamespace(request=denied))
    with pytest.raises(httpx.HTTPStatusError):await stream._run()


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

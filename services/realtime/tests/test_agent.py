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

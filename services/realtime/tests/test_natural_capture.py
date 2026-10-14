import asyncio,io,wave
from natural_capture import MicrophoneClip
import pytest
class Backend:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    async def request(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        if self.fail:raise RuntimeError('fixture upload unavailable')
        return {'status':'uploaded'}
@pytest.mark.asyncio
async def test_disabled_capture_no_silence_sample_and_bounded_microphone_only_payload():
    b=Backend();c=MicrophoneClip(b);c.feed(b'\x01\0'*100000,True);c.finish('t');assert not b.calls
    c=MicrophoneClip(b,True);c.feed(bytes(400000),False);assert not c.pcm
    c.feed(b'\x01\0'*500000,True);assert len(c.pcm)==480000
    c.finish('t');await asyncio.gather(*c.tasks)
    args,k=b.calls[0];assert args==('POST','/samples') and k['data']=={'turn_id':'t'}
    with wave.open(io.BytesIO(k['files']['sample'][1])) as w:assert w.getnchannels()==1 and w.getnframes()==240000
    assert not c.pcm
@pytest.mark.asyncio
async def test_upload_failure_does_not_raise_or_block_turn_and_close_clears_audio():
    b=Backend(True);c=MicrophoneClip(b,True);c.feed(bytes(200000),True);c.finish('t');await asyncio.gather(*c.tasks);assert b.calls
    c.feed(bytes(200000),True);c.close();assert not c.enabled and not c.pcm


@pytest.mark.asyncio
async def test_short_normal_utterances_accumulate_without_waiting_silence_or_recitation():
    b=Backend();c=MicrophoneClip(b,True)
    c.feed(bytes(80000),True);c.finish('first');assert not b.calls and len(c.pcm)==80000
    c.feed(bytes(320000),False);assert len(c.pcm)==80000
    c.feed(bytes(90000),True);c.finish('second');await asyncio.gather(*c.tasks)
    with wave.open(io.BytesIO(b.calls[0][1]['files']['sample'][1])) as w:assert w.getnframes()==85000
    assert not c.pcm

@pytest.mark.asyncio
async def test_voice_identity_keeps_each_turn_separate_and_does_not_accumulate_guests():
    from natural_capture import UtteranceClip
    b=Backend();c=UtteranceClip(b,True)
    c.feed(b'\x01\0'*20000,True);c.finish('one')
    c.feed(bytes(32000),False)
    c.feed(b'\x02\0'*30000,True);c.finish('two')
    await asyncio.gather(*c.tasks)
    assert [x[1]['data']['turn_id'] for x in b.calls]==['one','two']
    assert all(x[0]==('POST','/utterances') for x in b.calls)
    for index,(_,kwargs) in enumerate(b.calls):
        with wave.open(io.BytesIO(kwargs['files']['sample'][1])) as f:
            assert f.readframes(f.getnframes())==(b'\x01\0'*20000 if index==0 else b'\x02\0'*30000)
    c.close();assert not c.pcm

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr


def test_provider_uses_fresh_text_input_session_and_native_pcm(monkeypatch):
    from app.step_realtime import StepRealtimeSpeech
    import websockets.asyncio.client
    sent=[]; connections=[]
    frames=[{'type':'session.created'}, {'type':'session.updated'},
        {'type':'response.created','response':{'id':'r1'}},
        {'type':'response.audio_transcript.delta','response_id':'r1','delta':'喜欢淡茶。'},
        {'type':'response.audio.delta','response_id':'r1','delta':base64.b64encode(b'\0\0'*240).decode()},
        {'type':'response.done','response':{'id':'r1','status':'completed'}}]
    class Socket:
        def __init__(self):self.frames=iter(frames)
        async def send(self,value):sent.append(json.loads(value))
        async def recv(self):return json.dumps(next(self.frames))
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
    def connect(*a,**kw):connections.append((a,kw));return Socket()
    monkeypatch.setattr(websockets.asyncio.client,'connect',connect)
    async def run():
        provider=StepRealtimeSpeech(SimpleNamespace(step_realtime_api_key=SecretStr('test')))
        packet={'question':'喝什么茶？','mode':'evidence','candidates':[], 'source_version':'v1'}
        for _ in range(2):
            events=[e async for e in provider.stream(packet)]
            assert [e['type'] for e in events]==['text','pcm','done']
            assert events[1]['data']==b'\0\0'*240
    asyncio.run(run())
    assert len(connections)==2
    update=next(e for e in sent if e['type']=='session.update')['session']
    assert update['turn_detection'] is None
    assert update['output_audio_format']=='pcm16'
    assert not any(e['type']=='input_audio_buffer.append' for e in sent)
    assert sum(e['type']=='response.create' for e in sent)==2


def test_turn_revocation_blocks_late_pcm_and_never_saves_a_twin_answer():
    from app.step_realtime import RealtimeVoiceTurns
    from app.api.twin import SourceChanged
    async def run():
        events=[]; valid=True
        async def send(e):events.append(e)
        async def guard():
            if not valid:raise SourceChanged('changed')
        async def prepare(q,h):return {'question':q,'evidence':[],'source_version':'v1'}
        class Provider:
            async def stream(self,packet,**kwargs):
                nonlocal valid
                yield {'type':'text','text':'回答'}
                valid=False
                yield {'type':'pcm','data':b'\0\0'*240}
        turns=RealtimeVoiceTurns('s',send,prepare,Provider(),guard)
        await turns.submit('问题');await turns.task
        assert not any(e['type']=='audio' for e in events)
        assert events[-1]['type']=='error' and events[-1]['stop_playback']
        assert turns.current is None
        await turns.close()
    asyncio.run(run())


def test_interruption_excludes_unheard_reply_and_rejects_late_chunks():
    from app.step_realtime import RealtimeVoiceTurns
    async def run():
        events=[]; first=asyncio.Event(); release=asyncio.Event(); seen=[]
        async def send(e):events.append(e)
        async def guard():pass
        async def prepare(q,h):seen.append(h);return {'question':q,'evidence':[],'source_version':'v1'}
        class Provider:
            async def stream(self,p,**kwargs):
                yield {'type':'text','text':'已生成但还没听完'}
                yield {'type':'pcm','data':b'\0\0'*240}
                if p['question']=='旧问题':
                    first.set()
                    try:await release.wait()
                    except asyncio.CancelledError:pass
                    yield {'type':'pcm','data':b'\1\0'*240}
                yield {'type':'done'}
        turns=RealtimeVoiceTurns('s',send,prepare,Provider(),guard)
        await turns.submit('旧问题');await first.wait()
        old=turns.turn_id
        await turns.submit('新问题');await turns.task
        assert seen[-1][0]['heard_answer']=='' and seen[-1][0]['interrupted']
        assert len([e for e in events if e['type']=='audio' and e['turn_id']==old])==1
        assert turns.current.get('answer') is None
        await turns.close()
    asyncio.run(run())


def test_provider_disconnect_is_error_and_next_question_can_recover():
    from app.step_realtime import RealtimeVoiceTurns
    async def run():
        events=[]
        async def send(e):events.append(e)
        async def guard():pass
        async def prepare(q,h):return {'question':q,'evidence':[],'source_version':'v1'}
        class Provider:
            async def stream(self,p,**kwargs):
                if p['question']=='第一次':raise ConnectionError('upstream closed')
                yield {'type':'text','text':'有依据的回答'}
                yield {'type':'pcm','data':b'\0\0'*240}
                yield {'type':'done'}
        turns=RealtimeVoiceTurns('s',send,prepare,Provider(),guard)
        await turns.submit('第一次');await turns.task
        assert events[-1]['type']=='error' and events[-1]['stop_playback']
        assert not any(e['type']=='answer_ready' for e in events)
        await turns.submit('下一次');await turns.task
        assert events[-1]['type']=='audio_end' and turns.history==[]
        await turns.close()
    asyncio.run(run())

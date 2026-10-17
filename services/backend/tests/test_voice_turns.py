import asyncio
import pytest
from app.voice_turns import VoiceTurns, conversation_control


def test_social_controls_cannot_answer_embedded_memory_questions():
    assert conversation_control('你好，可以和我聊聊吗？')
    assert conversation_control('谢谢！') == 'thanks'
    assert conversation_control('你好。') == 'greeting'
    assert conversation_control('你好，我女儿叫什么？') is None
    assert conversation_control('谢谢，你最喜欢什么？') is None


def test_prepared_tts_never_reaches_client_if_answer_review_fails():
    async def run():
        events=[];produced=asyncio.Event();closed=asyncio.Event()
        async def tts(text):
            try:
                produced.set();yield b'ab'
                await asyncio.Event().wait()
            finally:closed.set()
        async def answer(q,h,prepare):
            await prepare('错误草稿。')
            await produced.wait()
            raise RuntimeError('review rejected')
        async def send(e):events.append(e)
        async def guard(a=None):pass
        call=VoiceTurns('s',send,answer,tts,guard,prepare_audio=True)
        await call.submit('真实问题');await call.task
        assert produced.is_set() and closed.is_set()
        assert not any(e['type'] in {'audio','answer_ready'} for e in events)
        assert events[-1]['type']=='error'
        await call.close()
    asyncio.run(run())


def test_revoked_draft_is_not_sent_to_tts():
    async def run():
        events=[];synthesized=[];allowed=True
        async def tts(text):
            synthesized.append(text);yield b'ab'
        async def answer(q,h,prepare):
            nonlocal allowed
            allowed=False
            await prepare('已经撤权的草稿。')
            await asyncio.sleep(0)
            return {'answer':'已经撤权的草稿。','answer_id':'old'}
        async def guard(a=None):
            if not allowed:raise RuntimeError('revoked')
        async def send(e):events.append(e)
        call=VoiceTurns('s',send,answer,tts,guard,prepare_audio=True)
        await call.submit('真实问题');await call.task
        assert synthesized==[]
        assert not any(e['type'] in {'audio','answer_ready'} for e in events)
        await call.close()
    asyncio.run(run())


def test_source_whitespace_is_not_submitted_as_a_spoken_sentence():
    async def run():
        calls=[];events=[]
        async def answer(q,h): return {'answer':'我喜欢淡茶。\n\n','answer_id':'a'}
        async def tts(text):
            assert text.strip()
            calls.append(text);yield bytes(20)
        async def send(e):events.append(e)
        async def guard(a=None):pass
        call=VoiceTurns('s',send,answer,tts,guard)
        await call.submit('喝什么？');await call.task
        assert events[-1]['type']=='audio_end'
        assert calls==['我喜欢淡茶。']
    asyncio.run(run())


def test_cancelled_generation_and_audio_cannot_publish():
    async def run():
        events=[]; gate=asyncio.Event()
        async def answer(q,h):
            try: await gate.wait()
            except asyncio.CancelledError: pass  # deliberately misbehaving late provider
            return {'answer':'旧答案。','answer_id':'old','source_version':'v1'}
        async def tts(text): yield b'\0\0'*20
        async def send(e): events.append(e)
        async def check(answer=None): pass
        call=VoiceTurns('session',send,answer,tts,check)
        await call.submit('旧问题'); await asyncio.sleep(0)
        await call.interrupt(); gate.set(); await asyncio.sleep(.01)
        assert not any(e['type'] in {'answer_ready','audio'} for e in events)
        await call.close()
    asyncio.run(run())


def test_history_contains_only_completed_played_sentences():
    async def run():
        events=[]; histories=[]
        async def answer(q,h):
            histories.append(h)
            return {'answer':'先检查原因。也要听家人的意见。','answer_id':'a','source_version':'v1'}
        async def tts(text): yield b'\0\0'*100
        async def send(e): events.append(e)
        async def check(answer=None): pass
        call=VoiceTurns('s',send,answer,tts,check)
        await call.submit('怎么修？'); await call.task
        turn=call.turn_id
        call.playback(turn,150)
        await call.interrupt()
        await call.submit('为什么？'); await call.task
        assert histories[-1] == [{'question':'怎么修？','heard_answer':'先检查原因。','interrupted':True}]
        with pytest.raises(ValueError): call.playback(call.turn_id,99999)
        call.playback(turn,200)  # old ack cannot mark current answer heard
        assert call.played==0
        await call.close()
    asyncio.run(run())


def test_source_change_stops_audio_and_clears_history():
    async def run():
        events=[]; changed=False
        async def answer(q,h): return {'answer':'原来的话。','answer_id':'a','source_version':'v1'}
        async def tts(text):
            nonlocal changed
            yield b'\0\0'*10
            changed=True
            yield b'\0\0'*10
        async def send(e): events.append(e)
        async def check(answer=None):
            if changed: raise RuntimeError('revoked')
        call=VoiceTurns('s',send,answer,tts,check)
        await call.submit('问题'); await call.task
        assert len([e for e in events if e['type']=='audio'])==1
        assert events[-1]['type']=='error'
        assert call.history==[]
        await call.close()
    asyncio.run(run())


def test_audio_checks_do_not_bypass_memory_questions():
    for q in ['喂，你好，你能听到我说的话吗？','能听见我说话吗？','你听得到吗？']:
        assert conversation_control(q)=='audio_check'
    for q in ['你以前听到我说什么？','你好，你叫什么名字？','你能听到我说话吗？我爱喝什么茶？']:
        assert conversation_control(q) is None


def test_hesitation_remains_part_of_the_next_sentence():
    from app.voice_turns import UtteranceBuffer
    b=UtteranceBuffer()
    assert b.final('嗯，') is None
    assert b.final('我想问一下，') is None
    assert b.display('你喜欢什么茶')=='嗯，我想问一下，你喜欢什么茶'
    assert b.final('你喜欢什么茶？')=='嗯，我想问一下，你喜欢什么茶？'
    assert b.pending==''

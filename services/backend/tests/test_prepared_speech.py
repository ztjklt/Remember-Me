import asyncio
import pytest


def test_prepared_audio_is_inaccessible_before_exact_final_answer_and_discards_changed_draft():
    from app.prepared_speech import PreparedSpeech
    async def run():
        sent=[]
        async def tts(text):
            sent.append(text);yield text.encode()
        speech=PreparedSpeech(tts)
        await speech.prepare('旧回答。后一句。')
        await asyncio.sleep(0)
        assert sent==['旧回答。']
        output=[chunk async for chunk in speech.stream('新回答。')]
        assert output==['新回答。'.encode()]
        assert sent==['旧回答。','新回答。']
        await speech.close()
    asyncio.run(run())


def test_exact_reviewed_first_sentence_reuses_preparation_and_close_cancels_waiting_provider():
    from app.prepared_speech import PreparedSpeech
    async def run():
        count=[];closed=asyncio.Event()
        async def tts(text):
            count.append(text)
            try:
                yield b'ab'
                await asyncio.Event().wait()
            finally:closed.set()
        speech=PreparedSpeech(tts)
        await speech.prepare('完整一句。另一句。')
        iterator=speech.stream('完整一句。')
        assert await anext(iterator)==b'ab'
        assert count==['完整一句。']
        await speech.close();await iterator.aclose()
        assert closed.is_set()
    asyncio.run(run())

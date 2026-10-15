import asyncio
from app.prepared_speech import PreparedSpeech


def test_same_first_sentence_does_not_restart_inflight_synthesis():
    async def run():
        calls=[]
        async def tts(text):calls.append(text);yield b'ab'
        speech=PreparedSpeech(tts)
        await speech.prepare('我喜欢淡茶。')
        first=speech.task
        await speech.prepare('我喜欢淡茶。后来口味没变。')
        assert speech.task is first
        assert b''.join([p async for p in speech.stream('我喜欢淡茶。')])==b'ab'
        assert calls==['我喜欢淡茶。']
    asyncio.run(run())


def test_material_cache_never_shares_mutated_traits_or_authorization():
    from app.voice_material_cache import VoiceMaterialCache
    cache=VoiceMaterialCache()
    key=('actor','subject','consent','local','v1',('e1',))
    cache.put(key,{'candidates':[{'traits':[]}]})
    loaded=cache.get(key);loaded['candidates'][0]['traits'].append('derived')
    assert cache.get(key)['candidates'][0]['traits']==[]
    for i in range(len(key)):
        changed=list(key);changed[i]='different'
        assert cache.get(tuple(changed)) is None
    cache.clear();assert cache.get(key) is None


def test_wrong_predicted_speech_is_never_released():
    async def run():
        async def tts(text):yield text.encode()
        speech=PreparedSpeech(tts)
        await speech.prepare('不相关的原话。')
        output=b''.join([p async for p in speech.stream('最终选择的原话。')])
        assert output=='最终选择的原话。'.encode()
        assert speech.task is None
    asyncio.run(run())


def test_endpoint_silence_is_only_faster_in_explicit_streamed_mode():
    from app.realtime_providers import endpoint_silence
    assert endpoint_silence(False,'streamed')==400
    assert endpoint_silence(False,'fast')==800
    assert endpoint_silence(False,'reviewed')==800
    assert endpoint_silence(True,'streamed')==1400


def test_tts_client_is_reused_until_call_closes(monkeypatch):
    from app.realtime_providers import XiaomiRealtime
    from types import SimpleNamespace
    import httpx
    from pydantic import SecretStr
    created=[];closed=[]
    original=httpx.AsyncClient
    class Client(original):
        async def aclose(self):closed.append(self);await super().aclose()
    def factory(**kw):
        instance=Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,text='data: {"choices":[{"delta":{"audio":{"data":"AQI="}}}]}\n\ndata: [DONE]\n\n')),**kw)
        created.append(instance);return instance
    monkeypatch.setattr(httpx,'AsyncClient',factory)
    async def run():
        tts=XiaomiRealtime(SimpleNamespace(xiaomi_voice_base_url='https://api.xiaomimimo.com/v1',xiaomi_voice_api_key=SecretStr('test')))
        for _ in range(2):assert [p async for p in tts.stream('一句话。')]==[b'\x01\x02']
        assert len(created)==1 and not closed
        await tts.close();assert len(closed)==1
    asyncio.run(run())


def test_audio_reuse_is_exact_bounded_and_never_retains_failed_stream():
    from app.realtime_providers import XiaomiRealtime
    from types import SimpleNamespace
    from pydantic import SecretStr
    import pytest
    async def run():
        tts=XiaomiRealtime(SimpleNamespace(xiaomi_voice_base_url='https://api.xiaomimimo.com/v1',xiaomi_voice_api_key=SecretStr('test')))
        tts.cache_enabled=True;calls=[]
        async def source(text):
            calls.append(text);yield b'12'
            if text=='failed':raise RuntimeError('truncated')
        tts._stream_uncached=source
        for text in ('first','first','different'):
            assert [x async for x in tts.stream(text)]==[b'12']
        assert calls==['first','different']
        with pytest.raises(RuntimeError):[x async for x in tts.stream('failed')]
        assert 'failed' not in tts.audio_cache
        for i in range(12):[x async for x in tts.stream(str(i))]
        assert len(tts.audio_cache)<=8 and tts.cached_bytes<=2_000_000
        await tts.close();assert not tts.audio_cache
    asyncio.run(run())

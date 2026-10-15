import asyncio
import pytest

@pytest.fixture
def anyio_backend():return 'asyncio'


@pytest.mark.anyio
async def test_prefetch_debounces_and_never_uses_changed_final_question():
    from app.voice_prefetch import VoicePrefetch
    seen=[]
    async def prepare(q,h,check):check();seen.append((q,h))
    p=VoicePrefetch(prepare,delay=.01)
    p.offer('以前喜欢喝浓茶',[]);p.offer('以前喜欢喝浓茶，现在不喜欢',[])
    await asyncio.sleep(.04)
    assert seen==[('以前喜欢喝浓茶，现在不喜欢',[])]
    await p.close()


@pytest.mark.anyio
async def test_prefetch_can_close_without_late_tasks_or_model_dispatch():
    from app.voice_prefetch import VoicePrefetch
    seen=[]
    async def prepare(q,h,check):check();seen.append(q)
    p=VoicePrefetch(prepare,delay=.02)
    p.offer('我的家人说过什么',[]);await p.close();await asyncio.sleep(.04)
    assert not seen


@pytest.mark.anyio
async def test_running_prefetch_observes_close_before_more_work():
    from threading import Event
    from app.voice_prefetch import VoicePrefetch
    started=Event();release=Event();finished=Event();seen=[]
    async def prepare(q,h,check):
        def work():
            started.set();release.wait(2)
            try:check();seen.append('late database work')
            except Exception:seen.append('cancelled')
            finally:finished.set()
        await asyncio.to_thread(work)
    p=VoicePrefetch(prepare,delay=.001);p.offer('请讲讲公交工作的故事',[])
    assert await asyncio.to_thread(started.wait,1)
    await p.close();release.set()
    assert await asyncio.to_thread(finished.wait,1)
    assert seen==['cancelled']


def test_selection_cache_keeps_question_negation_history_identity_and_version():
    from app.voice_prefetch import SelectionCache
    c=SelectionCache();key=('subject','owner','consent','v1')
    c.put(key,'他喜欢浓茶',{'sources':{'s1':{'text':'过去喜欢，但后来不喜欢。'}}})
    assert c.get(key,'他喜欢浓茶')['sources']['s1']['text'].endswith('不喜欢。')
    assert c.get(key,'他不喜欢浓茶') is None
    assert c.get(('subject','reader','consent','v1'),'他喜欢浓茶') is None
    assert c.get(('subject','owner','consent','v2'),'他喜欢浓茶') is None

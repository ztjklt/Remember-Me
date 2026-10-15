import asyncio
import pytest
from app.errors import ProviderRateLimited, ProviderTimeout
from functools import wraps


def run_async(function):
    @wraps(function)
    def run(): return asyncio.run(function())
    return run


@run_async
async def test_slow_primary_uses_one_backup_and_cancels_loser():
    from app.providers.voice_race import bounded_race
    calls=[]; closed=[]
    async def attempt(number):
        calls.append(number)
        try:
            await asyncio.sleep(.2 if number==1 else .005)
            return number
        finally: closed.append(number)
    result=await bounded_race(attempt,delay=.01,timeout=.1)
    assert result==2 and calls==[1,2] and set(closed)=={1,2}


@run_async
async def test_fast_primary_does_not_make_an_extra_billable_call():
    from app.providers.voice_race import bounded_race
    calls=[]
    async def attempt(number): calls.append(number); return number
    assert await bounded_race(attempt,delay=.1,timeout=.2)==1
    assert calls==[1]


@run_async
async def test_rate_limit_does_not_trigger_backup():
    from app.providers.voice_race import bounded_race
    calls=[]
    async def attempt(number): calls.append(number); raise ProviderRateLimited(60)
    with pytest.raises(ProviderRateLimited): await bounded_race(attempt,delay=.1,timeout=.2)
    assert calls==[1]


@run_async
async def test_total_deadline_and_cancel_join_both_requests():
    from app.providers.voice_race import bounded_race
    closed=[]
    async def attempt(number):
        try: await asyncio.sleep(1)
        finally: closed.append(number)
    with pytest.raises(TimeoutError): await bounded_race(attempt,delay=.01,timeout=.04)
    assert set(closed)=={1,2}


@run_async
async def test_failed_primary_uses_backup_without_sleep_and_still_only_two():
    from app.providers.voice_race import bounded_race
    calls=[]
    async def attempt(number):
        calls.append(number)
        if number==1: raise ProviderTimeout('test')
        return 'ok'
    assert await bounded_race(attempt,delay=.3,timeout=.1)=='ok'
    assert calls==[1,2]


@run_async
async def test_sequential_retry_closes_first_before_starting_second():
    from app.providers.voice_race import bounded_retry
    events=[]
    async def attempt(number):
        events.append(('start',number))
        try:
            await asyncio.sleep(.2 if number==1 else .005)
            return number
        finally:events.append(('closed',number))
    assert await bounded_retry(attempt,delay=.01,timeout=.1)==2
    assert events==[('start',1),('closed',1),('start',2),('closed',2)]


@run_async
async def test_sequential_shared_deadline_does_not_restart_timeout_budget():
    from app.providers.voice_race import bounded_retry
    closed=[]
    async def attempt(number):
        try:await asyncio.sleep(1)
        finally:closed.append(number)
    with pytest.raises(TimeoutError):await bounded_retry(attempt,delay=.01,timeout=.03)
    assert closed==[1,2]


@run_async
async def test_sequential_never_retries_rate_limit():
    from app.providers.voice_race import bounded_retry
    calls=[]
    async def attempt(number):calls.append(number);raise ProviderRateLimited(60)
    with pytest.raises(ProviderRateLimited):await bounded_retry(attempt,delay=.01,timeout=.1)
    assert calls==[1]

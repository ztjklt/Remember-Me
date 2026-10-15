"""At most two identical authorized requests, one winner, one shared deadline."""
import asyncio
from time import perf_counter
from ..errors import ProviderAuthenticationFailed, ProviderRateLimited


async def bounded_retry(attempt, *, delay, timeout):
    """Close a stalled stream before retry; all attempts share the same deadline."""
    deadline=perf_counter()+timeout
    async with asyncio.timeout(timeout):
        try:
            async with asyncio.timeout(min(delay,timeout)):
                return await attempt(1)
        except (ProviderAuthenticationFailed,ProviderRateLimited):raise
        except Exception:
            if perf_counter()>=deadline:raise
            return await attempt(2)


async def bounded_race(attempt, *, delay, timeout):
    tasks=[]; pending=set(); last_error=None
    def launch():
        task=asyncio.create_task(attempt(len(tasks)+1))
        tasks.append(task);pending.add(task)
    try:
        async with asyncio.timeout(timeout):
            launch()
            while pending:
                done,_=await asyncio.wait(pending,timeout=delay if len(tasks)==1 else None,
                                          return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    launch();continue
                # A quota/auth failure is terminal even if another reply races it.
                for task in done:
                    error=task.exception()
                    if isinstance(error,(ProviderAuthenticationFailed,ProviderRateLimited)):raise error
                for task in tasks:
                    if task not in done:continue
                    pending.remove(task)
                    try:return task.result()
                    except Exception as error:last_error=error
                if len(tasks)==1:launch()
            raise last_error
    finally:
        for task in tasks:
            if not task.done():task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)

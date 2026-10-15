"""Per-request cancellation shared with synchronous provider workers."""
import asyncio
from contextvars import ContextVar
from threading import Event
from .errors import ProviderUnavailable

cancelled_request: ContextVar[Event | None]=ContextVar('cancelled_request',default=None)


def check_cancelled():
    event=cancelled_request.get()
    if event and event.is_set(): raise ProviderUnavailable('Voice request cancelled')


async def cancellable(awaitable):
    event=cancelled_request.get()
    if event is None: return await awaitable
    task=asyncio.create_task(awaitable)
    try:
        while not task.done():
            check_cancelled()
            await asyncio.wait({task},timeout=.1)
        check_cancelled()
        return task.result()
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task,return_exceptions=True)


async def until_disconnect(request, function):
    event=Event(); token=cancelled_request.set(event)
    task=asyncio.create_task(asyncio.to_thread(function))
    try:
        while not task.done():
            if await request.is_disconnected():
                event.set()
                raise ProviderUnavailable('Voice caller disconnected')
            await asyncio.wait({task},timeout=.1)
        return task.result()
    finally:
        event.set();cancelled_request.reset(token)
        # to_thread cannot kill Python code; provider transport observes Event.
        # Retrieve its eventual exception without blocking the app event loop.
        if task.done():
            if not task.cancelled(): task.exception()
        else: task.add_done_callback(lambda t: None if t.cancelled() else t.exception())

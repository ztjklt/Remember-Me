"""Private API-to-AI preparation stream. Drafts are NEVER client-facing answers."""
import asyncio
import json
from contextvars import ContextVar
from threading import Event
from fastapi.responses import StreamingResponse
from .cancellation import cancelled_request, check_cancelled

draft_observer=ContextVar('voice_draft_observer',default=None)
semantic_review_required=ContextVar('voice_semantic_review_required',default=True)
generation_streamed=ContextVar('voice_generation_streamed',default=False)


def prepare_draft(output):
    check_cancelled()
    observer=draft_observer.get()
    if observer is not None:
        observer({'type':'draft','text':output.answer})


def voice_response(function, *, review_required=True,stream_generation=False):
    async def events():
        loop=asyncio.get_running_loop();queue=asyncio.Queue(maxsize=4);cancelled=Event()
        def emit(event):
            if not cancelled.is_set():loop.call_soon_threadsafe(put,event)
        def put(event):
            if not cancelled.is_set():queue.put_nowait(event)
        def run():
            token=cancelled_request.set(cancelled);draft_token=draft_observer.set(emit)
            review_token=semantic_review_required.set(review_required)
            stream_token=generation_streamed.set(stream_generation)
            try:
                result=function();check_cancelled()
                value=result.model_dump(mode='json')
                if not review_required:
                    value.pop('coverage',None);value.pop('omitted_points',None)
                emit({'type':'final','result':value,
                      'semantic_review':'performed' if review_required else 'skipped'})
            except Exception as exc:
                emit({'type':'error','code':getattr(exc,'code','AI_OUTPUT_INVALID')})
            finally:
                generation_streamed.reset(stream_token)
                semantic_review_required.reset(review_token)
                draft_observer.reset(draft_token);cancelled_request.reset(token)
        task=asyncio.create_task(asyncio.to_thread(run))
        try:
            while True:
                event=await queue.get()
                yield json.dumps(event,ensure_ascii=False)+'\n'
                if event['type'] in {'final','error'}:break
        finally:
            cancelled.set()
            if task.done():
                if not task.cancelled():task.exception()
            else:task.add_done_callback(lambda t:None if t.cancelled() else t.exception())
    return StreamingResponse(events(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store'})

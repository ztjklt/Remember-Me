"""Bounded per-call retrieval preparation. Never predicts or publishes answers."""
import asyncio
from collections import OrderedDict
from copy import deepcopy
from threading import Lock, Event


class SelectionCache:
    def __init__(self):self.lock=Lock();self.values=OrderedDict();self.closed=False
    def get(self,key,question):
        with self.lock:return deepcopy(self.values.get((key,question.strip())))
    def put(self,key,question,value):
        with self.lock:
            if self.closed:return
            self.values[(key,question.strip())]=deepcopy(value)
            while len(self.values)>4:self.values.popitem(last=False)
    def close(self):
        with self.lock:self.closed=True;self.values.clear()


class VoicePrefetch:
    def __init__(self,prepare,delay=.20):
        self.prepare=prepare;self.delay=delay;self.task=None;self.closed=False
        self.latest=None;self.count=0;self.epoch=0
        self.running_stop=None
    def offer(self,question,history):
        if self.closed or len(question.strip())<6 or self.count>=2:return
        self.latest=(question,deepcopy(history),self.epoch)
        if self.task is None or self.task.done():self.task=asyncio.create_task(self._run())
    async def _run(self):
        while not self.closed and self.latest is not None and self.count<2:
            candidate=self.latest
            await asyncio.sleep(self.delay)
            if candidate!=self.latest:continue
            self.latest=None;self.count+=1
            stop=Event();self.running_stop=stop
            def check():
                if stop.is_set():raise RuntimeError('Prefetch cancelled')
            try:await self.prepare(candidate[0],candidate[1],check)
            except asyncio.CancelledError:raise
            except Exception:pass  # Final query must still run its ordinary checks.
            finally:self.running_stop=None
    def finish(self):
        self.latest=None;self.epoch+=1;self.count=0
        if self.running_stop:self.running_stop.set()
    async def close(self):
        self.closed=True;self.latest=None
        if self.running_stop:self.running_stop.set()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)

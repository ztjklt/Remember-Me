"""Bounded, ephemeral TTS preparation. Only an exact reviewed sentence consumes it."""
import asyncio
import re


def sentences(text):
    return [s for s in re.findall(r'.+?(?:[。！？!?](?:[”’」』])?|$)',text,re.S) if s.strip()]


class PreparedSpeech:
    def __init__(self,tts):
        self.tts=tts;self.text=None;self.task=None;self.queue=None
        self.preparations=0;self.first_prepared_text=None

    async def prepare(self,text):
        parts=sentences(text)
        if not parts:return
        if self.task is not None and parts[0]==self.text:return
        await self.close()
        self.text=parts[0];self.queue=asyncio.Queue(maxsize=8)
        self.preparations+=1
        if self.first_prepared_text is None:self.first_prepared_text=self.text
        queue=self.queue;first=self.text
        async def produce():
            try:
                async for chunk in self.tts(first):
                    # Bound individual queue entries independently of vendor
                    # HTTP chunk sizes. At most 8 * 16 KiB plus one source chunk.
                    for offset in range(0,len(chunk),16384):
                        await queue.put(chunk[offset:offset+16384])
                await queue.put(None)
            except asyncio.CancelledError:raise
            except Exception as exc:await queue.put(exc)
        self.task=asyncio.create_task(produce())

    async def stream(self,reviewed_sentence):
        if self.task is not None and reviewed_sentence==self.text:
            queue=self.queue
            try:
                while True:
                    chunk=await queue.get()
                    if chunk is None:break
                    if isinstance(chunk,Exception):raise chunk
                    yield chunk
            finally:await self.close()
        else:
            await self.close()
            async for chunk in self.tts(reviewed_sentence):yield chunk

    async def close(self):
        task=self.task;self.task=None;self.text=None;self.queue=None
        if task is not None:
            task.cancel();await asyncio.gather(task,return_exceptions=True)

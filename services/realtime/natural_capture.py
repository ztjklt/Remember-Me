"""Bounded microphone clip collection; failures never delay a conversational turn."""
import asyncio,io,wave
class MicrophoneClip:
    def __init__(self,backend,enabled=False):
        self.backend=backend;self.enabled=enabled;self.pcm=bytearray();self.started=False;self.attempts=0;self.tasks=set()
    def feed(self,data,speech):
        if not self.enabled:return
        if speech:self.started=True
        if self.started and len(self.pcm)<480000:self.pcm.extend(data[:480000-len(self.pcm)])
    def finish(self,turn):
        self.started=False
        if not self.enabled or self.attempts>=3:return
        # Several short normal utterances can make one useful sample. Do not
        # collect inter-turn silence or ask the person to speak longer.
        if len(self.pcm)<160000:return
        pcm=bytes(self.pcm);self.pcm.clear()
        self.attempts+=1
        async def send():
            try:
                buffer=io.BytesIO()
                with wave.open(buffer,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm)
                reply=await self.backend.request('POST','/samples',data={'turn_id':turn},files={'sample':('dialogue.wav',buffer.getvalue(),'audio/wav')})
                if reply.get('status')=='prepared':self.enabled=False
            except Exception:pass
        task=asyncio.create_task(send());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
    def close(self):
        self.enabled=False;self.pcm.clear()
        for task in self.tasks:task.cancel()

class UtteranceClip:
    """A separate clip for every turn. Never mix two turns to verify identity."""
    def __init__(self,backend,enabled=False,publish=None):
        self.backend=backend;self.enabled=enabled;self.publish=publish;self.pcm=bytearray();self.started=False;self.tasks=set();self.attempts=0
    def feed(self,data,speech):
        if not self.enabled:return
        if speech:self.started=True
        if self.started and len(self.pcm)<960000:self.pcm.extend(data[:960000-len(self.pcm)])
    def finish(self,turn):
        self.started=False;pcm=bytes(self.pcm);self.pcm.clear()
        if not self.enabled or len(pcm)<16000 or self.attempts>=120:return
        self.attempts+=1
        async def send():
            try:
                buffer=io.BytesIO()
                with wave.open(buffer,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm)
                await self.backend.request('POST','/utterances',data={'turn_id':turn},files={'sample':('utterance.wav',buffer.getvalue(),'audio/wav')})
                # Report recognition without holding the answer/planning task.
                if self.publish:
                    for _ in range(30):
                        await asyncio.sleep(2)
                        result=await self.backend.request('GET','/utterances/'+turn)
                        if result.get('status') in ('ready','skipped','deleted'):
                            if result.get('message'):await self.publish({'type':'speaker','turn_id':turn,'message':result['message']})
                            break
            except Exception:pass
        task=asyncio.create_task(send());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
    def close(self):
        self.enabled=False;self.pcm.clear()
        for task in self.tasks:task.cancel()

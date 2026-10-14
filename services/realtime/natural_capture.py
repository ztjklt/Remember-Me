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

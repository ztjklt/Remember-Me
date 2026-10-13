"""Transport independent call state. Playback acknowledgements, not generated text, form history."""
from __future__ import annotations
import asyncio
import base64
import re
import time
import logging
logger=logging.getLogger(__name__)


def conversation_control(text):
    """Only literal social controls. Never infer a person's facts or attitudes."""
    key=re.sub(r'[\s，。！？,.!?]','',text)
    return {'你好':'你好，你想聊哪段故事？','你好可以和我聊聊吗':'可以，你想聊哪段故事？',
            '谢谢':'不客气。你可以接着问，也可以结束通话。'}.get(key)


class VoiceTurns:
    def __init__(self, session_id, send, answer, tts, guard, *, prepare_audio=False):
        self.session_id=session_id; self.send=send; self.answer=answer; self.tts=tts; self.guard=guard
        self.turn_id=0; self.task=None; self.closed=False; self.history=[]
        self.current=None; self.segments=[]; self.samples=0; self.played=0; self.sequence=0
        self.timings={}; self.retired=set(); self.audio_complete=False
        self.prepare_audio=prepare_audio

    async def emit(self, kind, turn=None, **fields):
        if self.closed: return
        if turn is not None and turn!=self.turn_id: return
        await self.send(dict(type=kind,session_id=self.session_id,turn_id=self.turn_id,**fields))

    def playback(self, turn, samples):
        if turn!=self.turn_id: return
        if type(samples) is not int or samples<self.played or samples>self.samples: raise ValueError('Invalid playback position')
        if samples>0 and not self.played:
            self.timings['playback_ack_ms']=round((time.monotonic()-self.timings['asr_final'])*1000)
            logger.info('voice_playback',extra={'session_id':self.session_id,'turn_id':turn,
                'playback_ack_ms':self.timings['playback_ack_ms']})
        self.played=samples

    def _archive(self):
        if self.current:
            heard=''.join(text for end,text in self.segments if end<=self.played)
            self.history.append({'question':self.current['question'],'heard_answer':heard,
                'interrupted': not self.audio_complete or self.played < self.samples or not self.segments})
            self.history=self.history[-6:]
        self.current=None; self.samples=0; self.played=0; self.segments=[]; self.sequence=0; self.audio_complete=False

    async def interrupt(self):
        self._archive()
        self.turn_id+=1
        if self.task and not self.task.done():
            self.task.cancel()
            # Do not let a slow/cancellation-resistant provider block new speech.
            self.retired.add(self.task); self.task.add_done_callback(self.retired.discard)
        await self.emit('interrupted')

    async def submit(self, question):
        if self.closed: return
        if not question.strip() or len(question)>1000: raise ValueError('Question length invalid')
        await self.interrupt()
        turn=self.turn_id
        self.current={'question':question}
        self.timings={'asr_final':time.monotonic()}
        await self.emit('turn_started',turn,question=question)
        self.task=asyncio.create_task(self._respond(turn,question,list(self.history)))

    async def _respond(self, turn, question, history):
        start=time.monotonic()
        from .prepared_speech import PreparedSpeech, sentences as split_sentences
        async def authorized_tts(text):
            # Every NEW provider dispatch, including unpublished preparation,
            # must still be authorized. Playback guards alone are too late.
            await self.guard()
            if self.closed or turn!=self.turn_id:raise asyncio.CancelledError
            async for chunk in self.tts(text):yield chunk
        speech=PreparedSpeech(authorized_tts)
        try:
            await self.guard()
            answer=(await self.answer(question,history,speech.prepare) if self.prepare_audio
                    else await self.answer(question,history))
            if self.closed or turn!=self.turn_id: return
            await self.guard(answer)
            self.current['answer']=answer
            await self.emit('answer_ready',turn,answer=answer,
                            reviewed_ms=round((time.monotonic()-start)*1000))
            # Whole answer is reviewed first. Sentence boundaries are playback
            # accounting only; punctuation is never used to truncate meaning.
            sentences=split_sentences(answer['answer'])
            first=True
            for sentence in sentences:
                if not sentence.strip(): continue
                async for pcm in speech.stream(sentence):
                    if self.closed or turn!=self.turn_id: return
                    await self.guard(answer)
                    self.samples+=len(pcm)//2; self.sequence+=1
                    fields={'data':base64.b64encode(pcm).decode(),'sequence':self.sequence,
                            'samples':self.samples,'sample_rate':24000}
                    if first:
                        fields['first_audio_ms']=round((time.monotonic()-start)*1000); first=False
                    await self.emit('audio',turn,**fields)
                self.segments.append((self.samples,sentence))
            self.audio_complete=True
            await self.emit('audio_end',turn,samples=self.samples,
                            total_ms=round((time.monotonic()-start)*1000))
        except asyncio.CancelledError: raise
        except Exception as exc:
            if turn!=self.turn_id or self.closed: return
            self.history=[]; self.current=None
            code=getattr(exc,'code','VOICE_TURN_FAILED')
            # Client must stop and flush on ANY error; a source change may have
            # happened while already-sent chunks waited in its playback buffer.
            await self.emit('error',turn,code=code,message='本轮未完成，请重试。',stop_playback=True)
        finally:
            await speech.close()

    async def close(self):
        self.closed=True; self.turn_id+=1; self.history=[]; self.current=None
        tasks=list(self.retired)+([self.task] if self.task else [])
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks:
            done,_=await asyncio.wait(tasks,timeout=2)
            for task in done:
                if not task.cancelled(): task.exception()

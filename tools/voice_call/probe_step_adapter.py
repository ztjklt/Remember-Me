"""Live provider smoke, synthetic data only; key read server-side, never printed."""
import asyncio,json,time,wave,sys
from pathlib import Path
from types import SimpleNamespace
from dotenv import dotenv_values
from pydantic import SecretStr
from app.step_realtime import StepRealtimeSpeech

async def main():
    out=Path(sys.argv[1]);out.mkdir(exist_ok=True,parents=True)
    key=dotenv_values(sys.argv[2])['STEP_API_KEY']
    provider=StepRealtimeSpeech(SimpleNamespace(step_realtime_api_key=SecretStr(key)))
    packet=dict(question='他为什么偏爱淡茶？',mode='evidence',candidates=[dict(statement='喝茶',
        evidence=[dict(excerpt='我平时就爱喝淡茶，太甜的我不喜欢。只是个人口味，不是因为身体有毛病。')])],
        understandings=[],examples=[],contributions=[],dialogue_context=[])
    start=time.perf_counter();events=[];pcm=bytearray()
    try:
        async for event in provider.stream(packet):
            ms=round((time.perf_counter()-start)*1000)
            if event['type']=='pcm':pcm.extend(event['data']);events.append(dict(type='pcm',ms=ms,bytes=len(event['data'])))
            else:events.append(dict(event,ms=ms))
    except Exception as exc:events.append(dict(error=type(exc).__name__,code=getattr(exc,'code',None)))
    (out/'probe.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf8')
    if pcm:
        with wave.open(str(out/'probe.wav'),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(pcm)
    print(json.dumps(dict(done=any(e.get('type')=='done' for e in events),events=len(events),
        first_audio_ms=next((e['ms'] for e in events if e.get('type')=='pcm'),None),last=events[-1]),ensure_ascii=False))
asyncio.run(main())

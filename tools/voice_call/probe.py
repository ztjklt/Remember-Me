"""Run on ECS with its existing env. Outputs timings, never credentials."""
import asyncio
import json
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, '/opt/remember-me/current/services/backend')
sys.path.insert(0, str(Path(__file__).parent / 'deps'))
from app.config import Settings
from realtime_providers import ParaformerRealtime, XiaomiRealtime


async def main():
    settings = Settings(_env_file='/etc/remember-me/api.env')
    result = {'tts': {}, 'asr': {}, 'fictional_probe': True}
    out = Path(__file__).parent
    start = time.perf_counter()
    frames = []
    try:
        async for pcm in XiaomiRealtime(settings).stream('这是勿忘我的语音测试。我喜欢喝淡一点的茶。'):
            if not frames: result['tts']['first_chunk_ms'] = round((time.perf_counter()-start)*1000)
            frames.append(pcm)
        audio = b''.join(frames)
        result['tts'].update(ok=True, model='mimo-v2.5-tts', voice='白桦', chunks=len(frames),
            total_ms=round((time.perf_counter()-start)*1000), audio_seconds=len(audio)/48000)
        with wave.open(str(out/'preset.wav'), 'wb') as wav:
            wav.setparams((1,2,24000,0,'NONE','not compressed')); wav.writeframes(audio)
    except Exception as exc:
        result['tts'].update(ok=False, code=getattr(exc,'code',type(exc).__name__),
                             total_ms=round((time.perf_counter()-start)*1000))
    # Test ASR handshake independently even if TTS failed.
    start=time.perf_counter()
    try:
        async with ParaformerRealtime(settings) as asr:
            result['asr']['handshake_ms']=round((time.perf_counter()-start)*1000)
            if frames:
                process=await asyncio.create_subprocess_exec('/usr/bin/ffmpeg','-v','error','-i',str(out/'preset.wav'),
                    '-f','s16le','-ar','16000','-ac','1','pipe:1',stdout=asyncio.subprocess.PIPE)
                pcm,_=await process.communicate()
                if process.returncode: raise RuntimeError('RESAMPLE_FAILED')
                events=[]
                async def receive():
                    async for event in asr.events():
                        events.append(dict(event,elapsed_ms=round((time.perf_counter()-start)*1000)))
                        if event['type']=='asr_finished': break
                reader=asyncio.create_task(receive())
                for i in range(0,len(pcm),3200):
                    await asr.send(pcm[i:i+3200]); await asyncio.sleep(.1)
                for _ in range(12): await asr.send(bytes(3200)); await asyncio.sleep(.1)
                await asr.finish()
                await asyncio.wait_for(reader,15)
                result['asr'].update(events=events,ok=any(e.get('final') for e in events))
            else: result['asr'].update(ok=False,connected=True,reason='TTS sample unavailable')
    except Exception as exc:
        status=getattr(getattr(exc,'response',None),'status_code',None)
        result['asr'].update(ok=False,code=getattr(exc,'code',type(exc).__name__),http_status=status,
                            total_ms=round((time.perf_counter()-start)*1000))
    (out/'probe-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': asyncio.run(main())

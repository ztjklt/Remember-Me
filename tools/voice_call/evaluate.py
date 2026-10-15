"""Real-provider, synthetic-speech evaluation on an isolated deployment.

Protocol acknowledgements below simulate consumption and are NEVER phone/headphone
measurements. Credentials are read from a private JSON file, never in results.
"""
import argparse,asyncio,base64,hashlib,json,ssl,subprocess,time,wave
from pathlib import Path
import httpx
from websockets.asyncio.client import connect
from app.config import Settings
from app.realtime_providers import XiaomiRealtime

CASES=[
 ('short','你好，可以和我聊聊吗？'),
 ('short','你喜欢喝什么茶？'),
 ('short','刚才说的茶，浓一点还是淡一点？'),
 ('short','你想和女儿说些什么？'),
 ('short','刚才那件事，能再简单讲一句吗？'),
 ('memory','第一次独立跑十二路是哪一年？'),
 ('memory','为什么有一条记录说是一九八六年？'),
 ('memory','旧水杯有什么故事？'),
 ('memory','他银行卡的密码是什么？'),
 ('memory','关于喝茶，亲友有什么不同的回忆？'),
 ('interrupt','请讲讲公交工作中的故事。'),
 ('interrupt','先不说工作了，你喜欢什么茶？'),
 ('interrupt','第一次跑十二路是哪一年？'),
 ('interrupt','请详细说说旧水杯的故事。'),
 ('interrupt','先停一下，你女儿叫什么名字？'),
]


async def main(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    settings=Settings(_env_file=args.env)
    credentials=json.loads(Path(args.credentials).read_text(encoding='utf-8-sig'))
    rows=[]
    tls=ssl.create_default_context(cafile=args.ca_file) if args.ca_file else ssl.create_default_context()
    async with httpx.AsyncClient(base_url=args.base,timeout=130,trust_env=False,verify=tls) as http:
        def ok(response): response.raise_for_status();return response.json()
        login=ok(await http.post('/api/v1/accounts/login',json=credentials))
        token=login['actor_token'];http.headers['Authorization']='Bearer '+token
        spaces=ok(await http.get('/api/v1/workbench/spaces'))['items']
        subject=next(s['subject_id'] for s in spaces if s['role']==args.role and '陈守义' in s.get('display_name',s.get('name','')))
        if args.role=='owner':
            consents=ok(await http.get('/api/v1/consents',params={'subject_id':subject}))
            consent=next(c['consent_id'] for c in consents if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
        else:
            grants=ok(await http.get(f'/api/v1/workbench/subjects/{subject}/grants'))['items']
            consent=next(g['grant_id'] for g in grants if g['cloud_processing_allowed'] and not g.get('revoked_at'))
        ws=None;call=None;silence_task=None;injecting=False
        async def keep_audio(connection):
            while True:
                if not injecting:await connection.send(bytes(3200))
                await asyncio.sleep(.1)
        try:
            for index,(group,question) in enumerate(CASES[:args.limit]):
                row=dict(index=index+1,group=group,input=question,synthetic_input=True,
                         playback_measurement='protocol simulation only',events=[],ok=False)
                rows.append(row)
                def save(): (out/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
                save()
                # A new session per group; follow-up questions within a group share
                # only the protocol-confirmed played answer, not a gold script.
                if index%5==0 or ws is None:
                    if silence_task:
                        silence_task.cancel();await asyncio.gather(silence_task,return_exceptions=True)
                    if ws: await ws.close()
                    call=ok(await http.post(f'/api/v1/subjects/{subject}/voice-sessions',json=dict(
                        cloud_consent_id=consent,mode=args.mode,policy='continuous-voice-v1',
                        cloud_asr_allowed=True,cloud_tts_allowed=True,response_speed=args.response_speed,
                        engine=args.engine)))
                    ws=await connect(args.base.replace('http','ws',1)+call['websocket_path'],
                        additional_headers={'Authorization':'Bearer '+token},proxy=None,max_size=1_000_000,
                        **({'ssl':tls} if args.base.startswith('https://') else {}))
                    ready=json.loads(await asyncio.wait_for(ws.recv(),20));assert ready['type']=='ready',ready
                    silence_task=asyncio.create_task(keep_audio(ws))
                digest=hashlib.sha256(question.encode()).hexdigest()[:16]
                source=out/(digest+'.wav')
                if not source.exists():
                    provider=XiaomiRealtime(settings)
                    try:frames=[pcm async for pcm in provider.stream(question)]
                    finally:await provider.close()
                    with wave.open(str(source),'wb') as f:
                        f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b''.join(frames))
                pcm=subprocess.check_output(['/usr/bin/ffmpeg','-v','error','-i',str(source),'-f','s16le','-ar','16000','-ac','1','pipe:1'])
                row['input_audio']=source.name;row['input_seconds']=len(pcm)/32000
                started=time.monotonic();speech_end=None;frames=[]
                async def send_audio():
                    nonlocal speech_end,injecting
                    injecting=True
                    try:
                        for offset in range(0,len(pcm),3200):
                            await ws.send(pcm[offset:offset+3200]);await asyncio.sleep(.1)
                        speech_end=time.monotonic()
                    finally:injecting=False
                sending=asyncio.create_task(send_audio())
                try:
                    async with asyncio.timeout(160):
                        while True:
                            event=json.loads(await ws.recv());kind=event['type']
                            elapsed=round((time.monotonic()-started)*1000)
                            if kind=='audio':
                                frames.append(base64.b64decode(event.pop('data')))
                                if len(frames)==1:
                                    row['first_audio_after_input_end_ms']=round((time.monotonic()-(speech_end or started))*1000)
                                    row['first_audio_event']=dict(event)
                                # Interruption trials stop the first chunk and verify
                                # the following question does not receive this turn.
                                if group=='interrupt':
                                    old=event['turn_id'];await ws.send(json.dumps({'type':'interrupt'}))
                                    while True:
                                        next_event=json.loads(await ws.recv())
                                        if next_event['type']=='interrupted':break
                                    row['interrupt_ack_ms']=round((time.monotonic()-started)*1000)-elapsed
                                    row['retired_turn']=old;row['ok']=True;break
                                await ws.send(json.dumps({'type':'playback','turn_id':event['turn_id'],'samples':event['samples']}))
                            elif kind=='answer_ready':
                                row['answer']=event['answer'];row['response_speed']=event.get('response_speed','reviewed')
                                row['answer_ready_ms']=event.get('answer_ready_ms',event.get('reviewed_ms'))
                                if 'reviewed_ms' in event:row['reviewed_ms']=event['reviewed_ms']
                            elif kind=='transcript' and event['final']:row['asr']=event['text'];row['asr_final_after_input_end_ms']=round((time.monotonic()-(speech_end or started))*1000)
                            row['events'].append(dict(event,client_elapsed_ms=elapsed))
                            if kind=='audio_end':row['ok']=True;break
                            if kind=='error':row['error']=event;break
                    await sending
                except Exception as exc:
                    row['exception']=type(exc).__name__;sending.cancel()
                    await asyncio.gather(sending,return_exceptions=True)
                    if ws:await ws.close();ws=None
                if frames:
                    with wave.open(str(out/f'answer-{index+1:02d}.wav'),'wb') as f:
                        f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b''.join(frames))
                row['elapsed_ms']=round((time.monotonic()-started)*1000);save()
                print(json.dumps({k:row.get(k) for k in ('index','ok','asr','reviewed_ms','first_audio_after_input_end_ms','exception','error')},ensure_ascii=False),flush=True)
        finally:
            if silence_task:
                silence_task.cancel();await asyncio.gather(silence_task,return_exceptions=True)
            if ws:await ws.close()
            if call:await http.delete('/api/v1/voice-sessions/'+call['session_id'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8895')
    p.add_argument('--env',required=True);p.add_argument('--credentials',required=True)
    p.add_argument('--mode',choices=['evidence','persona'],default='evidence')
    p.add_argument('--response-speed',choices=['reviewed','fast','streamed'],default='reviewed')
    p.add_argument('--engine',choices=['pipeline','step_realtime'],default='pipeline')
    p.add_argument('--role',choices=['owner','reader'],default='owner')
    p.add_argument('--ca-file')
    p.add_argument('--output',required=True);p.add_argument('--limit',type=int,default=15)
    asyncio.run(main(p.parse_args()))

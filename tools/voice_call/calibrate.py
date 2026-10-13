"""Explicit synthetic voice-calibration probe; review the actual ASR between phases.

Runs against an authorized test account. No source script is sent as an answer to
the comparison model. Raw ASR, reviewed text and synthetic input stay separate.
"""
import argparse, asyncio, base64, json, time, wave
from datetime import datetime, timezone
from pathlib import Path
import httpx
from websockets.asyncio.client import connect
from app.config import Settings
from app.realtime_providers import XiaomiRealtime


async def main(args):
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    state_path=out/'result.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {
        'synthetic_human_audio':True, 'human_listening_verified':False,
        'question':'平时喝茶喜欢浓一点还是淡一点？', 'stages':[]}
    def save(): state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    def ok(response):
        if response.is_error:
            state.setdefault('errors',[]).append({'status':response.status_code,'body':response.json()}); save()
        response.raise_for_status(); return response.json()
    async with httpx.AsyncClient(base_url=args.base,timeout=150,trust_env=False,
                                 headers={'X-Forwarded-Proto':'https'}) as client:
        login=ok(await client.post('/api/v1/accounts/login',json=json.loads(Path(args.credentials).read_text())))
        token=login['actor_token']; client.headers['Authorization']='Bearer '+token
        spaces=ok(await client.get('/api/v1/workbench/spaces'))['items']
        subject=next(s['subject_id'] for s in spaces if s['role']=='owner' and '陈守义' in s['display_name'])
        base=f'/api/v1/subjects/{subject}'
        consents=ok(await client.get('/api/v1/consents',params={'subject_id':subject}))
        consent=lambda scope: next(c['consent_id'] for c in consents if c['scope']==scope and c['status']=='granted')
        if args.phase=='prepare':
            if 'calibration' in state: raise RuntimeError('Already prepared; preserve checkpoint')
            started=time.monotonic()
            row=ok(await client.post(base+'/calibrations/prepare-voice',json={
                'question':state['question'],'mode':'evidence','cloud_consent_id':consent('CLOUD_TWIN')}))
            assert row['answer_hidden'] and row['locked_answer'] is None
            state['calibration']=row; state['locked_ms']=round((time.monotonic()-started)*1000); save()
            response=await client.get(base+'/twin/answers/'+row['twin_answer_id'])
            state['blind_answer_read_status']=response.status_code;save()
            assert response.status_code==404
            text='我喝茶喜欢淡一点，太甜的我喝不惯。这就是我的口味，不是谁规定我只能这么喝。'
            (out/'synthetic-script.txt').write_text(text)
            frames=[p async for p in XiaomiRealtime(Settings(_env_file=args.env)).stream(text)]
            audio=out/'synthetic-answer.wav'
            with wave.open(str(audio),'wb') as f:
                f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b''.join(frames))
            caps=ok(await client.get('/api/v1/workbench/capabilities'))
            episode=ok(await client.post('/api/v1/episodes',data={
                'subject_id':subject,'recording_consent_id':consent('RECORDING'),
                'idempotency_key':row['calibration_id'],'source':'IMPORT',
                'recorded_at':datetime.now(timezone.utc).isoformat(),'audio_ref':audio.name,
                'metadata':json.dumps({'calibration_id':row['calibration_id'],
                    'cloud_asr_policy':caps['cloud_asr_policy'],'synthetic_test':True})},
                files={'file':(audio.name,audio.read_bytes(),'audio/wav')}))
            state['episode_id']=episode['episode_id']; save()
            for _ in range(50):
                review=ok(await client.get('/api/v1/episodes/'+state['episode_id']+'/transcript-review'))
                if review['state']=='reviewing':
                    state['actual_asr']=review; save()
                    (out/'actual-asr.txt').write_text(review['transcript']); print(json.dumps(review,ensure_ascii=False));return
                await asyncio.sleep(3)
            raise TimeoutError('ASR not ready; retained checkpoint')
        if not args.reviewed_file: raise RuntimeError('Reviewed ASR file required')
        review=Path(args.reviewed_file).read_text().strip()
        state['reviewed_text']=review; state['review_kind']='technical review of synthetic material';save()
        eid=state['episode_id']; cid=state['calibration']['calibration_id']
        ok(await client.patch('/api/v1/episodes/'+eid+'/transcript-review',json={'transcript':review}))
        for _ in range(60):
            status=ok(await client.get('/api/v1/episodes/'+eid))
            state['episode_status']=status;save()
            if status['status']=='failed': raise RuntimeError('Extraction failed; preserve failure')
            if status['status']=='ready':break
            await asyncio.sleep(3)
        else: raise TimeoutError('Extraction not ready')
        state['extraction']=ok(await client.get('/api/v1/episodes/'+eid+'/result'));save()
        completed=ok(await client.post(base+'/calibrations/'+cid+'/complete',json={'cloud_consent_id':consent('CLOUD_TWIN')}))
        assert completed['status']=='complete' and not completed['answer_hidden']
        state['comparison']=completed;save()
        call=ok(await client.post(base+'/voice-sessions',json={'cloud_consent_id':consent('CLOUD_TWIN'),
            'policy':'continuous-voice-v1','cloud_asr_allowed':True,'cloud_tts_allowed':True,
            'purpose':'calibration_report','calibration_id':cid}))
        frames=[]; events=[]; started=time.monotonic()
        try:
            async with connect(args.base.replace('http','ws',1)+call['websocket_path'],
                additional_headers={'Authorization':'Bearer '+token},proxy=None) as ws:
                async with asyncio.timeout(120):
                    async for raw in ws:
                        event=json.loads(raw)
                        if event['type']=='audio':
                            frames.append(base64.b64decode(event.pop('data')))
                            if len(frames)==1:state['report_first_audio_ms']=round((time.monotonic()-started)*1000)
                            await ws.send(json.dumps({'type':'playback','turn_id':event['turn_id'],'samples':event['samples']}))
                        events.append(event)
                        if event['type']=='error':raise RuntimeError(event['code'])
                        if event['type']=='audio_end':break
            with wave.open(str(out/'comparison-report.wav'),'wb') as f:
                f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b''.join(frames))
            state['report_events']=events; state['ok']=bool(frames);save()
            print(json.dumps({'ok':state['ok'],'report_first_audio_ms':state['report_first_audio_ms'],
                              'summary':completed['summary']},ensure_ascii=False))
        finally:await client.delete('/api/v1/voice-sessions/'+call['session_id'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--env',required=True)
    p.add_argument('--credentials',required=True);p.add_argument('--output',required=True)
    p.add_argument('--phase',choices=['prepare','complete'],required=True);p.add_argument('--reviewed-file')
    asyncio.run(main(p.parse_args()))

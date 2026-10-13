"""Explicitly authorized fictional corpus, serial TTS and actual ECS processing.

No authored script is submitted as ASR or model evidence. The review subcommand
requires an independently saved review file; it never copies the TTS script.
Credentials and all outputs must be in an ignored directory, supplied by path.
"""
import argparse, base64, hashlib, json, os, time
from pathlib import Path
import httpx
from dotenv import dotenv_values
from tools.monthly_eval import speech_pipeline as speech

ROOT = Path(__file__).resolve().parents[2]
def sha(data): return hashlib.sha256(data).hexdigest()
def save(path, value): speech.save(path, value)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=['audio','upload','snapshot','review','organize'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--env',type=Path)
    p.add_argument('--voice',type=Path)
    p.add_argument('--episode',default='bus_driver-01')
    a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    state_path=a.out/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'episodes':{}}
    corpus=ROOT/'evaluations/spoken-corpus-v2'
    manifest=json.loads((corpus/'manifest.json').read_text(encoding='utf-8'))
    ep=next(e for e in manifest['episodes'] if e['id']==a.episode)
    folder=a.out/a.episode;folder.mkdir(exist_ok=True)
    row=state['episodes'].setdefault(a.episode,{})
    def checkpoint():save(state_path,state)
    if a.stage=='audio':
        text=(corpus/ep['script']).read_text(encoding='utf-8')
        assert sha(text.encode())==ep['sha256'], 'Frozen script changed'
        if (folder/'audio.json').exists():
            meta=json.loads((folder/'audio.json').read_text())
            assert meta['text_sha256']==ep['sha256'] and sha((folder/'audio.wav').read_bytes())==meta['audio_sha256']
            print(a.episode,'existing immutable audio retained');return
        env={**dotenv_values(a.env),**os.environ}; key=env.get('MIMO_API_KEY','')
        if not key:raise RuntimeError('MIMO_API_KEY missing; no provider switch')
        assert a.voice and a.voice.exists(), 'Provide the existing fictional voice sample'
        voice='data:audio/wav;base64,'+base64.b64encode(a.voice.read_bytes()).decode()
        speech.OUT=a.out; speech.PROMPT='spoken-garden-v2-20261011'
        audio,meta=speech.synthesize(key,'mimo-v2.5-tts-voiceclone',text,
            '虚构的退休公交司机，年长男声，自然讲述，平静温暖。完整朗读给定文字，不加内容，不省略；段落自然停顿。',voice)
        with (folder/'audio.wav').open('xb') as f:f.write(audio)
        save(folder/'audio.json',{**meta,'synthetic':True,'manual_listening':'pending','voice_sha256':sha(a.voice.read_bytes()),
             'authored_script':ep['script'],'simulated_day':ep['simulated_day']})
        row['audio_sha256']=meta['audio_sha256'];checkpoint()
        print(a.episode,'audio saved',round(meta['duration_seconds'],1),'seconds',flush=True);return

    cfg=json.loads((a.out/'private-config.json').read_text(encoding='utf-8'))
    with httpx.Client(base_url='https://39.108.183.47',timeout=55,trust_env=False,
        verify=str(ROOT/'apps/android/app/src/internal/res/raw/remember_ecs_ip_demo.pem')) as client:
        def call(method,path,**kwargs):
            start=time.monotonic()
            r=client.request(method,path,headers={'Authorization':'Bearer '+cfg['owner']['token']},**kwargs)
            with (a.out/'ecs-calls.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'at':time.time(),'method':method,'path':path,'http_status':r.status_code,
                    'elapsed_seconds':round(time.monotonic()-start,3)})+'\n')
            if r.is_error:raise RuntimeError(f'HTTP {r.status_code}: {r.text[:500]}')
            return r.json() if r.content else {}
        subject=cfg['owner']['subject_id'];base=f'/api/v1/workbench/subjects/{subject}'
        def consent(scope):return call('POST','/api/v1/consents',json={'subject_id':subject,'scope':scope})['consent_id']
        if a.stage=='upload' and not row.get('episode_id'):
            caps=call('GET','/api/v1/workbench/capabilities');save(a.out/'capabilities.json',caps)
            assert caps['stt_processing']=='cloud' and 'paraformer' in caps['stt_model'].lower(), 'Expected ECS Paraformer'
            meta=json.loads((folder/'audio.json').read_text());audio=folder/'audio.wav'
            assert sha(audio.read_bytes())==meta['audio_sha256']
            with audio.open('rb') as f:
                created=call('POST','/api/v1/episodes',data={'subject_id':subject,'source':'IMPORT',
                    'recorded_at':f"2026-09-{ep['simulated_day']:02d}T08:00:00Z",'audio_ref':a.episode+'.wav',
                    'duration_ms':str(round(meta['duration_seconds']*1000)),
                    'idempotency_key':'spoken-garden-v2-'+ep['id']+'-'+ep['sha256'][:16],
                    'recording_consent_id':consent('RECORDING'),
                    'metadata':json.dumps({'capture_client':'fictional-spoken-garden-v2','cloud_asr_policy':caps['cloud_asr_policy']})},
                    files={'file':(a.episode+'.wav',f,'audio/wav')})
            row['episode_id']=created['episode_id'];checkpoint()
        if a.stage=='organize':
            job=call('POST',base+'/narrative/suggest',json={'cloud_consent_id':consent('CLOUD_TWIN'),
                'episode_ids':[row['episode_id']]})
            row['narrative_job']=job;checkpoint();print(a.episode,'narrative',job['status']);return
        if a.stage=='review':
            review=json.loads((folder/'review.json').read_text(encoding='utf-8'))
            actual=json.loads((folder/'asr.json').read_text(encoding='utf-8'))
            assert review['asr_sha256']==sha(actual['transcript'].encode()) and review['technical_review'] is True
            consent('CLOUD_TWIN')
            call('PATCH',f"/api/v1/episodes/{row['episode_id']}/transcript-review",json={
                'transcript':review['transcript'],'supplement':review.get('supplement','')})
            row['review_submitted']=True;checkpoint()
        if a.stage=='snapshot':
            save(a.out/'narrative.json',call('GET',base+'/narrative'))
            save(a.out/'stories.json',call('GET',base+'/stories'))
            print('Current source snapshots saved');return
        for _ in range(150):
            story=next(s for s in call('GET',base+'/stories')['items'] if s['episode_id']==row['episode_id'])
            save(folder/'story.json',story);row['status']=story['status'];checkpoint()
            if story['status']=='failed':raise RuntimeError('Actual processing failed: '+json.dumps(story.get('error',{})))
            if story.get('waiting_for_review'):
                actual=call('GET',f"/api/v1/episodes/{row['episode_id']}/transcript-review")
                save(folder/'asr.json',actual);print(a.episode,'actual ASR saved; awaiting review',flush=True);return
            if story['status']=='ready':
                print(a.episode,'ready; actual memories',len(story['memories']),flush=True);return
            time.sleep(3)
        raise RuntimeError('Bounded wait ended; checkpoint and audio retained')

if __name__=='__main__':main()

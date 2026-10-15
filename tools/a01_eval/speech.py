"""Fresh fictional Xiaomi audio; uses the existing synthesis adapter only."""
import base64
import importlib.util
import json
import os
from pathlib import Path
from dotenv import dotenv_values
from tools.a01_eval.prepare import ROOT, DATA, save, digest

OUT=ROOT/'services/backend/var/a01-20261012/evaluation/speech'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('a01_existing_speech',ROOT/'tools/monthly_eval/speech_pipeline.py')
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    adapter.OUT=OUT
    original_client=adapter.httpx.Client
    class BoundedClient(original_client):
        def __init__(self,*args,**kwargs):
            kwargs['timeout']=45
            super().__init__(*args,**kwargs)
    adapter.httpx.Client=BoundedClient
    env={**dotenv_values('D:/codex_work/remember-me-agent-loop/services/backend/.env.speech-eval'),**os.environ}
    key=env.get('MIMO_API_KEY','')
    if not key:raise SystemExit('MIMO_API_KEY missing; no call')
    episodes=json.loads((DATA/'input/episodes.json').read_text(encoding='utf-8'))
    style='虚构的老年男性，声音平实温和，自然说话，不刻意模仿病症。完整逐字朗读，不省略；句间自然停顿。'
    probe_audio=None
    for i,ep in enumerate(episodes):
        if digest(ep['text'].encode())!=ep['sha256']:raise RuntimeError('Spoken hash changed')
        name=ep['id'];audio=OUT/(name+'.wav');record=OUT/(name+'.json')
        if record.exists():
            state=json.loads(record.read_text(encoding='utf-8'))
            if state['status']!='saved':raise RuntimeError('Previous synthesis not complete; no silent duplicate '+name)
            if digest(audio.read_bytes())!=state['audio_sha256']:raise RuntimeError('Audio changed')
            data=audio.read_bytes()
        else:
            if audio.exists():raise RuntimeError('Uncertain existing audio; preserve')
            save(record,{'status':'started','episode_id':name,'script_sha256':ep['sha256']})
            try:
                model='mimo-v2.5-tts-voicedesign' if i==0 else 'mimo-v2.5-tts-voiceclone'
                voice=None if i==0 else 'data:audio/wav;base64,'+base64.b64encode(probe_audio).decode()
                data,meta=adapter.synthesize(key,model,ep['text'],style,voice)
                with audio.open('xb') as f:f.write(data)
                save(record,{**meta,'status':'saved','episode_id':name,'synthetic':True,'fiction':True,
                    'script_sha256':ep['sha256'],'manual_listening':'pending','asr_status':'blocked_configuration',
                    'source_audio':'new_A01_Xiaomi_synthetic_not_original_recording'})
            except Exception as exc:
                save(record,{'status':'failed','episode_id':name,'error_type':type(exc).__name__,
                    'reason':str(exc),'asr_status':'not_run'})
                raise
        if i==0:
            probe_audio=data
            save(OUT/'probe-gate.json',{'episode_id':name,'technical_wav_validation':True,
                'manual_listening':'pending','remaining_nine_authorization':'A01 local approved plan: expand after fresh technical probe succeeds'})
        current=json.loads(record.read_text(encoding='utf-8'))
        current.update(style_sha256=digest(style.encode()),
            voice_seed_audio_sha256=None if i==0 else digest(probe_audio),
            source_paragraph=ep['paragraph'],input_type='exact_spoken_script_text')
        save(record,current)
        print(name,'saved',len(data),'bytes',flush=True)
    save(OUT/'asr-blocker.json',{'actual_asr_calls':0,'status':'blocked',
        'reason':'Visible local backend config selects historical Groq; no approved Paraformer configuration found. No provider switch or local Whisper.',
        'transcript_policy':'No scripts or old audio labeled ASR; script source remains separate.'})

if __name__=='__main__':main()

"""Reproducible Xiaomi synthetic-only speech and local Whisper evaluation.

Does not load gold, call the text model, confirm transcripts or publish memory.
Run --samples first. --remaining requires a manually reviewed live gate report.
Secrets live in ignored services/backend/.env.speech-eval or environment only.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import dotenv_values

REPO=Path(__file__).resolve().parents[2]
CORPUS=REPO/'evaluations/monthly-integration-v1'
OUT=REPO/'services/backend/var/monthly-eval'
ENDPOINT='https://api.xiaomimimo.com/v1/chat/completions'
PROMPT='synthetic-monthly-speech-v1'

def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def audit(row):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'calls.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')

def synthesize(key,model,text,style,voice=None):
    body={'model':model,'messages':[{'role':'user','content':style},{'role':'assistant','content':text}],
        'audio':{'format':'wav'}}
    if voice:body['audio']['voice']=voice
    for attempt in range(1,4):
        start=time.monotonic();row={'at':datetime.now(timezone.utc).isoformat(),'endpoint':ENDPOINT,
            'request_model':model,'prompt_version':PROMPT,'text_sha256':sha(text.encode()),'attempt':attempt}
        try:
            with httpx.Client(timeout=300,trust_env=False,follow_redirects=False) as client:
                response=client.post(ENDPOINT,json=body,headers={'Authorization':'Bearer '+key})
            row.update(http_status=response.status_code,elapsed_seconds=round(time.monotonic()-start,3))
            if response.status_code in {408,429,500,502,503,504}:
                row['validation']='transient_http_failure';audit(row)
                if attempt<3:time.sleep(2**attempt);continue
                raise RuntimeError(f'TTS transient HTTP {response.status_code}, retry budget exhausted')
            if not response.is_success:
                row['validation']='rejected';audit(row)
                raise RuntimeError(f'TTS HTTP {response.status_code}; no provider switch, inspect account configuration')
            result=response.json();choice=result['choices'][0]
            row.update(response_model=result.get('model'),finish_reason=choice.get('finish_reason'),usage=result.get('usage'))
            if choice.get('finish_reason') not in {None,'stop'}:raise ValueError('truncated_audio')
            data=base64.b64decode(choice['message']['audio']['data'],validate=True)
            with wave.open(io.BytesIO(data),'rb') as wav:
                duration=wav.getnframes()/wav.getframerate()
                if duration<=0:raise ValueError('empty_audio')
                row.update(duration_seconds=duration,sample_rate=wav.getframerate(),channels=wav.getnchannels())
            row.update(validation='valid_wav_not_yet_listened',audio_sha256=sha(data));audit(row)
            return data,row
        except httpx.TimeoutException:
            row.update(http_status=None,elapsed_seconds=round(time.monotonic()-start,3),validation='timeout');audit(row)
            if attempt==3:raise RuntimeError('TTS timed out after three attempts') from None
            time.sleep(2**attempt)
        except (ValueError,KeyError,wave.Error):
            row.update(elapsed_seconds=round(time.monotonic()-start,3),validation='invalid_audio_response');audit(row)
            raise RuntimeError('TTS returned invalid or truncated audio; no automatic retry') from None

def main():
    ap=argparse.ArgumentParser();group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--samples',action='store_true');group.add_argument('--remaining',action='store_true')
    ap.add_argument('--preset',action='store_true',help='Explicitly use preset instead of design/clone; reported as fallback')
    ap.add_argument('--stt-url',default='http://127.0.0.1:8878/transcribe');args=ap.parse_args()
    env={**dotenv_values(REPO/'services/backend/.env.speech-eval'),**os.environ}
    key=(env.get('MIMO_API_KEY') or '').strip()
    if not key:raise SystemExit('MIMO_API_KEY missing; no request made')
    manifest=json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
    if args.remaining:
        gate=OUT/'sample-gate.json'
        required={'real_weixin','reviewed_asr','persisted_memory','qa_sources','manual_listening','duration_pass'}
        data=json.loads(gate.read_text()) if gate.exists() else {}
        if not all(data.get(p['id'],{}).get(k) is True for p in manifest['people'] for k in required):
            raise SystemExit('Three live sample gates are not approved; remaining27 synthesis blocked')
    OUT.mkdir(parents=True,exist_ok=True)
    for person in manifest['people']:
        style=person['voice']+'完整逐字朗读，不省略；每分钟约一百八十至二百个汉字，段落之间自然停顿。'
        folder=OUT/person['id'];folder.mkdir(exist_ok=True)
        voice_file=folder/'synthetic-voice.wav'
        voice_manifest=folder/'synthetic-voice.json'
        if not args.preset and not voice_file.exists():
            data,meta=synthesize(key,'mimo-v2.5-tts-voicedesign','这是一段虚构人物的合成声音，只用于软件测试。我想把这些故事慢慢说清楚，拿不准的事情，就先留着空白。',style)
            voice_file.write_bytes(data);save(voice_manifest,{**meta,'synthetic':True,'description':person['voice']})
        if args.preset:voice='茉莉'
        else:
            meta=json.loads(voice_manifest.read_text(encoding='utf-8'))
            if sha(voice_file.read_bytes())!=meta['audio_sha256']:raise RuntimeError('Voice sample hash mismatch')
            voice='data:audio/wav;base64,'+base64.b64encode(voice_file.read_bytes()).decode()
        for ep in person['episodes'][:1] if args.samples else person['episodes'][1:]:
            text=(CORPUS/ep['script']).read_text(encoding='utf-8')
            if sha(text.encode())!=ep['script_sha256']:raise RuntimeError('Script hash mismatch; rebuild manifest explicitly')
            audio=folder/(ep['id']+'.wav');record=folder/(ep['id']+'.json')
            request_fingerprint=sha((text+style+voice+PROMPT).encode())
            if audio.exists() and record.exists():
                meta=json.loads(record.read_text(encoding='utf-8'))
                if meta['request_fingerprint']!=request_fingerprint or meta['audio_sha256']!=sha(audio.read_bytes()):
                    raise RuntimeError('Existing audio identity differs; preserve and regenerate explicitly')
            else:
                data,meta=synthesize(key,'mimo-v2.5-tts' if args.preset else 'mimo-v2.5-tts-voiceclone',text,style,voice)
                audio.write_bytes(data);meta.update(episode_id=ep['id'],request_fingerprint=request_fingerprint,
                    simulated_recorded_at=ep['simulated_recorded_at'],synthetic=True,manual_listening='pending',
                    duration_pass=180<=meta['duration_seconds']<=300,preset_fallback=args.preset)
                save(record,meta)
            asr=folder/(ep['id']+'.asr.json')
            if not asr.exists():
                start=time.monotonic()
                r=httpx.post(args.stt_url,content=audio.read_bytes(),headers={'Content-Type':'audio/wav'},timeout=300,trust_env=False)
                if r.status_code!=200:raise RuntimeError(f'Local STT HTTP {r.status_code}; audio remains saved')
                data=r.json();save(asr,{'audio_sha256':meta['audio_sha256'],'elapsed_seconds':time.monotonic()-start,
                    'endpoint':args.stt_url,'raw_asr':data['text'],'model_version':data['model_version'],'review_status':'pending'})
            print(ep['id'],round(meta['duration_seconds'],1),'seconds','duration_pass='+str(meta['duration_pass']),
                'ASR saved, human listening/review and cloud processing pending',flush=True)

if __name__=='__main__':main()

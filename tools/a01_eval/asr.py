"""Use the existing Paraformer adapter on new immutable A01 WAVs only.

Never sends script/gold to ASR. Private adapter state stays in the ignored run.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx
from pydantic import SecretStr
from tools.a01_eval.prepare import ROOT, save, digest

sys.path.insert(0,str(ROOT/'services/backend'))
from app.config import Settings
from app.errors import AppError
from app import paraformer_asr

BASE=ROOT/'services/backend/var/a01-20261012/evaluation'
OUT=BASE/'asr-paraformer-v1'
PRIVATE=ROOT/'services/backend/var/a01-20261012/private/paraformer.json'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--remaining',action='store_true')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    configuration_bytes=PRIVATE.read_bytes()
    values=json.loads(configuration_bytes)
    if set(values)!={'paraformer_api_key','paraformer_base_url'}:raise RuntimeError('Unexpected private configuration fields')
    settings=Settings(_env_file=None, stt_backend='paraformer',
        paraformer_api_key=SecretStr(values['paraformer_api_key']),
        paraformer_base_url=values['paraformer_base_url'],
        paraformer_state_dir=str(OUT/'adapter-state'), stt_timeout_seconds=45,
        paraformer_poll_interval_seconds=2,paraformer_poll_timeout_seconds=120)
    if not paraformer_asr.configured(settings):raise RuntimeError('Paraformer configuration rejected before upload')
    # Use the adapter's exact upload/submission/poll/result checks, with proxies
    # explicitly disabled. No alternative STT implementation is introduced.
    paraformer_asr._client=lambda timeout:httpx.Client(timeout=timeout,follow_redirects=False,trust_env=False)
    provider=paraformer_asr.ParaformerSttProvider(settings)
    first=OUT/'A01_01.raw-asr.json'
    if args.remaining and not first.exists():raise RuntimeError('Fresh ASR probe must succeed first')
    ids=range(2,11) if args.remaining else [1]
    for number in ids:
        id=f'A01_{number:02}'
        audio_path=BASE/'speech'/f'{id}.wav'
        audio_meta=json.loads((BASE/'speech'/f'{id}.json').read_text(encoding='utf-8'))
        expected=audio_meta['audio_sha256']
        path=OUT/f'{id}.raw-asr.json'
        if path.exists():
            result=json.loads(path.read_text(encoding='utf-8'))
            if result['audio_sha256']!=expected:raise RuntimeError('ASR audio identity differs')
            print(id,'checkpoint_reused',flush=True);continue
        def authorize():
            if digest(audio_path.read_bytes())!=expected:raise RuntimeError('Audio source changed')
            if PRIVATE.read_bytes()!=configuration_bytes:raise RuntimeError('ASR configuration changed')
        authorize()
        save(OUT/f'{id}.stage.json',{'episode_id':id,'status':'started','audio_sha256':expected,
            'at':datetime.now(timezone.utc).isoformat(),'authorization':'Explicit fictional A01 local evaluation; actual existing Paraformer adapter',
            'script_or_gold_sent':False,'adapter_state_resumable':True})
        try:
            transcript=provider.transcribe_authorized(audio_path.read_bytes(),'audio/wav',authorize)
            result={'episode_id':id,'audio_sha256':expected,'text':transcript.text,
                'transcript_sha256':digest(transcript.text.encode()),'backend':transcript.backend,
                'model_version':transcript.model_version,'metadata':transcript.metadata,
                'input_type':'fresh_Xiaomi_synthetic_audio','review_status':'unreviewed_machine_transcript',
                'script_or_gold_sent':False,'timestamps_alignment':'not_verified'}
            save(path,result)
            save(OUT/f'{id}.stage.json',{'episode_id':id,'status':'raw_asr_saved','audio_sha256':expected})
            print(id,'ASR_saved',len(transcript.text),'chars','seconds',transcript.metadata['elapsed_seconds'],flush=True)
            if number==1:
                save(OUT/'probe-gate.json',{'episode_id':id,'raw_transcript_received':True,
                    'matching_audio_verified':True,'model_version':transcript.model_version,
                    'manual_audio_listening':'pending','authorization':'Continue remaining nine after fresh actual ASR probe succeeds'})
        except Exception as error:
            safe={'episode_id':id,'status':'failed','error_type':type(error).__name__,
                'error_code':getattr(error,'code',None)}
            if isinstance(error,AppError):safe['reason']=error.message
            save(OUT/f'{id}.stage.json',safe)
            print(id,'ASR_failed',safe['error_type'],safe['error_code'],flush=True)
            raise SystemExit(1) from None

if __name__=='__main__':main()

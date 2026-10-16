"""Paired real-provider test on frozen, authorized fictional fixtures only.

Both routes use the identical semantic review; this probe excludes ASR/TTS.
Run from the candidate AI Core directory. Output contains fixture text, so keep
the directory private and publish only manually reviewed timing metadata.
"""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import time

from app.config import Settings
from app.providers.weixin import WeixinChat
from app.quoted_twin import QuotedTwin
from app.twin import TwinInput


def main(args):
    os.umask(0o077)
    args.output.mkdir(exist_ok=False)
    settings=Settings(_env_file=args.ai_env)
    chat=WeixinChat(api_key=settings.weixin_api_key.get_secret_value())
    logger=logging.getLogger('remember_me.ai_core')
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.FileHandler(args.output/'calls.jsonl',encoding='utf8'))
    records=[]
    class RecordedChat:
        @property
        def json_retry_managed(self): return chat.json_retry_managed
        def complete(self, system, packet):
            begin=time.monotonic()
            stage='review' if 'selection' in packet else 'selection'
            row={'stage':stage, 'prompt_sha256':hashlib.sha256(system.encode()).hexdigest()}
            calls.append(row)
            try:
                raw,model=chat.complete(system,packet)
                row.update(status='ok',raw=raw,model=model)
                return raw,model
            except Exception as exc:
                row.update(status='failed',error=type(exc).__name__)
                raise
            finally:row['duration_ms']=round((time.monotonic()-begin)*1000,3)
    try:
        for repeat in range(args.repeats):
            for index,item in enumerate(json.loads(args.packets.read_text(encoding='utf8'))):
                payload=TwinInput.model_validate(item['payload']); payload.voice_response=True
                modes=[False,True] if (repeat+index)%2 else [True,False]
                if args.route!='both':modes=[args.route=='direct']
                for direct in modes:
                    calls=[];begin=time.monotonic()
                    record=dict(case=item['id'],repeat=repeat+1,direct_original=direct,
                        packet_sha256=hashlib.sha256(payload.model_dump_json().encode()).hexdigest())
                    try:
                        with chat.transport_scope(timeout_seconds=settings.voice_call_timeout_seconds,
                            retry_after_seconds=settings.voice_retry_after_seconds,
                            json_retry_after_seconds=settings.effective_voice_json_retry_after_seconds):
                            result=QuotedTwin(RecordedChat(),direct_original=direct).answer(payload)
                        record.update(status='ok',answer=result.model_dump())
                    except Exception as exc:
                        record.update(status='failed',error=type(exc).__name__)
                    record.update(duration_ms=round((time.monotonic()-begin)*1000,3),calls=calls)
                    records.append(record)
                    (args.output/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
                    print(json.dumps({k:record.get(k) for k in ('case','repeat','direct_original','status','duration_ms','error')}),flush=True)
                    if record.get('error') in {'ProviderAuthenticationFailed','ProviderRateLimited'}:
                        return
                    time.sleep(args.pause_seconds)
    finally:chat.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--ai-env',type=Path,required=True)
    parser.add_argument('--packets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--route',choices=['both','direct','control'],default='both')
    parser.add_argument('--pause-seconds',type=float,default=5)
    main(parser.parse_args())

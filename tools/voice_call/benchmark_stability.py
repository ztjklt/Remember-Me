"""Paired source/condition-preserving live benchmark, no answer or prompt tuning."""
import argparse
import json
import logging
import time
from pathlib import Path
from dotenv import dotenv_values
from app.providers.weixin import WeixinChat
from app.quoted_twin import QuotedTwin
from app.twin import TwinInput
from app.voice_stream import generation_streamed, semantic_review_required


def main(a):
    samples=json.loads(Path(a.packets).read_text('utf8'))
    output=Path(a.output); output.mkdir(parents=True,exist_ok=False)
    rows=[]; logs=[]
    class Recorder(logging.Handler):
        def emit(self, record):
            try: logs.append(json.loads(record.getMessage()))
            except ValueError: pass
    logger=logging.getLogger('remember_me.ai_core'); handler=Recorder(); logger.addHandler(handler)
    chat=WeixinChat(api_key=dotenv_values('/etc/remember-me/ai.env')['WEIXIN_CHAT_API_KEY'])
    twin=QuotedTwin(chat)
    stream=generation_streamed.set(True);review=semantic_review_required.set(False)
    try:
        for repeat in range(a.rounds):
            for sample in samples:
                modes=(['control','bounded'] if repeat%2==0 else ['bounded','control']) if a.both else ['bounded']
                for mode in modes:
                    start=time.perf_counter();logs.clear()
                    row=dict(repeat=repeat,sample=sample['id'],mode=mode,ok=False)
                    try:
                        with chat.transport_scope(timeout_seconds=8,retry_after_seconds=a.delay if mode=='bounded' else 0):
                            result=twin.answer(TwinInput.model_validate(sample['payload']))
                        row.update(ok=True,answer=result.model_dump())
                    except Exception as error:row['error']=type(error).__name__
                    row.update(total_ms=round((time.perf_counter()-start)*1000,3),logs=list(logs));rows.append(row)
                    (output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf8')
                    print(json.dumps({k:v for k,v in row.items() if k not in ('logs','answer')}),flush=True)
                    if row.get('error')=='ProviderRateLimited': return
                    time.sleep(a.interval)
    finally:
        generation_streamed.reset(stream);semantic_review_required.reset(review)
        chat.close();logger.removeHandler(handler)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--packets',required=True);p.add_argument('--output',required=True)
    p.add_argument('--rounds',type=int,default=3);p.add_argument('--delay',type=float,default=3);p.add_argument('--both',action='store_true')
    p.add_argument('--interval',type=float,default=5)
    main(p.parse_args())

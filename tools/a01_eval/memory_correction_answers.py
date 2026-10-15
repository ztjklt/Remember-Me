"""Same Twin/model/questions before and after the isolated correction replay."""
import json
import sys
import logging
from pathlib import Path
from time import perf_counter
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'services/ai-core'))
from dotenv import dotenv_values
from app.providers.weixin import WeixinTwinProvider
from app.twin import TwinInput


def main():
    base=ROOT/'services/backend/var/memory-quality-20261015'
    out=Path((base/'latest-replay.txt').read_text(encoding='utf-8'))
    replay=json.loads((out/'replay.json').read_text(encoding='utf-8'))
    key=dotenv_values(ROOT.parents[3]/'services/ai-core/.env').get('WEIXIN_CHAT_API_KEY')
    if not key:raise SystemExit('Existing credential unavailable')
    questions=['桂芳究竟有没有动过他的钥匙？','他在给桂芳的话里，说谁这些年没有享到多少清福？',
        '修老车床时究竟哪里出了问题？他后来还反思了自己什么？']
    provider=WeixinTwinProvider(api_key=key,quote_answers=True)
    logging.getLogger('remember_me.ai_core').disabled=True
    results=[]
    try:
        for index,question in enumerate(questions):
            for stage in (('before','after') if index%2==0 else ('after','before')):
                candidates=[{k:v for k,v in c.items() if k in {'memory_item_id','statement','domain','traits','graph_facts','evidence'}}
                            for c in replay[stage]]
                payload=TwinInput(question=question,candidates=candidates)
                result={'question':question,'stage':stage}; start=perf_counter()
                try:
                    output=provider.answer(payload)
                    result.update(status='ok',output=output.model_dump(mode='json'))
                except Exception as exc:result.update(status='failed',error_type=type(exc).__name__)
                result['duration_seconds']=round(perf_counter()-start,3)
                results.append(result)
                (out/'answers.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
                print(index+1,stage,result['status'],result['duration_seconds'],flush=True)
    finally:provider.close()


if __name__=='__main__':main()

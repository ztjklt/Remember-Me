"""Same authorized packets, phase timings only; never print credentials/headers."""
import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from app.twin import TwinInput
from app.quoted_twin import quote_packet, VOICE_SYSTEM, SourceSelection, render_ids


async def main(a):
    samples = json.loads(Path(a.packets).read_text('utf8'))
    key = dotenv_values(a.env)['WEIXIN_CHAT_API_KEY']
    output = Path(a.output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    async with httpx.AsyncClient(trust_env=False, limits=httpx.Limits(keepalive_expiry=60)) as warm:
        for repeat in range(a.rounds):
            for sample in samples[:a.samples]:
                modes = ['cold', 'warm'] if repeat % 2 == 0 else ['warm', 'cold']
                for mode in modes:
                    payload = TwinInput.model_validate(sample['payload'])
                    packet, _ = quote_packet(payload)
                    packet['response_schema'] = SourceSelection.model_json_schema()
                    stable = ('recordings', 'confirmed_understanding', 'understandings', 'examples', 'contributions', 'response_schema')
                    packet = {**{k: packet[k] for k in stable if k in packet}, **{k: v for k,v in packet.items() if k not in stable}}
                    body = dict(model='Deepseek-v4-flash', stream=True, response_format={'type':'json_object'},
                        messages=[dict(role='system', content=VOICE_SYSTEM), dict(role='user', content=json.dumps(packet,ensure_ascii=False,separators=(',',':')))])
                    row = dict(sample=sample['id'], repeat=repeat, mode=mode, ok=False,
                               packet_sha256=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest(), phases=[])
                    started = time.perf_counter()
                    async def trace(event, info, row=row, started=started):
                        # Values include request bodies, keys and arbitrary exceptions: discard all.
                        row['phases'].append(dict(event=event, ms=round((time.perf_counter()-started)*1000,3)))
                    client = warm if mode=='warm' else httpx.AsyncClient(trust_env=False)
                    parts=[]; done=False; finish=None
                    try:
                        async with asyncio.timeout(a.timeout):
                            async with client.stream('POST','https://chatapi.weixin.qq.com/openai/v1/chat/completions',
                                json=body, headers={'Authorization':'Bearer '+key}, timeout=a.timeout,
                                extensions={'trace':trace}) as response:
                                row.update(status=response.status_code, headers_ms=round((time.perf_counter()-started)*1000,3))
                                response.raise_for_status()
                                async for line in response.aiter_lines():
                                    if not line.startswith('data:'): continue
                                    raw=line[5:].strip()
                                    if raw=='[DONE]': done=True; continue
                                    event=json.loads(raw)
                                    if event.get('model'): row['model']=event['model']
                                    if event.get('usage'): row['usage']=event['usage']
                                    for choice in event.get('choices',[]):
                                        content=(choice.get('delta') or {}).get('content')
                                        if content:
                                            row.setdefault('first_content_ms',round((time.perf_counter()-started)*1000,3))
                                            parts.append(content)
                                        if choice.get('finish_reason') is not None: finish=choice['finish_reason']
                                if not done or finish!='stop': raise ValueError('incomplete stream')
                                answer,_=render_ids(json.loads(''.join(parts)),payload,row['model'])
                                row.update(ok=True,answer=answer.model_dump(),selection=''.join(parts))
                    except Exception as error:
                        row['error']=type(error).__name__
                    finally:
                        if mode=='cold': await client.aclose()
                    row['total_ms']=round((time.perf_counter()-started)*1000,3)
                    row.update(raw_content=''.join(parts),finish_reason=finish,done=done)
                    rows.append(row)
                    (output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf8')
                    print(json.dumps({k:row[k] for k in ('sample','repeat','mode','ok','error','total_ms','headers_ms','first_content_ms') if k in row}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--packets',required=True); p.add_argument('--env',default='/etc/remember-me/ai.env')
    p.add_argument('--output',required=True);p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--samples',type=int,default=3);p.add_argument('--timeout',type=float,default=8)
    asyncio.run(main(p.parse_args()))

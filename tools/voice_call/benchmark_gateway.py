"""Explicit contest-gateway experiment; never imported by production services."""
import argparse,json,time,hashlib
from pathlib import Path
import httpx
from dotenv import dotenv_values
from app.twin import TwinInput
from app.quoted_twin import quote_packet,VOICE_SYSTEM,SourceSelection,render_ids

MODELS=['deepseek-v4.1-flash','glm-5.2','qwen-max','nova-pro','kimi-k3','deepseek-v4-pro']

def main(a):
    key=dotenv_values(a.env)['ANKER_API_KEY']; packets=json.loads(Path(a.packets).read_text('utf8'))
    output=Path(a.output);output.mkdir(exist_ok=False,parents=True)
    selected=a.models.split(',') if a.models else MODELS
    rows=[]
    for repeat in range(a.repeats):
      for sample in (packets[:1] if a.smoke else packets):
       for name in selected:
        payload=TwinInput.model_validate(sample['payload']);packet,_=quote_packet(payload)
        packet['response_schema']=SourceSelection.model_json_schema()
        if a.compact:
            from app.voice_packet import compact_packet
            packet=compact_packet(packet)
        prompt=VOICE_SYSTEM
        if a.compact:
            from app.voice_packet import COMPACT_INSTRUCTION
            prompt+='\n'+COMPACT_INSTRUCTION
        model='Deepseek-v4-flash' if name=='weixin' else 'hackathon/v_model/'+name
        endpoint='https://chatapi.weixin.qq.com/openai/v1/chat/completions' if name=='weixin' else 'https://ai-router-cn-pub.anker-in.com/chat/completions'
        secret=dotenv_values(a.weixin_env)['WEIXIN_CHAT_API_KEY'] if name=='weixin' else key
        body={'model':model,'stream':True,'response_format':{'type':'json_object'},'max_tokens':a.max_tokens,
              'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(packet,ensure_ascii=False,separators=(',',':'))}]}
        if a.disable_thinking and name in ('weixin','deepseek-v4.1-flash','deepseek-v4-pro'):
            body['thinking']={'type':'disabled'}
        if a.disable_thinking and name=='qwen-max':body['enable_thinking']=False
        if a.reasoning_effort and name in ('deepseek-v4.1-flash','deepseek-v4-pro'):
            body['reasoning_effort']=a.reasoning_effort
        row={'sample':sample['id'],'question':payload.question,'requested_model':model,'repeat':repeat,
             'compact':a.compact,'thinking':body.get('thinking'),'enable_thinking':body.get('enable_thinking'),'max_tokens':a.max_tokens,'reasoning_effort':body.get('reasoning_effort'),'packet_sha256':hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
             'input_chars':sum(len(x['content']) for x in body['messages']),'ok':False}
        start=time.perf_counter();parts=[];reason=None;done=False
        try:
          with httpx.Client(timeout=httpx.Timeout(a.timeout),trust_env=False) as client:
           with client.stream('POST',endpoint,json=body,
                             headers={'Authorization':'Bearer '+secret}) as r:
            row['status']=r.status_code
            if r.status_code!=200:
                row['error']='HTTP_'+str(r.status_code)
            else:
             for line in r.iter_lines():
              if time.perf_counter()-start>a.timeout:raise TimeoutError('task deadline')
              if not line.startswith('data:'):continue
              raw=line[5:].strip()
              if raw=='[DONE]':done=True;break
              event=json.loads(raw)
              if event.get('model'):row['response_model']=event['model']
              if event.get('usage'):row['usage']=event['usage']
              for c in event.get('choices',[]):
                delta=c.get('delta') or {};text=delta.get('content')
                if text:
                    row.setdefault('first_content_ms',round((time.perf_counter()-start)*1000));parts.append(text)
                if c.get('finish_reason') is not None:reason=c['finish_reason']
             row.update(done=done,finish_reason=reason)
             if not done or reason!='stop':raise ValueError('incomplete SSE')
             answer,_=render_ids(json.loads(''.join(parts)),payload,row.get('response_model',model))
             row.update(ok=True,answer=answer.model_dump(),raw_selection=''.join(parts))
        except Exception as e:row['error']=type(e).__name__
        row['raw_content']=''.join(parts)
        row['total_ms']=round((time.perf_counter()-start)*1000);rows.append(row)
        (output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf8')
        print(json.dumps({k:row[k] for k in ('sample','requested_model','ok','status','error','total_ms','first_content_ms') if k in row}),flush=True)
        if row.get('status')==429:break

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--env',required=True);p.add_argument('--packets',required=True);p.add_argument('--output',required=True)
    p.add_argument('--smoke',action='store_true');p.add_argument('--compact',action='store_true');p.add_argument('--models');p.add_argument('--repeats',type=int,default=1);p.add_argument('--timeout',type=float,default=20);p.add_argument('--weixin-env',default='/etc/remember-me/ai.env')
    p.add_argument('--disable-thinking',action='store_true')
    p.add_argument('--max-tokens',type=int,default=512)
    p.add_argument('--reasoning-effort',choices=['low','high','max'])
    main(p.parse_args())

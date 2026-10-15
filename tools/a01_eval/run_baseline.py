"""Serial A01 text baseline; never opens DOCX or reference-only data.

Uses frozen extraction/profile/Twin validators. No repair or retry on schema or
semantic failures. A started checkpoint without an outcome blocks rerun.
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'services/ai-core'))
from app.providers.weixin import WeixinChat, WeixinProvider
from app.extractor import MemoryExtractor
from app.contracts import AICoreInput
from app.profile_proposals import ProfileProposalProvider, ProfileProposalInput
from app.twin import TwinInput
from app.quoted_twin import SYSTEM, REVIEW, Verdict, SourceSelection, quote_packet, render_ids
from app.errors import ProviderTimeout, ProviderUnavailable, ProviderRateLimited, AIOutputInvalid
from tools.a01_eval.prepare import save, digest

DATA = ROOT/'evaluations/a01-20261012'
OUT = ROOT/'services/backend/var/a01-20261012/evaluation'
OUT.mkdir(parents=True, exist_ok=True)

class Telemetry(logging.Handler):
    def emit(self, record):
        try:
            obj=json.loads(record.getMessage())
            if isinstance(obj,dict):
                with (OUT/'provider-telemetry.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps(obj,ensure_ascii=False)+'\n')
        except (ValueError,TypeError): pass

logging.getLogger('remember_me.ai_core').addHandler(Telemetry())

class TraceMixin:
    stage = ''
    serial = 0
    def complete(self, system, payload):
        self.serial += 1
        callid=f'{self.stage}-{self.serial:02}'
        trace={'id':callid,'started_at':datetime.now(timezone.utc).isoformat(),
            'endpoint':self.base_url+'/chat/completions','requested_model':self.model,
            'system_sha256':digest(system.encode()),
            'payload_sha256':digest(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()),
            'system':system,'payload':payload,'status':'started'}
        path=OUT/'calls'/f'{callid}.json'
        save(path,trace)
        for attempt in range(1,4):
            trace['attempt']=attempt
            try:
                raw, model=super().complete(system,payload)
                save(path,{**trace,'status':'transport_json_success','raw_output':raw,'response_model':model})
                return raw,model
            except (ProviderTimeout,ProviderUnavailable) as exc:
                save(path,{**trace,'status':'transient_failure','error_code':exc.code})
                if attempt == 3: raise
                delay=getattr(exc,'retry_after_seconds',2**attempt)
                if delay > 60: raise
                time.sleep(delay)
            except Exception as exc:
                save(path,{**trace,'status':'failed_no_retry','error_type':type(exc).__name__})
                raise

class ExtractionChat(TraceMixin,WeixinProvider): pass
class Chat(TraceMixin,WeixinChat): pass

def checkpoint_task(name, function):
    path=OUT/'tasks'/f'{name}.json'
    if path.exists():
        state=json.loads(path.read_text(encoding='utf-8'))
        if state['status']=='started':raise RuntimeError('Uncertain prior call outcome: '+name)
        print(name,'checkpoint',state['status'],flush=True)
        return state
    save(path,{'status':'started','id':name})
    try:
        result=function()
        state={'id':name,'status':'validated','result':result,
               'semantic_status':'pending_independent_technical_review'}
    except Exception as exc:
        state={'id':name,'status':'failed','error_type':type(exc).__name__,
            'error_code':getattr(exc,'code',None),'reason':getattr(exc,'message',type(exc).__name__),
            'semantic_status':'not_passed'}
    save(path,state)
    print(name,state['status'],flush=True)
    return state

def qa(chat,question,episodes,evidence_suffix='-script'):
    candidates=[{'memory_item_id':ep['id']+'-whole-text','statement':ep['text'],
        'evidence':[{'evidence_id':ep['id']+evidence_suffix,'excerpt':ep['text'],'source_type':'SUBJECT',
        'episode_id':ep['id'],'span_start':0,'span_end':len(ep['text'])}]} for ep in episodes]
    payload=TwinInput(question=question,candidates=candidates)
    packet,_=quote_packet(payload)
    packet={**packet,'response_schema':SourceSelection.model_json_schema()}
    raw,model=chat.complete(SYSTEM,packet)
    output,selection=render_ids(raw,payload,model)
    sources={s['id']:s for r in packet['recordings'] for s in r['sources']}
    cited=[[sources[q.source_id] for q in p.quotes] for p in selection.points]
    checked,_=chat.complete(REVIEW,{**packet,'response_schema':Verdict.model_json_schema(),
        'selection':selection.model_dump(),'cited_material':cited,
        'rendered_answer':output.model_dump(exclude={'model_version','confidence'})})
    verdict=Verdict.model_validate(checked)
    if verdict.valid and (verdict.failure_codes or verdict.replacement is not None):
        raise AIOutputInvalid('Inconsistent positive quote review')
    if not verdict.valid:raise AIOutputInvalid('Quoted answer failed relevance review')
    return {'question':question,'answer':output.model_dump(mode='json'),'review':verdict.model_dump(),
            'original_evidence':[e.model_dump(mode='json') for c in payload.candidates for e in c.evidence
                                 if e.evidence_id in output.evidence_ids]}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--stage',choices=['all','extract','qa','qa-early'],default='all')
    args=parser.parse_args()
    env={**dotenv_values('D:/codex_work/remember-me-agent-loop/services/ai-core/.env'),**os.environ}
    key=env.get('WEIXIN_CHAT_API_KEY','')
    save(OUT/'configuration-presence.json',{'WEIXIN_CHAT_API_KEY':bool(key),
        'endpoint':'https://chatapi.weixin.qq.com/openai/v1','model':'Deepseek-v4-flash',
        'timeout_seconds':45,'serial_requests':True,'max_transient_attempts':3,'schema_semantic_retries':0})
    if not key:raise SystemExit('WEIXIN_CHAT_API_KEY missing; no calls')
    episodes=json.loads((DATA/'input/episodes.json').read_text(encoding='utf-8'))
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    if digest((DATA/'input/episodes.json').read_bytes()) != manifest['input_sha256']:
        raise ValueError('Prepared input file changed; no model call made')
    if [ep['paragraph'] for ep in episodes] != [28,31,34,37,40,43,46,49,52,55]:raise ValueError('Input manifest changed')
    for ep in episodes:
        if digest(ep['text'].encode())!=ep['sha256']:raise ValueError('Input hash mismatch')
    save(OUT/'input-trace.json',{'path':'input/episodes.json','sha256':digest((DATA/'input/episodes.json').read_bytes()),
        'episodes':[{k:ep[k] for k in ['id','paragraph','sha256']} for ep in episodes],
        'reference_files_opened':False,'input_type':'text_baseline_not_ASR'})
    extract=ExtractionChat(api_key=key); chat=Chat(api_key=key)
    worker=MemoryExtractor(provider=extract,model=extract.model,model_version=extract.model)
    if args.stage in ('all','extract'):
        for batch,stop in enumerate((4,7,10),1):
            start=(0,4,7)[batch-1]
            for ep in episodes[start:stop]:
                extract.stage='extract-'+ep['id'];extract.serial=0
                checkpoint_task(extract.stage,lambda ep=ep:worker.process(AICoreInput(
                    episode_id=ep['id'],subject_id='fictional-A01-local-only',transcript=ep['text'],
                    existing_model_version='A01-text-baseline',trace_id=extract.stage)).model_dump(mode='json'))
            chat.stage=f'profile-batch{batch}';chat.serial=0
            materials=[{'evidence_id':ep['id']+'-script','episode_id':ep['id'],'excerpt':ep['text']} for ep in episodes[:stop]]
            checkpoint_task(chat.stage,lambda:ProfileProposalProvider(chat).propose(
                ProfileProposalInput(materials=materials)).model_dump(mode='json'))
    if args.stage in ('all','qa'):
        questions=json.loads((DATA/'input/questions.json').read_text(encoding='utf-8'))
        for q in questions:
            chat.stage='qa-'+q['id'];chat.serial=0
            checkpoint_task(chat.stage,lambda q=q:qa(chat,q['question'],episodes))
    if args.stage == 'qa-early':
        questions=json.loads((DATA/'input/questions.json').read_text(encoding='utf-8'))[:8]
        for batch,stop in ((1,4),(2,7)):
            for q in questions:
                chat.stage=f'qa-batch{batch}-'+q['id'];chat.serial=0
                checkpoint_task(chat.stage,lambda q=q,stop=stop:qa(chat,q['question'],episodes[:stop]))
    extract.close();chat.close()

if __name__=='__main__':main()

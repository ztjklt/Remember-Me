"""Fixed 60 real text-model questions; no TTS, STT, gold answers or repairs.

Each invocation owns a new checkpoint. Resume sends only unfinished questions;
completed answers and failed attempts are never overwritten or cherry-picked.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from speech_pipeline import CORPUS, OUT, save
from product_loop import AUTH, MAPPING, call, check_qa_scope


def pending_attempts(row):
    if 'result' in row or row.get('terminal_error'):return range(0)
    return range(len(row.get('attempts',[])),3)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--round',required=True)
    parser.add_argument('--recognition-run')
    parser.add_argument('--cases', help='Explicit comma-separated case IDs for a separately recorded regression')
    parser.add_argument('--protocol', default='twin-compact-v2')
    args=parser.parse_args()
    if not args.round.replace('-','').isalnum(): raise SystemExit('Invalid round name')
    if args.recognition_run and not args.recognition_run.replace('-','').isalnum(): raise SystemExit('Invalid recognition run')
    selected = set(args.cases.split(',')) if args.cases else None
    recognition = OUT/'cloud-asr-runs'/args.recognition_run if args.recognition_run else None
    target=OUT/('qa-'+args.round+'.json')
    state=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {
        'round':args.round,'started_at':datetime.now(timezone.utc).isoformat(),
        'prompt_protocol':args.protocol,'new_audio_recognition':False,
        'recognition_run':args.recognition_run,'selected_cases':sorted(selected) if selected else None,
        'human_listening':False,'qa':{}}
    if state.get('selected_cases') != (sorted(selected) if selected else None): raise SystemExit('Cases differ from saved round')
    auth=json.loads(((recognition/'identities.json') if recognition else AUTH).read_text(encoding='utf-8'))
    mapping=json.loads(((recognition/'product-episodes.json') if recognition else MAPPING).read_text(encoding='utf-8'))
    for pid,pair in auth.items():
        gold=json.loads((CORPUS/'gold'/(pid+'.json')).read_text(encoding='utf-8'))
        owner=pair['owner'];subject=owner['subject_id'];root='/api/v1/workbench/subjects/'+subject
        cons=call('GET','/api/v1/consents?subject_id='+subject,owner)
        cloud=next(c['consent_id'] for c in cons if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
        grants=call('GET',root+'/grants',pair['reader'])['items']
        reader_cloud=next(g['grant_id'] for g in grants if g['cloud_processing_allowed'] and not g.get('revoked_at'))
        check_qa_scope(pid,gold['qa_protocol'],mapping,grants,call('GET',root+'/stories',pair['reader'])['items'],call('GET',root+'/revisions',owner)['items'])
        checks=state['qa'].setdefault(pid,{'checks':[]})['checks']
        for check in gold['qa']:
            if selected is not None and check['id'] not in selected: continue
            row=next((r for r in checks if r['id']==check['id']),None)
            if row is None:
                row={'id':check['id'],'role':check['role'],'question':check['question'],'text_review':'pending','attempts':[]}
                checks.append(row);save(target,state)
            for attempt in pending_attempts(row):
                start=time.monotonic()
                entry={'state':'started','started_at':datetime.now(timezone.utc).isoformat()}
                row['attempts'].append(entry);save(target,state)
                try:
                    # Only the question is sent. Expected answers never enter
                    # requests; the backend constructs authorized evidence.
                    row['result']=call('POST','/api/v1/subjects/'+subject+'/twin/answers',pair[check['role']],
                        json={'question':check['question'],'cloud_consent_id':cloud if check['role']=='owner' else reader_cloud})
                    entry.update(state='complete',http_status=200,elapsed_seconds=round(time.monotonic()-start,3))
                    save(target,state);break
                except Exception as exc:
                    entry.update(state='failed',error=str(exc),elapsed_seconds=round(time.monotonic()-start,3))
                    save(target,state)
                    # Retry only transient transport/service failures, never a
                    # semantically wrong but completed model answer.
                    if not any(s in str(exc) for s in ('HTTP 429','HTTP 502','HTTP 503','HTTP 504','timed out')):
                        row['terminal_error']=True;save(target,state);break
                    if attempt<2:time.sleep(2**attempt)
            print(row['id'],'saved' if 'result' in row else 'failed',flush=True)
    state['finished_at']=datetime.now(timezone.utc).isoformat();state['quality_review']='pending';save(target,state)


if __name__=='__main__':main()

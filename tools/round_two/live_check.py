"""Real-provider round-two checks. Reuses existing ASR, never sends gold answers.

Run after serve.py. Outputs are local ignored artifacts, with durable checkpoints.
Each invocation starts only missing stages; failures are retained, not retried.
"""
import json,time,argparse,sys
from pathlib import Path
from datetime import datetime,timezone
import httpx
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'services/backend/var/round-two'
AUTH=ROOT/'services/backend/var/monthly-eval/identities.json'

def save(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)

def main():
    args=argparse.ArgumentParser();args.add_argument('--stage',choices=['proposals','qa'],default='proposals');args.add_argument('--run-name',choices=['initial','checked','context-v8','context-v8-full','points-v1','points-v1-full','points-v2','points-v3','points-v4','points-v5','points-v6','quotes-v7','quotes-v8','quotes-v9','quotes-v10'],default='initial')
    args.add_argument('--case',action='append',help='Run only specified development-case IDs; no gold answer is sent')
    args=args.parse_args()
    auth=json.loads(AUTH.read_text(encoding='utf8'));path=OUT/(args.stage+('-'+args.run_name if args.run_name!='initial' else '')+'.json')
    report=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'started':datetime.now(timezone.utc).isoformat(),'people':{},'human_listening':False,'new_asr':False}
    for pid,pair in auth.items():
        owner=pair['owner'];subject=owner['subject_id'];root=f'/api/v1/workbench/subjects/{subject}'
        def call(method,url,who=owner,**kw):
            response=httpx.request(method,'http://127.0.0.1:8890'+url,headers={'Authorization':'Bearer '+who['actor_token']},trust_env=False,timeout=150,**kw)
            if response.status_code>=400: raise RuntimeError(str(response.status_code)+' '+response.json().get('error_code','request_failed'))
            return response.json()
        item=report['people'].setdefault(pid,{})
        cons=call('GET','/api/v1/consents?subject_id='+subject)
        consent=next(c['consent_id'] for c in cons if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
        if args.stage=='proposals':
            if item.get('status') in {'complete','failed','timed_out'}: continue
            if not item.get('job_id'):
                response=call('POST',root+'/narrative/suggest',json={'cloud_consent_id':consent})
                item.update(response);save(path,report)
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                jobs=call('GET',root+'/narrative/jobs')['items'];job=next(j for j in jobs if j['job_id']==item['job_id'])
                if job['status'] in {'complete','failed'}:
                    item.update(job);save(path,report);break
                time.sleep(2)
            else:item['status']='timed_out';save(path,report)
            data=call('GET',root+'/narrative');save(OUT/(pid+'-narrative.json'),data)
            print(pid,item['status'],'records',len(data['records']),flush=True)
        else:
            # Dev regression, explicitly separate from unseen holdout evaluation.
            gold=json.loads((ROOT/'evaluations/monthly-integration-v1/gold'/ (pid+'.json')).read_text(encoding='utf8'))
            sys.path.insert(0,str(ROOT/'tools/monthly_eval'))
            from product_loop import check_qa_scope,MAPPING
            mapping=json.loads(MAPPING.read_text(encoding='utf8'))
            grants=call('GET',root+'/grants',who=pair['reader'])['items']
            check_qa_scope(pid,gold['qa_protocol'],mapping,grants,
                call('GET',root+'/stories',who=pair['reader'])['items'],call('GET',root+'/revisions')['items'])
            reader_consent=next(g['grant_id'] for g in grants if g['cloud_processing_allowed'] and not g.get('revoked_at'))
            for case in gold['qa']:
                if args.case and case['id'] not in args.case:continue
                if case['id'] in item:continue
                result={'question':case['question'],'role':case['role'],'semantic_review':'pending'}
                start=time.monotonic()
                try: result['response']=call('POST',f'/api/v1/subjects/{subject}/twin/answers',who=pair[case['role']],json={'question':case['question'],'cloud_consent_id':consent if case['role']=='owner' else reader_consent})
                except Exception as exc:result['error']=str(exc)
                result['seconds']=round(time.monotonic()-start,3);item[case['id']]=result;save(path,report)
                print(case['id'],'saved' if 'response' in result else 'failed',flush=True)
    report['finished']=datetime.now(timezone.utc).isoformat();save(path,report)

if __name__=='__main__':main()

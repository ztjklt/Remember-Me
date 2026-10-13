"""Bounded explicit two-recording trials across the existing thirty recordings.

Retains every failed job. No automatic repair, confirmation, sharing or retry.
"""
import json,time,argparse
from pathlib import Path
import httpx
from live_check import save,ROOT,OUT,AUTH

def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group();group.add_argument('--retry-failed-v4',action='store_true');group.add_argument('--retry-failed-v5',action='store_true');args=parser.parse_args()
    retry=args.retry_failed_v4 or args.retry_failed_v5
    original=json.loads((OUT/('paired-recheck-v4.json' if args.retry_failed_v5 else 'paired-proposals.json')).read_text(encoding='utf8')) if retry else {}
    path=OUT/('paired-recheck-v5.json' if args.retry_failed_v5 else 'paired-recheck-v4.json' if retry else 'paired-proposals.json');report=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    for pid,pair in json.loads(AUTH.read_text(encoding='utf8')).items():
        owner=pair['owner'];subject=owner['subject_id'];root='/api/v1/workbench/subjects/'+subject
        def call(method,url,**kwargs):
            r=httpx.request(method,'http://127.0.0.1:8890'+url,headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,timeout=120,**kwargs)
            if not r.is_success: raise RuntimeError(f'HTTP {r.status_code} '+r.json().get('error_code','unknown'))
            return r.json()
        sources=call('GET',root+'/narrative')['source_evidence'];episodes=list(dict.fromkeys(s['episode_id'] for s in sources))
        consent=next(c['consent_id'] for c in call('GET','/api/v1/consents?subject_id='+subject) if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
        for i in range(0,len(episodes),2):
            key=pid+'-'+str(i//2+1)
            if retry and original.get(key,{}).get('status')!='failed':continue
            if report.get(key,{}).get('status') in {'complete','failed','timed_out'}:continue
            item=report.setdefault(key,{'person':pid,'episodes':episodes[i:i+2],'status':'starting','semantic_review':'pending',
                'previous_job_id':original.get(key,{}).get('job_id')});save(path,report)
            try:
                if not item.get('job_id'):
                    item.update(call('POST',root+'/narrative/suggest',json={'cloud_consent_id':consent,'episode_ids':item['episodes']}));save(path,report)
                deadline=time.monotonic()+150
                while time.monotonic()<deadline:
                    saved=next(j for j in call('GET',root+'/narrative/jobs')['items'] if j['job_id']==item['job_id'])
                    if saved['status'] in {'complete','failed'}:item.update(saved);break
                    time.sleep(2)
                else:item['status']='timed_out'
            except Exception as exc:item.update(status='failed',error=str(exc))
            save(path,report);save(OUT/(pid+'-paired-narrative.json'),call('GET',root+'/narrative'))
            print(key,item['status'],flush=True)

if __name__=='__main__':main()

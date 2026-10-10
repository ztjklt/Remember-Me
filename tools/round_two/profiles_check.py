"""One actual profile refresh per fictional person, no silent retry/approval."""
import argparse,json,time
import httpx
from live_check import AUTH,OUT,save

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--retry-timeout',action='store_true');args=parser.parse_args()
    # Explicit, bounded second attempt after the recorded life_review 504.
    path=OUT/('profile-timeout-recheck.json' if args.retry_timeout else 'profile-refresh.json');report=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    for pid,pair in json.loads(AUTH.read_text(encoding='utf8')).items():
        if args.retry_timeout and pid!='life_review':continue
        owner=pair['owner'];root='http://127.0.0.1:8890/api/v1/workbench/subjects/'+owner['subject_id']
        def call(method,url,**kwargs):
            r=httpx.request(method,url,headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,timeout=120,**kwargs)
            if not r.is_success:raise RuntimeError('HTTP '+str(r.status_code))
            return r.json()
        item=report.setdefault(pid,{})
        if item.get('status') in {'complete','failed','timed_out'}:continue
        if 'job_id' not in item:
            cons=call('GET','http://127.0.0.1:8890/api/v1/consents?subject_id='+owner['subject_id'])
            cid=next(c['consent_id'] for c in cons if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
            item.update(call('POST',root+'/profile-candidates/refresh',json={'cloud_consent_id':cid}));save(path,report)
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            data=call('GET',root+'/profile-candidates');job=next(j for j in data['jobs'] if j['job_id']==item['job_id'])
            if job['status'] in {'complete','failed'}:
                item.update(job);save(path,report);save(OUT/(pid+'-profiles-final.json'),data)
                save(OUT/(pid+'-narrative-final.json'),call('GET',root+'/narrative'));break
            time.sleep(2)
        else:item['status']='timed_out';save(path,report)
        print(pid,item['status'],flush=True)

if __name__=='__main__':main()

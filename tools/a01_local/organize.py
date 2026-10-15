"""Queue actual narrative organization after complete ASR ingestion, retain results."""
import json
import time
from pathlib import Path
import httpx
from ingest import BASE,VAR,STATE,request,save


def main():
    state=json.loads(STATE.read_text(encoding='utf8'))
    if len(state['episodes'])!=10 or any(e.get('status')!='ready' for e in state['episodes'].values()):
        raise SystemExit('All ten actual Episodes must be ready first.')
    account=json.loads((VAR/'private/local-accounts.json').read_text(encoding='utf8'))['owner']
    with httpx.Client(base_url=BASE,headers={'Origin':BASE},trust_env=False,timeout=120) as c:
        request(c,'POST','/api/v1/accounts/login',json={k:account[k] for k in ['username','password']})
        root='/api/v1/workbench/subjects/'+state['subject_id']
        if not state.get('narrative_jobs'):
            state['narrative_jobs']=[];save(STATE,state)
        # Bounded story tasks keep original per-recording context, in order.
        groups=[list(state['episodes'])[a:b] for a,b in [(0,4),(4,7),(7,10)]]
        for idx,keys in enumerate(groups):
            if len(state['narrative_jobs'])<=idx:
                job=request(c,'POST',root+'/narrative/suggest',json={'cloud_consent_id':state['CLOUD_TWIN'],
                    'episode_ids':[state['episodes'][k]['episode_id'] for k in keys]})
                state['narrative_jobs'].append(job);save(STATE,state)
            id=state['narrative_jobs'][idx]['job_id'];deadline=time.monotonic()+140
            while time.monotonic()<deadline:
                job=next(j for j in request(c,'GET',root+'/narrative/jobs')['items'] if j['job_id']==id)
                if job['status'] in {'complete','failed'}:
                    state['narrative_jobs'][idx]=job;save(STATE,state)
                    print(f'Narrative batch {idx+1}: '+job['status'],flush=True);break
                time.sleep(2)
            else:raise RuntimeError('Narrative remains running; inspect checkpoint instead of resubmitting.')
        result=request(c,'GET',root+'/narrative');save(VAR/'runtime/narrative-result.json',result)
        profiles=request(c,'GET',root+'/profile-candidates');save(VAR/'runtime/profile-result.json',profiles)
        print('Saved real proposals, no automatic confirmation.',flush=True)


if __name__=='__main__':main()

"""Exercise actual local APIs using new A01 audio, never substitute TTS scripts.

Technical ASR confirmation is explicitly logged, not claimed as human listening.
Checkpointed uploads/reviews use application idempotency; failure is retained.
"""
import hashlib
import argparse
import json
import secrets
import string
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[2]
VAR=ROOT/'services/backend/var/a01-20261012'
STATE=VAR/'runtime/ingest.json'
BASE='http://127.0.0.1:8891'


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)


def request(client,method,path,**kwargs):
    response=client.request(method,path,**kwargs)
    if response.is_error:
        try:code=response.json().get('error_code','HTTP_ERROR')
        except ValueError:code='HTTP_ERROR'
        raise RuntimeError(f'{method} {path}: {response.status_code} {code}')
    return response.json()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--retry-failed',action='store_true')
    parser.add_argument('--retry-reason',default='explicit local configuration repair');args=parser.parse_args()
    state=json.loads(STATE.read_text(encoding='utf8')) if STATE.exists() else {'episodes':{},'events':[]}
    creds_path=VAR/'private/local-accounts.json'
    if creds_path.exists():accounts=json.loads(creds_path.read_text(encoding='utf8'))
    else:
        accounts={key:dict(username=user,password=''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(8)),display_name=name)
            for key,user,name in [('owner','a01owner','陈国梁 · 虚构人物'),('reader','a01guest','A01 亲友体验')]}
        save(creds_path,accounts)
    clients={}
    for role,account in accounts.items():
        client=httpx.Client(base_url=BASE,timeout=120,trust_env=False,headers={'Origin':BASE})
        login=client.post('/api/v1/accounts/login',json={k:account[k] for k in ('username','password')})
        if login.status_code==401:
            result=request(client,'POST','/api/v1/accounts/register',json=account)
        else:
            login.raise_for_status();result=login.json()
        state[role+'_actor_id']=result['actor_id'];clients[role]=client
    client=clients['owner']
    spaces=request(client,'GET','/api/v1/workbench/spaces')['items']
    subject=next(s['subject_id'] for s in spaces if s['role']=='owner')
    state['subject_id']=subject;root=f'/api/v1/workbench/subjects/{subject}'
    for scope in ['RECORDING','CLOUD_TWIN']:
        if scope not in state:
            state[scope]=request(client,'POST','/api/v1/consents',json={'subject_id':subject,'scope':scope})['consent_id'];save(STATE,state)
    caps=request(client,'GET','/api/v1/workbench/capabilities')
    audio_root=VAR/'evaluation/speech'
    for n in range(1,11):
        key=f'A01_{n:02d}';entry=state['episodes'].setdefault(key,{})
        if entry.get('status')=='ready':continue
        audio=audio_root/(key+'.wav')
        if 'episode_id' not in entry:
            with audio.open('rb') as stream:
                result=request(client,'POST','/api/v1/episodes',data={'subject_id':subject,'recording_consent_id':state['RECORDING'],
                    'idempotency_key':'a01-new-audio-v1-'+key,'source':'IMPORT','recorded_at':f'2026-10-{n:02d}T09:00:00Z','audio_ref':key+'.wav',
                    'metadata':json.dumps({'cloud_asr_policy':caps['cloud_asr_policy'],'fictional_sample':'A01',
                        'audio_origin':'Xiaomi synthetic','recorded_at_kind':'simulated_story_order',
                        'review_basis':'user-authorized imperfect ASR technical confirmation; no human listening claim'})},
                    files={'file':(audio.name,stream,'audio/wav')})
            entry.update(result);entry['audio_sha256']=hashlib.sha256(audio.read_bytes()).hexdigest();save(STATE,state)
        eid=entry['episode_id'];deadline=time.monotonic()+240
        if entry.get('status')=='failed' and args.retry_failed:
            if entry.get('manual_retries',0)>=2:raise RuntimeError('Manual retry bound reached; inspect saved failure.')
            entry.setdefault('failures',[]).append({'error_code':entry.get('error_code'),'retry_reason':args.retry_reason})
            request(client,'POST',f'/api/v1/episodes/{eid}/retry')
            entry.update(status='retrying',manual_retries=entry.get('manual_retries',0)+1);save(STATE,state)
        while time.monotonic()<deadline:
            status=request(client,'GET',f'/api/v1/episodes/{eid}')
            review=request(client,'GET',f'/api/v1/episodes/{eid}/transcript-review')
            if review['state']=='reviewing':
                transcript=review['transcript']
                save(VAR/f'runtime/review/{key}.json',{'raw_review_response':review,'confirmed_text':transcript,
                    'basis':'technical-only; no script replacement; no human listening','audio_sha256':entry['audio_sha256']})
                request(client,'PATCH',f'/api/v1/episodes/{eid}/transcript-review',json={'transcript':transcript})
                entry['technical_confirmed']=True;save(STATE,state)
            if status['status']=='ready':
                entry['status']='ready';save(STATE,state);print(key+' saved + actual ASR + technical confirmation + real extraction',flush=True);break
            if status['status']=='failed':
                entry.update(status='failed',error_code=status.get('error_code'));save(STATE,state)
                raise RuntimeError(key+' failed '+str(status.get('error_code')))
            time.sleep(1)
        else:raise RuntimeError(key+' waiting beyond bounded local ingest timeout')
    # Explicit test sharing: illness story 07 remains private. No auto-wide grant.
    for key,entry in state['episodes'].items():
        if key=='A01_07' or entry.get('grant_id'):continue
        result=request(client,'POST',root+'/grants',json={'episode_id':entry['episode_id'],'reader_actor_id':state['reader_actor_id'],
            'include_audio_confirmed':True,'cloud_processing_allowed':True})
        entry['grant_id']=result['grant_id'];save(STATE,state)
    if not state.get('profile_job'):
        state['profile_job']=request(client,'POST',root+'/profile-candidates/refresh',json={'cloud_consent_id':state['CLOUD_TWIN']});save(STATE,state)
    print('Ten episode flow complete; profile remains candidate-only; A01_07 private.',flush=True)
    for client in clients.values():client.close()


if __name__=='__main__':main()

"""Real IP HTTPS test with fresh Paraformer and Weixin calls; no desktop ASR.

Reuses a documented fictional archived microphone file as IMPORT. Separate
written supplements test corrections without pretending they were spoken.
Passwords/tokens are read from ignored files; result files never contain them.
"""
import argparse,hashlib,json,ssl,time
from pathlib import Path
from datetime import datetime,timezone
import httpx
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'services/backend/var/paired-delivery'
SOURCE=ROOT/'services/backend/var/android-client-relay-probe/native-original.m4a'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--staging-root',type=Path);args=parser.parse_args()
    stage=args.staging_root
    if stage and (stage.parent!=Path('/var/lib/remember-me') or not stage.name.startswith('paired-stage-')):
        raise ValueError('Only explicit ECS staging roots are allowed')
    credentials=json.loads(((stage/'accounts.json') if stage else OUT/'ecs-accounts.json').read_text('utf8'))
    report_path=(stage/'smoke.json') if stage else OUT/'ecs-pair-smoke.json'
    report=json.loads(report_path.read_text('utf8')) if report_path.exists() else {'fresh_asr':True,'source':'archived fictional native audio imported over IP HTTPS','human_listening':False,'physical_phone':False,'episodes':{},'cycles':[]}
    if stage:report.update(network='ECS loopback isolated staging, not public APK validation',source='archived fictional audio imported in isolated staging')
    def save():
        temp=report_path.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(report_path)
    def result(r):
        if r.status_code>=400:raise RuntimeError(str(r.status_code)+' '+r.json().get('error_code','HTTP_ERROR'))
        return r.json()
    context=ssl.create_default_context(cafile=str(ROOT/'apps/android/app/src/internal/res/raw/remember_ecs_ip_demo.pem'))
    clients={}
    try:
        for role,row in credentials.items():
            c=httpx.Client(base_url='http://127.0.0.1:8880' if stage else 'https://39.108.183.47',verify=context,trust_env=False,timeout=150)
            auth=result(c.post('/api/v1/accounts/login',json={k:row[k] for k in ['username','password']}))
            c.headers['Authorization']='Bearer '+auth['actor_token'];clients[role]=c
        owner,reader=clients['owner'],clients['reader'];subject=credentials['owner']['subject_id'];root=f'/api/v1/workbench/subjects/{subject}'
        report['service_info']=result(owner.get('/api/v1/service-info'));assert not report['service_info']['registration_allowed']
        caps=result(owner.get('/api/v1/workbench/capabilities'));assert caps['stt_model']=='paraformer-v2'
        def consent(scope):
            values=result(owner.get('/api/v1/consents',params={'subject_id':subject}))
            old=next((c for c in values if c['scope']==scope and c['status']=='granted'),None)
            return old['consent_id'] if old else result(owner.post('/api/v1/consents',json={'subject_id':subject,'scope':scope}))['consent_id']
        rec=consent('RECORDING');cloud=consent('CLOUD_TWIN')
        def story(ep):return next(x for x in result(owner.get(root+'/stories'))['items'] if x['episode_id']==ep)
        def wait(ep,review=False):
            for _ in range(100):
                s=story(ep)
                if s['status']=='failed':raise RuntimeError('Episode failed: '+s.get('error_code','unknown'))
                if s['status']=='ready' or review and s.get('waiting_for_review'):return s
                time.sleep(2)
            raise TimeoutError('Episode stage did not complete')
        def upload(key,supplement,target=None):
            row=report['episodes'].setdefault(key,{})
            if 'episode_id' not in row:
                with SOURCE.open('rb') as f:
                    meta={'cloud_asr_policy':caps['cloud_asr_policy'],'acceptance':'paired-v1 archived import'}
                    row['episode_id']=result(owner.post('/api/v1/episodes',data={'subject_id':subject,'source':'IMPORT','recorded_at':datetime.now(timezone.utc).isoformat(),'audio_ref':SOURCE.name,'duration_ms':'19622','idempotency_key':'paired-v1-'+key,'recording_consent_id':rec,'metadata':json.dumps(meta)},files={'file':(SOURCE.name,f,'audio/mp4')}))['episode_id'];save()
            ep=row['episode_id']
            if target and 'revision' not in row:
                row['revision']=result(owner.post(root+'/revisions',json={'target_memory_id':target,'episode_id':ep,'kind':'correction'}));save()
            s=wait(ep,True)
            if s.get('waiting_for_review'):
                assert not s['memories'];row['before_review']=s;save()
                review=result(owner.get(f'/api/v1/episodes/{ep}/transcript-review'))
                text=review['transcript'].replace('不要正经','不要挣钱')
                # The experiment's explicit written supplement is not ASR output.
                result(owner.patch(f'/api/v1/episodes/{ep}/transcript-review',json={'transcript':text,'supplement':supplement}))
            s=wait(ep);assert s['memories'];row['story']=s;save();return ep,s
        first,initial=upload('initial','虚构测试的本人书面补充：我的名字写作方宁。第一份工作从2011年开始。')
        report['original_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        assert hashlib.sha256(owner.get(root+f'/stories/{first}/audio').content).hexdigest()==report['original_sha256']
        def share(ep,known=False):
            selection={'episode_ids':[ep]};p=result(owner.post(root+'/sharing/preview',json=selection))
            body={**selection,'source_version':p['source_version'],'include_audio_confirmed':True,'cloud_processing_allowed':True}
            if known:body['recipient_actor_id']=credentials['reader']['actor_id']
            inv=result(owner.post(root+'/invitations',json=body));path=root+'/invitations/'+inv['id']
            if not known:
                result(reader.post('/api/v1/workbench/invitations/claim',json={'code':inv['code']}))
                assert reader.get(root+f'/stories/{ep}/audio').status_code==404
            return result(owner.post(path+'/approve')),path
        def ask(c,q,grant):return result(c.post(f'/api/v1/subjects/{subject}/twin/answers',json={'question':q,'cloud_consent_id':grant}))
        if not report.get('initial_share'):
            inv,path=share(first);report['initial_share']={'invitation':inv,'path':path};save()
        gid=report['initial_share']['invitation']['grant_ids'][0]
        if 'initial_answer' not in report:
            report['initial_answer']=ask(reader,'第一份工作从哪一年开始？',gid);save()
        if 'request' not in report:
            report['request']=result(reader.post(root+'/requests',json={'text':'你为什么一直保留这个蓝色水杯？'}));save()
        reply,reply_story=upload('reply','虚构测试的本人书面回答：我保留蓝色水杯，因为那是母亲送我的生日礼物。')
        result(owner.patch(root+'/requests/'+report['request']['request_id'],json={'status':'answered','answer_episode_id':reply}))
        assert reader.get(root+f'/stories/{reply}/audio').status_code==404
        report['reply_private_before_share']=True
        if 'reply_share' not in report:
            inv,path=share(reply,True);report['reply_share']={'invitation':inv,'path':path};save()
        if 'reply_answer' not in report:
            report['reply_answer']=ask(reader,'为什么保留蓝色水杯？',gid);save()
        target=next(m['memory_item_id'] for m in initial['memories'] if '2011' in m['statement'])
        corrected,corrected_story=upload('correction','虚构测试的本人书面纠正：之前的2011年写错了，第一份工作是2012年开始，不是2011年。',target)
        rev=report['episodes']['correction']['revision'];result(owner.post(root+'/revisions/'+rev['revision_id']+'/confirm'))
        assert reader.get(root+f'/stories/{corrected}/audio').status_code==404
        if 'corrected_owner_answer' not in report:
            report['corrected_owner_answer']=ask(owner,'第一份工作从哪一年开始？',cloud);save()
        if 'correction_share' not in report:
            inv,path=share(corrected,True);report['correction_share']={'invitation':inv,'path':path};save()
        if 'corrected_reader_answer' not in report:
            report['corrected_reader_answer']=ask(reader,'第一份工作从哪一年开始？',report['correction_share']['invitation']['grant_ids'][0]);save()
        # Bounded repeated read/revoke/explicit reshare on the new answer story.
        for n in range(len(report['cycles']),3):
            entry=report['reply_share'] if n==0 else None
            if entry:inv,path=entry['invitation'],entry['path']
            else:inv,path=share(reply,True)
            data=reader.get(root+f'/stories/{reply}/audio');assert data.status_code==200
            result(owner.post(path+'/revoke'));denied=reader.get(root+f'/stories/{reply}/audio').status_code;assert denied==404
            report['cycles'].append({'round':n+1,'invitation_id':inv['id'],'audio_before':200,'audio_after':denied});save()
        # Leave a usable explicit final sharing for interactive installation checks.
        if 'interactive_reply_share' not in report:
            inv,path=share(reply,True);report['interactive_reply_share']={'invitation':inv,'path':path};save()
        report['finished']=datetime.now(timezone.utc).isoformat();save()
        print(json.dumps({'episodes':len(report['episodes']),'revoke_cycles':len(report['cycles']),'result':'saved; semantic review separate','server':report['service_info']}))
    except Exception as exc:
        report.setdefault('failures',[]).append({'time':datetime.now(timezone.utc).isoformat(),'error':str(exc)});save();raise
    finally:
        for c in clients.values():
            try:c.post('/api/v1/accounts/logout')
            finally:c.close()

if __name__=='__main__':main()

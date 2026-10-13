"""Real local acceptance via ordinary account APIs; no direct database writes.

Reuses immutable Xiaomi fictional speech, obtains fresh Groq ASR and Weixin
results. Technical ASR confirmation is not human listening. Approval requires
an explicit ID after reviewing saved output. Credentials stay in ignored var.
"""
import argparse
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone

import httpx
from product_loop import call
from speech_pipeline import OUT, save
from cloud_asr_samples import wait_for_review
from cloud_followthrough import Steps, wait_profile


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',required=True)
    p.add_argument('--stage',choices=['initial','supplement','relations','remaining','verify','questions'],required=True)
    p.add_argument('--confirm-candidate')
    p.add_argument('--confirm-update')
    args=p.parse_args()
    if not args.run.replace('-','').isalnum(): raise SystemExit('Invalid run')
    folder=OUT/args.run;folder.mkdir(exist_ok=True)
    steps=Steps(folder/'steps.json')
    report_path=folder/'report.json'
    report=json.loads(report_path.read_text(encoding='utf8')) if report_path.exists() else {
        'run':args.run,'human_listening':False,'natural_microphone':False,
        'source':'immutable fictional Xiaomi TTS, new Groq ASR', 'episodes':{}, 'checks':[]}
    def persist(): save(report_path,report)
    credentials=folder/'credentials.json'
    auth=json.loads(credentials.read_text(encoding='utf8')) if credentials.exists() else {}
    for role in ['owner','reader']:
        if role not in auth:
            auth[role]={'username':args.run+'-'+role,'password':secrets.token_urlsafe(24),
                        'display_name':'真实链路虚构测试·'+role};save(credentials,auth)
        def register(role=role):
            response=httpx.post('http://127.0.0.1:8877/api/v1/accounts/register',json=auth[role],trust_env=False,timeout=30)
            if response.status_code!=201: raise RuntimeError('Account registration HTTP '+str(response.status_code))
            return response.json()
        auth[role]['session']=steps.once('register/'+role,register)
        identity=auth[role]['session']
        identity['subject_id']=next(s['subject_id'] for s in call('GET','/api/v1/workbench/spaces',identity)['items'] if s['role']=='owner')
        save(credentials,auth)
    owner,reader=auth['owner']['session'],auth['reader']['session'];subject=owner['subject_id']
    root='/api/v1/workbench/subjects/'+subject;api='/api/v1/subjects/'+subject;profiles=root+'/profile-candidates'
    def mutate(key,path,body=None,who=owner,method='POST',**kwargs):
        return steps.once(key,lambda:call(method,path,who,**({'json':body} if body is not None else {}),**kwargs))
    record=mutate('record-consent','/api/v1/consents',{'subject_id':subject,'scope':'RECORDING'})['consent_id']
    cloud=mutate('cloud-consent','/api/v1/consents',{'subject_id':subject,'scope':'CLOUD_TWIN'})['consent_id']
    caps=call('GET','/api/v1/workbench/capabilities',owner)
    if caps['stt']!='groq' or not caps['stt_configured']: raise RuntimeError('Groq required, no fallback')
    report.update(subject_id=subject,owner_actor_id=owner['actor_id'],reader_actor_id=reader['actor_id'])
    def upload(name, revision=None):
        path=OUT/'state-loop'/(name+'.wav');raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        manifest=json.loads(path.with_suffix('.json').read_text(encoding='utf8'))
        if sha!=manifest['audio_sha256']: raise RuntimeError('Immutable Xiaomi audio changed')
        ep=mutate('upload/'+name,'/api/v1/episodes',data={
            'subject_id':subject,'recording_consent_id':record,'source':'IMPORT',
            'recorded_at':datetime.now(timezone.utc).isoformat(),'audio_ref':path.name,
            'idempotency_key':args.run+'-'+name,
            'metadata':json.dumps({'fictional':True,'cloud_asr_policy':caps['cloud_asr_policy']})},
            files={'file':(path.name,raw,'audio/wav')})['episode_id']
        row=report['episodes'].setdefault(name,{'episode_id':ep,'audio_sha256':sha});persist()
        if revision:
            proposed=mutate(name+'-proposal',root+'/revisions',{**revision,'episode_id':ep})
            row['revision_id']=proposed['revision_id'];persist()
        wait_for_review(owner,ep,folder/(name+'.asr-review.json'),row,persist,seconds=300)
        story=next(s for s in call('GET',root+'/stories',owner)['items'] if s['episode_id']==ep)
        save(folder/(name+'.story.json'),story)
        if story['stt_model_version']!='groq/whisper-large-v3': raise RuntimeError('Wrong ASR provenance')
        if not story['memories'] or any(e['excerpt'] not in story['transcript'] for m in story['memories'] for e in m['evidence']):
            raise RuntimeError('Extraction or exact evidence failed')
        response=httpx.get('http://127.0.0.1:8877'+root+'/stories/'+ep+'/audio',
            headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,timeout=30)
        assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==sha
        row.update(audio_hash_verified=True,memories=len(story['memories']),status='ready');persist()
        print('Ready',name,'memories',len(story['memories']),flush=True)
        return story
    def job(label,action):
        j=mutate(label,profiles+'/'+action,{'cloud_consent_id':cloud})
        data=wait_profile(lambda:call('GET',profiles,owner),j['job_id'],seconds=180)
        save(folder/(label+'.json'),data);return data
    if args.confirm_candidate:
        data=call('GET',profiles,owner)
        candidate=next(c for c in data['items'] if c['candidate_id']==args.confirm_candidate and c['status']=='pending')
        assert candidate['evidence']
        mutate('approve/'+args.confirm_candidate,profiles+'/'+args.confirm_candidate+'/confirm')
        report['approval']='assistant reviewed fictional evidence, not human participant';persist()
    if args.confirm_update:
        mutate('approve-update/'+args.confirm_update,profiles+'/updates/'+args.confirm_update+'/confirm')
    if args.stage=='initial':
        upload('initial');job('initial-profile','refresh')
    elif args.stage=='supplement':
        upload('supplement');job('supplement-profile','refresh')
    elif args.stage=='relations':
        job('suggest-relations','suggest-relations')
        save(folder/'relation-updates.json',call('GET',profiles+'/updates',owner))
    elif args.stage=='remaining':
        stories=call('GET',root+'/stories',owner)['items']
        original=next(s for s in stories if s['episode_id']==report['episodes']['initial']['episode_id'])
        # Select the actual ASR-derived move memory; never modify it to match gold.
        target=next(m for m in original['memories'] if '苏州' in m['content'] and ('2010' in m['content'] or '二零一零' in m['content']))
        corrected=upload('correction',{'target_memory_id':target['memory_item_id'],'kind':'correction'})
        mutate('correction-confirm',root+'/revisions/'+report['episodes']['correction']['revision_id']+'/confirm')
        current=next(m for m in corrected['memories'] if '苏州' in m['content'])
        upload('change',{'target_memory_id':current['memory_item_id'],'kind':'change','time_text':'2019年'})
        mutate('change-confirm',root+'/revisions/'+report['episodes']['change']['revision_id']+'/confirm')
        upload('private')
        for label,q in [('year','讲述者哪一年搬到苏州？'),('now','讲述者后来搬到了哪里，现在住在哪里？'),('unknown','讲述者银行卡的密码是多少？')]:
            report[label]=mutate('qa/'+label,api+'/twin/answers',{'question':q,'cloud_consent_id':cloud});persist()
    elif args.stage=='questions':
        ep=report['episodes']['supplement']['episode_id']
        grant=mutate('questions/grant',root+'/grants',{'episode_id':ep,'reader_actor_id':reader['actor_id'],
            'include_audio_confirmed':True,'cloud_processing_allowed':True})
        question='为什么喜欢不加糖的茶？'
        asked=mutate('questions/request',root+'/requests',{'text':question},who=reader)
        mutate('questions/later',root+'/requests/'+asked['request_id'],{'status':'snoozed'},method='PATCH')
        story=upload('answer')
        mutate('questions/answered',root+'/requests/'+asked['request_id'],
            {'status':'answered','answer_episode_id':story['episode_id']},method='PATCH')
        before=mutate('questions/before-share',api+'/twin/answers',{'question':question,'cloud_consent_id':grant['grant_id']},who=reader)
        hidden=next(r for r in call('GET',root+'/requests',reader)['items'] if r['request_id']==asked['request_id'])
        assert hidden['answer_episode_id'] is None and before['response_type']=='UNKNOWN'
        shared=mutate('questions/share-answer',root+'/grants',{'episode_id':story['episode_id'],'reader_actor_id':reader['actor_id'],
            'include_audio_confirmed':True,'cloud_processing_allowed':True})
        after=mutate('questions/after-share',api+'/twin/answers',{'question':question,'cloud_consent_id':shared['grant_id']},who=reader)
        assert after['response_type']!='UNKNOWN' and any(e['episode_id']==story['episode_id'] for e in after['evidence'])
        report['question_cycle']={'request_id':asked['request_id'],'hidden_before_share':True,'before':before,'after':after};persist()
        for label,g in [('story',grant),('answer',shared)]:mutate('questions/revoke-'+label,root+'/grants/'+g['grant_id'],method='DELETE')
    elif args.stage=='verify':
        ep=report['episodes']['supplement']['episode_id'];private=report['episodes']['private']['episode_id']
        for n in range(3):
            grant=mutate(f'grant/{n}',root+'/grants',{'episode_id':ep,'reader_actor_id':reader['actor_id'],
                'include_audio_confirmed':True,'cloud_processing_allowed':True})
            answer=mutate(f'reader-qa/{n}',api+'/twin/answers',{'question':'方宁是讲述者的亲属吗？讲述者喜欢怎样喝茶？',
                'cloud_consent_id':grant['grant_id']},who=reader)
            visible=call('GET',root+'/stories',reader)['items'];assert {s['episode_id'] for s in visible}=={ep}
            assert all(e['episode_id']==ep for e in answer['evidence'])
            mutate(f'revoke/{n}',root+'/grants/'+grant['grant_id'],method='DELETE')
            codes=[]
            for path in [root+'/stories/'+ep+'/audio',root+'/stories/'+private+'/audio',api+'/twin/answers/'+answer['answer_id']]:
                response=httpx.get('http://127.0.0.1:8877'+path,headers={'Authorization':'Bearer '+reader['actor_token']},trust_env=False,timeout=30)
                codes.append(response.status_code)
            assert codes==[404,404,404]
            report['checks'].append({'round':n+1,'visible_only_shared_story':True,'after_revoke_codes':codes,'answer':answer});persist()
        report['finished_at']=datetime.now(timezone.utc).isoformat()
    persist();print('Stage saved:',args.stage,flush=True)


if __name__=='__main__':main()

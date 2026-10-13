"""Actual profile generation and three reader grant/revoke cycles after native capture."""
from pathlib import Path
import json,secrets,time
import httpx
from record_live import OUT,BASE,api

def save(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    owner=json.loads((OUT/'credentials.json').read_text(encoding='utf-8'))
    native=json.loads((OUT/'result.json').read_text(encoding='utf-8'));assert native['complete']
    sid=native['subject_id'];root=f'/api/v1/workbench/subjects/{sid}'
    with httpx.Client(timeout=120,trust_env=False,headers={'Authorization':'Bearer '+owner['actor_token']}) as c:
        stories=api(c,root+'/stories')['items'];ep=stories[0]['episode_id']
        consent=next(row['consent_id'] for row in api(c,'/api/v1/consents?subject_id='+sid) if row['scope']=='CLOUD_TWIN' and row['status']=='granted')
        api(c,root+'/vocabulary',method='PUT',json={'text':'测试私密词表：栀子42，仅保存在词表，未带入故事。'})
        if not (OUT/'profile-request.json').exists():
            request=api(c,root+'/profile-candidates/refresh',method='POST',json={'cloud_consent_id':consent})
            save('profile-request.json',request)
        for _ in range(60):
            profile=api(c,root+'/profile-candidates');save('profile.json',profile)
            if not any(j['status'] in ('queued','running') for j in profile.get('jobs',[])):break
            time.sleep(2)
        else:raise RuntimeError('Profile timeout; job preserved')
        if not profile['items']:raise RuntimeError('No profile candidates, inspect saved jobs')
        # No blanket auto-approval. Candidate facts are reviewed separately.
        if (OUT/'reader.json').exists():reader=json.loads((OUT/'reader.json').read_text(encoding='utf-8'))
        else:
            with httpx.Client(timeout=30,trust_env=False) as r:
                reader=api(r,'/api/v1/accounts/register',method='POST',json={'username':'reader_'+secrets.token_hex(5),'password':secrets.token_urlsafe(24),'display_name':'独立手机测试读者'})
            save('reader.json',reader)
        report=json.loads((OUT/'followthrough.json').read_text(encoding='utf-8')) if (OUT/'followthrough.json').exists() else {'profile_candidates':len(profile['items']),'cycles':[], 'failures':[]}
        with httpx.Client(timeout=120,trust_env=False,headers={'Authorization':'Bearer '+reader['actor_token']}) as r:
            for i in range(len(report['cycles']),3):
                grant=api(c,root+'/grants',method='POST',json={'episode_id':ep,'reader_actor_id':reader['actor_id'],'include_audio_confirmed':True,'cloud_processing_allowed':True})
                visible=api(r,root+'/stories')
                assert '栀子42' not in json.dumps(visible,ensure_ascii=False)
                assert r.get(BASE+root+'/vocabulary').status_code==404
                try:
                    answer=api(r,f'/api/v1/subjects/{sid}/twin/answers',method='POST',json={'question':'记录者说的落屋是什么意思？老隗是什么关系？','cloud_consent_id':grant['grant_id']})
                except Exception as error:
                    report['failures'].append({'round':i+1,'at':time.time(),'error':str(error)})
                    save('followthrough.json',report)
                    raise
                assert answer['response_type']=='SIMULATION',answer
                assert answer['evidence'] and all(e['excerpt'] in '\n'.join(m['content'] for s in stories for m in s['memories']) for e in answer['evidence'])
                portrait=api(r,root+'/portrait');assert portrait['scope']=='shared_stories_only' and '栀子42' not in json.dumps(portrait,ensure_ascii=False)
                audio=r.get(BASE+root+f'/stories/{ep}/audio');assert audio.status_code==200
                api(c,root+'/grants/'+grant['grant_id'],method='DELETE')
                audio_after=r.get(BASE+root+f'/stories/{ep}/audio').status_code
                answer_after=r.get(BASE+f'/api/v1/subjects/{sid}/twin/answers/'+answer['answer_id']).status_code
                assert audio_after==answer_after==404
                report['cycles'].append({'round':i+1,'answer':answer,'audio_before':200,'audio_after':audio_after,'answer_after':answer_after,'private_vocabulary_visible':False})
                save('followthrough.json',report)
                print('reader cycle',i+1,'complete',flush=True)
        print('profile candidates',len(profile['items']),'not automatically approved',flush=True)

if __name__=='__main__':main()

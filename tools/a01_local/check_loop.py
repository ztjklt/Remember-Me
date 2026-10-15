"""Real API QA and source-gated sharing for the isolated fictional A01 space."""
import json
import uuid
import httpx
from ingest import BASE,VAR,STATE,request,save


def main():
    result_path=VAR/'runtime/loop-check.json'
    result=json.loads(result_path.read_text(encoding='utf8')) if result_path.exists() else {'checks':[],'qa':[]}
    state=json.loads(STATE.read_text(encoding='utf8')); accounts=json.loads((VAR/'private/local-accounts.json').read_text(encoding='utf8'))
    clients={}
    for role,account in accounts.items():
        client=httpx.Client(base_url=BASE,headers={'Origin':BASE},trust_env=False,timeout=120)
        request(client,'POST','/api/v1/accounts/login',json={k:account[k] for k in ['username','password']});clients[role]=client
    own,reader=clients['owner'],clients['reader'];root='/api/v1/workbench/subjects/'+state['subject_id']
    if not result.get('invitation_id'):
        selection={'episode_ids':[state['episodes']['A01_01']['episode_id']]}
        preview=request(own,'POST',root+'/sharing/preview',json=selection)
        invite=request(own,'POST',root+'/invitations',json={**selection,'source_version':preview['source_version'],
            'include_audio_confirmed':True,'cloud_processing_allowed':True})
        request(reader,'POST','/api/v1/workbench/invitations/claim',json={'code':invite['code']})
        request(own,'POST',root+'/invitations/'+invite['id']+'/approve')
        result['invitation_id']=invite['id'];result['checks'].append('normal invitation claim + owner account approval');save(result_path,result)
    items=request(reader,'GET',root+'/stories')['items']
    private=state['episodes']['A01_07']['episode_id']
    assert private not in {item['episode_id'] for item in items}
    denied=reader.get(root+'/stories/'+private+'/audio');assert denied.status_code==404
    result['reader_visible_episodes']=len(items);result['private_audio_status']=denied.status_code
    cases=[('owner','讲述者为什么给豆豆买贵一些的画笔？',None),
           ('reader','讲述者与桂芳第一次见面是星期几？','UNKNOWN'),
           ('reader','医生告诉讲述者具体得了什么病？','UNKNOWN')]
    for index,(role,question,expected) in enumerate(cases):
        if any(q['index']==index for q in result['qa']):continue
        consent=state['CLOUD_TWIN'] if role=='owner' else state['episodes']['A01_01']['grant_id']
        try:
            answer=request(clients[role],'POST',f"/api/v1/subjects/{state['subject_id']}/twin/answers",json={'question':question,'cloud_consent_id':consent})
            row={'index':index,'role':role,'question':question,'actual':answer,'expected_response_type':expected,
                 'type_matches':not expected or answer['response_type']==expected,'semantic_review':'pending'}
        except Exception as exc:row={'index':index,'role':role,'question':question,'failure':str(exc),'semantic_review':'failed_delivery'}
        result['qa'].append(row);save(result_path,result)
    if not result.get('snapshot_checks'):
        records=request(own,'GET',root+'/narrative')['records']
        selected=next(r for r in records if r['title']=='老车床螺丝松动' and r['status']=='confirmed')
        episode=state['episodes']['A01_02']['episode_id']; rounds=[]
        for index in range(3):
            body={'narrative_ids':[selected['id']],'profile_candidate_ids':[],'recipient_actor_ids':[state['reader_actor_id']]}
            preview=request(own,'POST',root+'/companion/snapshots/preview',json=body)
            snap=request(own,'POST',root+'/companion/snapshots',json={**body,'idempotency_key':'a01-snapshot-check-'+uuid.uuid4().hex,
                 'source_version':preview['source_version'],'confirmed':True})
            route=root+'/companion/snapshots/'+snap['id']
            assert reader.get(route).status_code==200
            grants=request(own,'GET',root+'/grants')['items']
            grant=next(g for g in grants if g['episode_id']==episode and g['reader_actor_id']==state['reader_actor_id'] and not g.get('revoked_at'))
            request(own,'DELETE',root+'/grants/'+grant['grant_id'])
            assert reader.get(route).status_code==404
            assert reader.get(root+'/stories/'+episode+'/audio').status_code==404
            # Restore this explicit test grant so the demonstration stays usable.
            restored=request(own,'POST',root+'/grants',json={'episode_id':episode,'reader_actor_id':state['reader_actor_id'],
                'include_audio_confirmed':True,'cloud_processing_allowed':True})
            state['episodes']['A01_02']['grant_id']=restored['grant_id'];save(STATE,state)
            request(own,'POST',route+'/revoke',json={'revision':snap['revision']})
            assert reader.get(route).status_code==404
            rounds.append({'round':index+1,'before':200,'after_source_revoke':404,'old_audio':404,'after_snapshot_revoke':404})
            save(VAR/'runtime/snapshot-rounds.json',rounds)
        result['snapshot_checks']=rounds;save(result_path,result)
    print('Actual local API checks recorded; evaluate QA prose separately.')


if __name__=='__main__':main()

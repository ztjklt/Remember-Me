"""Real local API story/split/history cycle on the fictional evaluation copy."""
import json
import httpx
from live_check import AUTH,OUT,save

def main():
    out=OUT/'story-cycle.json'
    if out.exists():raise SystemExit('Existing cycle retained; do not duplicate its records')
    owner=json.loads(AUTH.read_text(encoding='utf8'))['life_review']['owner']
    root='http://127.0.0.1:8890/api/v1/workbench/subjects/'+owner['subject_id']+'/narrative'
    def call(method,path='',**kwargs):
        r=httpx.request(method,root+path,headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,**kwargs)
        if not r.is_success:raise RuntimeError(str(r.status_code)+' '+r.json().get('error_code','failed'))
        return r.json()
    data=call('GET');sources={e['evidence_id']:e for e in data['source_evidence']}
    refs=['ev_ce4d45c6f3444ab8','ev_e091a596d1f8474b','ev_842350e26e42405b']
    assert len({sources[e]['episode_id'] for e in refs})==2
    body=dict(kind='story',title='同一次开张：后来确认年份',
        text='讲述者再次回忆同一张长方形展示桌，不是第二次开张。后来确认工作室开张是2009年，不是2008年；筹备从哪天开始仍不确定。',
        evidence_ids=refs,facets=['EXPERIENCE'],time_text='2009年',same_event=True)
    row=call('POST','/records',json=body);record=row['id'];report={'reviewer':'assistant','fictional_only':True,'two_recordings':True,'record_id':record,'steps':[]}
    def checkpoint(action,value):report['steps'].append({'action':action,'record':value});save(out,report)
    row=call('POST','/records/'+record+'/confirm',json={'revision':row['revision']});checkpoint('confirm_group',row)
    assert row['status']=='confirmed'
    split={**body,'revision':row['revision'],'title':'拆出的年份说明','text':'工作室开张是2009年，不是2008年。','evidence_ids':refs[1:],'same_event':False}
    child=call('POST','/records/'+record+'/split',json=split);checkpoint('split',child)
    old=next(r for r in call('GET')['records'] if r['id']==record)
    assert old['status']==child['status']=='pending' and set(old['evidence_ids']).isdisjoint(child['evidence_ids'])
    row=call('POST','/records/'+record+'/undo',json={'revision':old['revision']});checkpoint('restore_pending',row)
    assert row['status']=='pending' and set(row['evidence_ids'])==set(refs)
    row=call('POST','/records/'+record+'/confirm',json={'revision':row['revision']});checkpoint('reconfirm',row)
    child=call('POST','/records/'+child['id']+'/reject',json={'revision':child['revision']});checkpoint('withdraw_split',child)
    report['history']=call('GET','/records/'+record+'/history')['items']
    assert len(report['history'])==5
    report['passed']=True;save(out,report);print('Two recordings grouped, split, restored and reconfirmed through HTTP.')

if __name__=='__main__':main()

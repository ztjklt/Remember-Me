"""Opt-in technical review of fictional sources; local copied DB only.

Run after the 60-question checked regression is finished. Never replaces ASR,
never publishes, and restores style to disabled and any temporary grants.
"""
import json,time
import httpx
from live_check import AUTH,OUT,save

def main():
    qa=json.loads((OUT/'qa-checked.json').read_text(encoding='utf8'))
    if not qa.get('finished'): raise SystemExit('Finish the fixed-scope QA run first')
    pair=json.loads(AUTH.read_text(encoding='utf8'))['bus_driver']
    owner,reader=pair['owner'],pair['reader']; subject=owner['subject_id']
    root='/api/v1/workbench/subjects/'+subject; endpoint='http://127.0.0.1:8890'
    path=OUT/'letters-style.json'
    report=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'fictional_only':True,'reviewer':'assistant','human_listening':False,'cycles':[]}
    def call(method,url,who=owner,**kwargs):
        r=httpx.request(method,endpoint+url,headers={'Authorization':'Bearer '+who['actor_token']},trust_env=False,timeout=240,**kwargs)
        if not r.is_success:raise RuntimeError(str(r.status_code)+' '+r.json().get('error_code','request_failed'))
        return r.json()
    def data(who=owner):return call('GET',root+'/narrative',who)
    source=next(e for e in data()['source_evidence'] if e['evidence_id']=='ev_125aec5d7dd8412b')
    assert source['excerpt']=='我的回忆属于我女儿可以用她自己的方式理解不需要为了记住我就走同一条路'
    for kind,title in [('letter','给女儿：用自己的方式理解'),('style','表达范例：尊重不同的人生')]:
        if kind in report:continue
        row=call('POST',root+'/narrative/records',json=dict(kind=kind,title=title,text=source['excerpt'],evidence_ids=[source['evidence_id']],facets=['EXPRESSION'],recipient_label='女儿' if kind=='letter' else ''))
        row=call('POST',root+'/narrative/records/'+row['id']+'/confirm',json={'revision':row['revision']})
        report[kind]=row;save(path,report)
    record_ids={report[k]['id'] for k in ('letter','style')}
    assert not record_ids & {r['id'] for r in data(reader)['records']},'Recipient label must not grant access'
    report['recipient_is_not_grant']=True;save(path,report)
    try:
        if 'answer' not in report and 'answer_error' not in report:
            pref=data()['style'];call('PUT',root+'/narrative/style',json={'enabled':True,'revision':pref['revision']})
            consent=next(c['consent_id'] for c in call('GET','/api/v1/consents?subject_id='+subject) if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
            start=time.monotonic()
            try:report['answer']=call('POST','/api/v1/subjects/'+subject+'/twin/answers',json={'question':'讲述者喜欢怎样的茶？他要求女儿走和自己一样的人生道路吗？请分别说明。','cloud_consent_id':consent})
            except Exception as exc:report['answer_error']=str(exc)
            report['seconds']=round(time.monotonic()-start,3);save(path,report)
    finally:
        pref=data()['style']
        if pref['enabled']:call('PUT',root+'/narrative/style',json={'enabled':False,'revision':pref['revision']})
    if 'answer' in report:
        old=call('GET','/api/v1/subjects/'+subject+'/twin/answers/'+report['answer']['answer_id'])
        assert old['stale'] and old['expression'] is None
        report['disable_invalidates_answer']=True
    report['style_restored_disabled']=not data()['style']['enabled'];save(path,report)
    # The first quote is in a recording with a later correction: sharing that
    # entire old recording is correctly blocked. Exercise re-grants on an
    # unaltered fictional private recording instead, without relaxing the rule.
    blocked=httpx.post(endpoint+root+'/grants',headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,
        json={'episode_id':source['episode_id'],'reader_actor_id':reader['actor_id'],'include_audio_confirmed':True})
    assert blocked.status_code==422
    report['corrected_source_share_blocked']=True
    source=next(e for e in data()['source_evidence'] if e['evidence_id']=='ev_ae65b2950089456a')
    if 'privacy_letter' not in report:
        row=call('POST',root+'/narrative/records',json=dict(kind='letter',title='给未来自己的话',text='我不愿意现在讲清争执的来龙去脉',evidence_ids=[source['evidence_id']],facets=['EXPRESSION'],recipient_label='自己'))
        report['privacy_letter']=call('POST',root+'/narrative/records/'+row['id']+'/confirm',json={'revision':row['revision']});save(path,report)
    record_ids={report['privacy_letter']['id']}
    assert not record_ids & {r['id'] for r in data(reader)['records']}
    for index in range(len(report['cycles']),3):
        grant=call('POST',root+'/grants',json={'episode_id':source['episode_id'],'reader_actor_id':reader['actor_id'],'include_audio_confirmed':True,'cloud_processing_allowed':False})
        try:
            assert record_ids <= {r['id'] for r in data(reader)['records']}
            with httpx.stream('GET',endpoint+root+'/stories/'+source['episode_id']+'/audio',headers={'Authorization':'Bearer '+reader['actor_token']},trust_env=False) as r:
                assert r.status_code==200
                assert len(next(r.iter_bytes(chunk_size=4096)))>0
        finally:call('DELETE',root+'/grants/'+grant['grant_id'])
        assert not record_ids & {r['id'] for r in data(reader)['records']}
        r=httpx.get(endpoint+root+'/stories/'+source['episode_id']+'/audio',headers={'Authorization':'Bearer '+reader['actor_token']},trust_env=False)
        assert r.status_code==404
        report['cycles'].append({'cycle':index+1,'shared_view':True,'audio_bytes':True,'revoked_view':True,'revoked_audio_status':r.status_code});save(path,report)
    report['style_restored_disabled']=not data()['style']['enabled'];save(path,report)
    print('Letters and three share/revoke cycles checked; inspect real expression outcome separately.')

if __name__=='__main__':main()

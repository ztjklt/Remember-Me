"""User-authorized fictional technical expansion; not human listening acceptance.
Resumable API operations, chronological within each subject. No gold/author text
is sent to STT, extractor, profiles or QA. See nightly report for every failure.
"""
import json,time,hashlib
from pathlib import Path
import httpx
from product_loop import AUTH,MAPPING,call
from speech_pipeline import CORPUS,OUT,save,sha
from nightly_rules import choose_audio,record_failure,check_correction
STATE=OUT/'nightly-state.json'
TARGETS={
 'bus_driver':{'correction':'mi_6485abec24644ae4','supplement':'mi_c72eeeaa988e46f6'},
 'firefighter':{'correction':'mi_c7fd4156b3d94819','supplement':'mi_aa55dac56c674c39'},
 'life_review':{'correction':'mi_18b6fdec37f14b7b','supplement':'mi_e60aaf4dca964cde'},
}
QUESTIONS={'bus_driver':'为什么总说平安回家比多跑一趟重要？','firefighter':'为什么留下那本灰色本子？','life_review':'为什么一直留着那本边角磨坏的工作本？'}

def next_episode(person,mapping,completed):
    for ep in person['episodes']:
        if ep['id'] not in completed:
            return ep
    return None

def main():
    manifest=json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
    auth=json.loads(AUTH.read_text(encoding='utf-8'))
    mapping=json.loads(MAPPING.read_text(encoding='utf-8'))
    state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'episodes':{},'events':[],'human_listening_pass':False,'authorization':'2026-10-08 user requests all ten recordings per person; imperfect ASR technical confirmation allowed'}
    def event(label,**data):
        state['events'].append({'at':time.time(),'label':label,**data});save(STATE,state)
        print(label,flush=True)
    def api(label,method,path,identity,**kw):
        start=time.monotonic()
        try:r=call(method,path,identity,**kw)
        except Exception as exc:event(label+' FAILED',error=str(exc));raise
        event(label,elapsed_seconds=round(time.monotonic()-start,3),result=r);return r
    for person in manifest['people']:
        ep=person['episodes'][0];owner=auth[person['id']]['owner']
        status=call('GET','/api/v1/episodes/'+mapping[ep['id']]['episode_id'],owner)
        if status['status']=='ready':state['episodes'].setdefault(ep['id'],{'complete':True,'previous_sample':True})
    save(STATE,state)
    deadline=time.monotonic()+6*3600
    while time.monotonic()<deadline:
        progressed=False
        for person in manifest['people']:
            pid=person['id'];pair=auth[pid];owner=pair['owner'];root='/api/v1/workbench/subjects/'+owner['subject_id']
            done={k for k,v in state['episodes'].items() if v.get('complete')}
            ep=next_episode(person,mapping,done)
            if not ep:continue
            name=ep['id'];folder=OUT/pid;record=folder/(name+'.json');wav=folder/(name+'.wav')
            row=state['episodes'].setdefault(name,{})
            if row.get('blocked') or row.get('retry_after',0)>time.time():continue
            if not record.exists() or not wav.exists():continue
            progressed=True
            try:
                meta=json.loads(record.read_text(encoding='utf-8'))
                wav=choose_audio(folder,name,meta)
                assert sha(wav.read_bytes())==meta['audio_sha256'],'audio hash mismatch'
                if meta['duration_seconds']<180 and not meta.get('segmented_repair'):
                    if not row.get('awaiting_audio_repair'):
                        row['awaiting_audio_repair']=True;event('AWAITING short-audio repair '+name)
                    time.sleep(2)
                    continue
                if name not in mapping:
                    res=api('upload '+name,'POST','/api/v1/episodes',owner,data={
                        'subject_id':owner['subject_id'],'recording_consent_id':owner['consent_id'],
                        'source':'IMPORT','audio_ref':wav.name,'recorded_at':ep['simulated_recorded_at'],
                        'duration_ms':round(meta['duration_seconds']*1000),'idempotency_key':'monthly:'+meta['audio_sha256'],
                        'metadata':json.dumps({'evaluation_id':name,'synthetic':True,'generated_at':meta['at'],'tts_model':meta['response_model'],'technical_quality_pending':True})},
                        files={'file':(wav.name,wav.read_bytes(),'audio/wav')})
                    mapping[name]={'episode_id':res['episode_id'],'person':pid,'audio_sha256':meta['audio_sha256']};save(MAPPING,mapping)
                eid=mapping[name]['episode_id'];row['episode_id']=eid
                number=int(name[-2:])
                if number in (4,6) and not row.get('revision_id'):
                    kind='correction' if number==4 else 'supplement'
                    rev=api('associate '+kind+' '+name,'POST',root+'/revisions',owner,json={'episode_id':eid,'target_memory_id':TARGETS[pid][kind],'kind':kind})
                    row['revision_id']=rev['revision_id'];save(STATE,state)
                # Episode05 introduces both old and new locations itself. No invented
                # target ID: preserve that timeline in content, do not link unrelated memory.
                if number==5:row['temporal_update']='Narrative supplies past/current locations; no matching prior location memory has been established'
                if number==9 and not row.get('request_id'):
                    req=api('reader asks '+name,'POST',root+'/requests',pair['reader'],json={'text':QUESTIONS[pid]})
                    row['request_id']=req['request_id'];save(STATE,state)
                end=time.monotonic()+2700
                while time.monotonic()<end:
                    review=call('GET','/api/v1/episodes/'+eid+'/transcript-review',owner)
                    status=call('GET','/api/v1/episodes/'+eid,owner)
                    if review['state']=='reviewing':
                        save(folder/(name+'.product-asr.json'),review)
                        (folder/(name+'.approved-asr.txt')).write_text(review['transcript'],encoding='utf-8')
                        save(folder/(name+'.reviewed.json'),{'basis':'user-authorized imperfect fictional ASR technical confirmation','human_listening':False,'text':review['transcript'],'raw_asr_kept':True})
                        api('confirm technical ASR '+name,'PATCH','/api/v1/episodes/'+eid+'/transcript-review',owner,json={'transcript':review['transcript']})
                    if status['status']=='ready':break
                    if status['status']=='failed':
                        count=row.get('explicit_retries',0)
                        if count>=2:raise RuntimeError('product failed after bounded explicit retries: '+str(status.get('error_code')))
                        row['explicit_retries']=count+1;save(STATE,state)
                        api('retry failed product '+name,'POST','/api/v1/episodes/'+eid+'/retry',owner)
                    time.sleep(2)
                else:raise RuntimeError('bounded product wait expired')
                stories=call('GET',root+'/stories',owner)['items'];story=next(s for s in stories if s['episode_id']==eid)
                if row.get('revision_id') and not row.get('revision_confirmed'):
                    if not story['memories']:raise RuntimeError('no extracted memory for revision; original audio and ASR retained')
                    if number==4:
                        old=next(m for st in stories for m in st['memories'] if m['memory_item_id']==TARGETS[pid]['correction'])
                        row['correction_gate']=check_correction(pid,old,story)
                        save(STATE,state)
                    api('confirm revision '+name,'POST',root+'/revisions/'+row['revision_id']+'/confirm',owner)
                    row['revision_confirmed']=True
                row['memory_count']=len(story['memories'])
                row['evidence_exact']=all(e['excerpt'] in story['transcript'] for m in story['memories'] for e in m['evidence'])
                assert row['evidence_exact'],'evidence is not in confirmed text'
                if number in (2,3,5,6,8,9) and not row.get('grant_id'):
                    g=api('share full selected story '+name,'POST',root+'/grants',owner,json={'episode_id':eid,'reader_actor_id':pair['reader']['actor_id'],'include_audio_confirmed':True,'cloud_processing_allowed':True})
                    row['grant_id']=g['grant_id']
                if number==10:
                    req=state['episodes'][pid+'-09']['request_id']
                    api('link private response '+name,'PATCH',root+'/requests/'+req,owner,json={'status':'answered','answer_episode_id':eid})
                    seen=call('GET',root+'/requests',pair['reader'])['items']
                    assert next(r for r in seen if r['request_id']==req)['answer_episode_id'] is None
                row['complete']=True;row['duration_pass']=meta['duration_pass'];save(STATE,state)
                event('COMPLETE '+name,memories=row['memory_count'],evidence_exact=row['evidence_exact'])
            except Exception as exc:
                record_failure(row,exc,time.time());save(STATE,state);event(('BLOCKED ' if row.get('blocked') else 'RETRY LATER ')+name,error=str(exc))
        if all(state['episodes'].get(ep['id'],{}).get('complete') for p in manifest['people'] for ep in p['episodes']):
            event('ALL30 technical ingestion complete');return
        if not progressed:time.sleep(5)
    event('Nightly time budget reached; resumable state retained')

if __name__=='__main__':main()

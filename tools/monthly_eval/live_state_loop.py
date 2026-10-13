"""Actual synthetic-audio -> local STT -> Weixin -> role/revision/calibration loop.

User authorized imperfect fictional ASR on 2026-10-07. Never marks listening QA
passed. Separate subjects and checkpoints keep the monthly benchmark untouched.
"""
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import httpx
from dotenv import dotenv_values
from speech_pipeline import REPO, OUT, save, synthesize

ROOT = OUT / 'state-loop'
STATE = ROOT / 'state.json'
IDENTITIES = ROOT / 'identities.json'
REPORT = ROOT / 'report.json'
BASE = 'http://127.0.0.1:8877'


def bootstrap():
    if IDENTITIES.exists(): return json.loads(IDENTITIES.read_text(encoding='utf-8'))
    backend = REPO / 'services/backend'
    previous = Path.cwd(); sys.path.insert(0, str(backend)); os.chdir(backend)
    try:
        from app.config import get_settings
        from app.db import Database
        from app.seed import seed_development_data
        with Database(get_settings().database_url).session() as session:
            result = {role:asdict(seed_development_data(session,subject_name='技术闭环·虚构许川·'+role,
                actor_name='闭环测试身份·'+role)) for role in ['owner','reader']}
        save(IDENTITIES, result); return result
    finally: os.chdir(previous)


class Loop:
    def __init__(self):
        self.auth=bootstrap();self.owner=self.auth['owner'];self.reader=self.auth['reader']
        self.subject=self.owner['subject_id'];self.root='/api/v1/workbench/subjects/'+self.subject
        self.subject_api='/api/v1/subjects/'+self.subject
        self.state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'episodes':{},'revisions':{}}
        self.report=json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {
            'benchmark':'fictional-state-loop-not-monthly','listening_quality_pass':False,'steps':[]}
        self.cloud=self.state.get('cloud')

    def call(self,label,method,path,role='owner',expected=(200,201,202),**kwargs):
        start=time.monotonic()
        r=httpx.request(method,BASE+path,headers={'Authorization':'Bearer '+self.auth[role]['actor_token']},
            trust_env=False,timeout=100,**kwargs)
        body=r.json() if 'json' in r.headers.get('content-type','') else {'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()}
        self.report['steps'].append({'label':label,'method':method,'path':path,'status':r.status_code,
            'elapsed_seconds':round(time.monotonic()-start,3),'result':body,'expected_status_pass':r.status_code in expected})
        save(REPORT,self.report);print(label,r.status_code,flush=True)
        if r.status_code not in expected:raise RuntimeError(label+': '+str(r.status_code))
        return body

    def checkpoint(self):save(STATE,self.state)

    def stories(self):return self.call('read persisted stories','GET',self.root+'/stories')['items']

    def upload(self,name,relation=None,metadata=None):
        path=ROOT/(name+'.wav');meta=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        if name not in self.state['episodes']:
            result=self.call('upload '+name,'POST','/api/v1/episodes',data={
                'subject_id':self.subject,'recording_consent_id':self.owner['consent_id'],
                'source':'IMPORT','audio_ref':path.name,'recorded_at':datetime.now(timezone.utc).isoformat(),
                'duration_ms':round(meta['duration_seconds']*1000),'idempotency_key':'state-loop:'+self.state.get('upload_version','v1')+':'+name+':'+meta['audio_sha256'],
                'metadata':json.dumps({'synthetic':True,'technical_test':True,**(metadata or {})})},
                files={'file':(path.name,path.read_bytes(),'audio/wav')})
            self.state['episodes'][name]=result['episode_id'];self.checkpoint()
        ep=self.state['episodes'][name]
        if relation and name not in self.state['revisions']:
            rev=self.call('propose '+name,'POST',self.root+'/revisions',json={'episode_id':ep,**relation})
            self.state['revisions'][name]=rev['revision_id'];self.checkpoint()
        for _ in range(150):
            r=httpx.get(BASE+'/api/v1/episodes/'+ep+'/transcript-review',trust_env=False,
                headers={'Authorization':'Bearer '+self.owner['actor_token']}).json()
            if r['state']=='reviewing':
                (ROOT/(name+'.approved-asr.txt')).write_text(r['transcript'],encoding='utf-8')
                save(ROOT/(name+'.review.json'),{'state':r,'basis':'user-authorized imperfect fictional ASR for technical test','human_listening':False})
                self.call('explicit test transcript confirmation '+name,'PATCH','/api/v1/episodes/'+ep+'/transcript-review',json={'transcript':r['transcript']})
                break
            if r['state']=='confirmed':break
            status=httpx.get(BASE+'/api/v1/episodes/'+ep,trust_env=False,headers={'Authorization':'Bearer '+self.owner['actor_token']}).json()['status']
            if status=='failed':raise RuntimeError('processing failed '+name)
            if status=='ready':break
            time.sleep(1)
        for _ in range(150):
            r=httpx.get(BASE+'/api/v1/episodes/'+ep,trust_env=False,headers={'Authorization':'Bearer '+self.owner['actor_token']}).json()
            if r['status']=='ready':break
            if r['status']=='failed':raise RuntimeError('model processing failed '+name)
            time.sleep(1)
        else:raise RuntimeError('ready timeout '+name)
        if relation:self.call('confirm '+name,'POST',self.root+'/revisions/'+self.state['revisions'][name]+'/confirm')
        return next(s for s in self.stories() if s['episode_id']==ep)

    def ask(self,question,role='owner',grant=None):
        return self.call('QA '+question,'POST',self.subject_api+'/twin/answers',role,
            json={'question':question,'cloud_consent_id':grant or self.cloud})

    def grant(self,ep):
        return self.call('share selected story','POST',self.root+'/grants',json={
            'episode_id':ep,'reader_actor_id':self.reader['actor_id'],
            'include_audio_confirmed':True,'cloud_processing_allowed':True})['grant_id']


def main():
    loop=Loop()
    if loop.report.get('api_state_loop_passed'):
        print('Existing technical loop is complete; report retained. Use a separate runtime directory for a fresh destructive replay.')
        return
    if not loop.cloud:
        loop.cloud=loop.call('owner cloud consent','POST','/api/v1/consents',json={
            'subject_id':loop.subject,'scope':'CLOUD_TWIN','evidence_ref':'user-authorized-fictional-state-loop'})['consent_id']
        loop.state['cloud']=loop.cloud;loop.checkpoint()
    if loop.state.get('phase') != 'after-change':
        initial=loop.upload('initial');private=loop.upload('private')
        memories=initial['memories']
        year=next(m for m in memories if '苏州' in m['content'] and any(v in m['content'] for v in ['2010','二零一零','二〇一〇']))
        tea=next(m for m in memories if '茶' in m['content'])
        loop.state.update(year_memory=year['memory_item_id'],tea_memory=tea['memory_item_id']);loop.checkpoint()
        grant=loop.grant(initial['episode_id'])
        loop.state['initial_grant']=grant;loop.checkpoint()
        visible=loop.call('reader sees only shared initial','GET',loop.root+'/stories','reader')['items']
        assert all(s['episode_id']!=private['episode_id'] for s in visible)
        result=loop.ask('那个私密蓝色木盒里纸条上写了什么？','reader',grant)
        assert result['response_type']=='UNKNOWN'
        loop.call('private audio denied','GET',loop.root+'/stories/'+private['episode_id']+'/audio','reader',expected=(404,))
        supplement=loop.upload('supplement',{'target_memory_id':tea['memory_item_id'],'kind':'supplement'})
        sg=loop.grant(supplement['episode_id']);loop.state['supplement_grant']=sg;loop.checkpoint()
        result=loop.ask('方宁是他的亲属还是邻居？')
        assert result['response_type']!='UNKNOWN' and '邻居' in result['answer']
        old_answer=loop.ask('他先前把搬到苏州的年份记作哪一年？')
        correction=loop.upload('correction',{'target_memory_id':year['memory_item_id'],'kind':'correction'})
        corrected=loop.ask('经纠正后，他哪一年搬到苏州？')
        assert any(y in corrected['answer'] for y in ['2012','二零一二','二〇一二'])
        stale=loop.call('old answer invalidated','GET',loop.subject_api+'/twin/answers/'+old_answer['answer_id'])
        assert stale['stale']
        result=loop.ask('经纠正后，他哪一年搬到苏州？','reader',sg)
        assert result['response_type']=='UNKNOWN'
        loop.call('corrected original reader audio unavailable','GET',loop.root+'/stories/'+initial['episode_id']+'/audio','reader',expected=(404,))
        newyear=next(m for m in correction['memories'] if '苏州' in m['content'] and any(v in m['content'] for v in ['2012','二零一二','二〇一二']))
        change=loop.upload('change',{'target_memory_id':newyear['memory_item_id'],'kind':'change','time_text':'2019年'})
        now=loop.ask('他后来搬家后现在住在哪里？')
        assert '杭州' in now['answer']
        past=loop.ask('他在搬去杭州以前有没有在苏州生活过？')
        if past['response_type']=='UNKNOWN':
            loop.report.setdefault('quality_findings',[]).append('Missed known historical Suzhou residence: UNKNOWN despite effective evidence; deferred answer-recall issue, not a quality pass.')
        loop.state['phase']='after-change';loop.checkpoint()
    private=next(x for x in loop.stories() if x['episode_id']==loop.state['episodes']['private'])
    tea={'memory_item_id':loop.state['tea_memory']}
    request=loop.call('reader question request','POST',loop.root+'/requests','reader',json={'text':'为什么喜欢不加糖的茶？'})
    response=loop.upload('answer')
    loop.call('associate actual answer','PATCH',loop.root+'/requests/'+request['request_id'],json={'status':'answered','answer_episode_id':response['episode_id']})
    requests=loop.call('answer remains private','GET',loop.root+'/requests','reader')['items']
    assert next(r for r in requests if r['request_id']==request['request_id'])['answer_episode_id'] is None
    ag=loop.grant(response['episode_id'])
    answer=loop.ask('为什么喜欢不加糖的茶？','reader',ag)
    assert answer['response_type']!='UNKNOWN' and ('味' in answer['answer'])
    # Lock before generating, uploading, transcribing, or sending the answer.
    if 'calibration_id' not in loop.state:
        twin=loop.ask('如果收入和家人安全冲突，他会怎样选择？')
        cal=loop.call('lock Twin before response audio','POST',loop.subject_api+'/calibrations',json={'twin_answer_id':twin['answer_id'],'cloud_consent_id':loop.cloud})
        loop.state['calibration_id']=cal['calibration_id'];loop.checkpoint()
    cal_id=loop.state['calibration_id']
    if (ROOT/'calibration.wav').exists():
        prior=json.loads((ROOT/'calibration.json').read_text(encoding='utf-8'))
        if prior.get('locked_calibration_id') != cal_id:
            stamp=str(time.time_ns())
            (ROOT/'calibration.wav').rename(ROOT/('calibration-unused-before-lock-'+stamp+'.wav'))
            (ROOT/'calibration.json').rename(ROOT/('calibration-unused-before-lock-'+stamp+'.json'))
    if not (ROOT/'calibration.wav').exists():
        corpus=json.loads((REPO/'evaluations/agent-loop-smoke-v1/scripts.json').read_text(encoding='utf-8'))
        text=next(c['text'] for c in corpus['clips'] if c['id']=='calibration')
        voice='data:audio/wav;base64,'+base64.b64encode((OUT/'bus_driver/synthetic-voice.wav').read_bytes()).decode()
        data,meta=synthesize(dotenv_values(REPO/'services/backend/.env.speech-eval')['MIMO_API_KEY'],
            'mimo-v2.5-tts-voiceclone',text,'虚构男性声音，清晰普通话，完整朗读。',voice)
        (ROOT/'calibration.wav').write_bytes(data);save(ROOT/'calibration.json',meta|{'locked_calibration_id':cal_id})
    loop.upload('calibration',metadata={'calibration_id':cal_id})
    cal=loop.call('real model calibration','POST',loop.subject_api+'/calibrations/'+cal_id+'/complete',json={'cloud_consent_id':loop.cloud})
    assert cal['status']=='complete' and cal['comparison_model_version']=='Deepseek-v4-flash'
    loop.call('derived person views','GET',loop.root+'/portrait')
    questions=loop.call('guided questions','GET',loop.subject_api+'/questions')['items']
    if questions:
        loop.call('snooze one guided question','PATCH',loop.root+'/questions/'+questions[0]['question_id'],json={'status':'snoozed'})
        loop.call('resume guided question','PATCH',loop.root+'/questions/'+questions[0]['question_id'],json={'status':'pending'})
    # Three actual-model rounds. Each update invalidates stored answers and each
    # revoked grant blocks new requests and original-audio reads.
    for i in range(3):
        current=loop.ask('他平时喜欢喝怎样的茶？')
        loop.call('confirmed text revision round '+str(i+1),'PATCH',loop.subject_api+'/memories/'+tea['memory_item_id'],json={'content':'平时喜欢喝不加糖的茶，保留其他人的口味选择。'})
        old=loop.call('old answer stale round '+str(i+1),'GET',loop.subject_api+'/twin/answers/'+current['answer_id'])
        assert old['stale']
        new=loop.ask('他平时喜欢喝怎样的茶？');assert new['response_type']!='UNKNOWN'
        g=loop.grant(response['episode_id'])
        loop.ask('为什么喜欢不加糖的茶？','reader',g)
        loop.call('revoke round '+str(i+1),'DELETE',loop.root+'/grants/'+g)
        loop.call('old audio blocked round '+str(i+1),'GET',loop.root+'/stories/'+response['episode_id']+'/audio','reader',expected=(404,))
        loop.call('revoked grant QA blocked round '+str(i+1),'POST',loop.subject_api+'/twin/answers','reader',expected=(403,404),json={'question':'喜欢怎样的茶？','cloud_consent_id':g})
    # Delete a private test memory via the public route, never the database.
    deletion_story = private if private['memories'] else next(s for s in loop.stories()
        if s['episode_id']==loop.state['episodes']['calibration'])
    deleted=deletion_story['memories'][0]['memory_item_id']
    loop.call('delete private memory','DELETE',loop.subject_api+'/memories/'+deleted)
    items=loop.call('deleted memory removed from list','GET',loop.subject_api+'/memories')['items']
    assert all(m['memory_item_id']!=deleted for m in items)
    loop.report['api_state_loop_passed']=True;loop.report['asr_quality']='known defects deferred by user'
    save(REPORT,loop.report)
    print('Real state loop passed; not monthly/physical-device/listening acceptance.',flush=True)


if __name__=='__main__':main()

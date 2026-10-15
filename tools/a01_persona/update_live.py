"""Actual local owner-condition update. Every mutating phase is explicit.

No gold/source DOCX is loaded. A later synthetic recording is uploaded only after
an immutable calibration answer exists. ASR is technically confirmed unchanged;
it is not claimed to have been listened to or endorsed by an actual person.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from tools.a01_persona.live_acceptance import VAR, read, save, live_context

OUT=VAR/'persona-update-20261012'
STATE=OUT/'state.json'
QUESTION='家里的旧台灯坏了，如果按你现在留下的想法，你会怎样考虑修还是换？'
PARAPHRASE='同样是家里的旧灯出了问题，你觉得什么情况下可以自己看看，什么情况下应当先停下来？'


def now():return datetime.now(timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()


class Run:
    def __init__(self):
        self.data=read(STATE) if STATE.exists() else {
            'fictional':True,'scope':'local_only','events':[],
            'review_basis':'Actual ASR technically confirmed, no real-person endorsement or listening claim',
            'source_description':'Additional fictional validation material, not part of original user DOCX'}
    def flush(self):save(STATE,self.data)
    def call(self,client,method,path,*,expected=200,**kwargs):
        event={'at':now(),'method':method,'path':path,'status':'started'}
        if 'json' in kwargs:event['request']=kwargs['json']
        self.data['events'].append(event);self.flush();start=time.monotonic()
        try:
            response=client.request(method,path,**kwargs)
            event.update(http_status=response.status_code,response=response.json(),
                elapsed_seconds=round(time.monotonic()-start,3),status='delivered' if response.status_code==expected else 'failed')
        except Exception as exc:
            event.update(status='failed',error_type=type(exc).__name__);self.flush();raise RuntimeError('Request failed; inspect checkpoint') from None
        self.flush()
        if response.status_code!=expected:raise RuntimeError(f'HTTP {response.status_code}; inspect saved event, no automatic retry')
        return event['response']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['lock','ingest','compare','refresh','apply','after'])
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--candidate')
    parser.add_argument('--target',default='pc_b70242e6b72f670b38195c4065478a17c966982d')
    args=parser.parse_args();run=Run();base=read(VAR/'runtime/ingest.json');s=base['subject_id']
    work=f'/api/v1/workbench/subjects/{s}';api=f'/api/v1/subjects/{s}'
    with live_context(base) as clients:
        owner=clients['owner'];reader=clients['reader']
        if args.phase=='lock':
            if 'calibration' in run.data:print('Already locked; preserved.');return
            run.data['before_person']=run.call(owner,'GET',work+'/narrative');run.flush()
            if 'before_answer' not in run.data:
                run.data['before_answer']=run.call(owner,'POST',api+'/twin/answers',json={
                    'question':QUESTION,'mode':'persona','cloud_consent_id':base['CLOUD_TWIN']});run.flush()
            answer=run.data['before_answer']
            if answer['response_type']=='UNKNOWN':raise RuntimeError('No known answer to compare; do not fabricate baseline')
            run.data['calibration']=run.call(owner,'POST',api+'/calibrations',json={
                'twin_answer_id':answer['answer_id'],'cloud_consent_id':base['CLOUD_TWIN']})
            run.data['locked_at']=now();run.flush();print('Actual answer locked before new recording.')
        elif args.phase=='ingest':
            if 'calibration' not in run.data:raise RuntimeError('Lock first')
            if not args.audio or not args.audio.is_file():raise RuntimeError('Actual new WAV required')
            audio=args.audio.read_bytes();cal=run.data['calibration']['calibration_id']
            if 'episode' not in run.data:
                caps=run.call(owner,'GET','/api/v1/workbench/capabilities')
                run.data['audio']={'path':str(args.audio.resolve()),'sha256':sha(audio),'actual_upload_at':now()};run.flush()
                run.data['episode']=run.call(owner,'POST','/api/v1/episodes',expected=201,data={
                    'subject_id':s,'recording_consent_id':base['RECORDING'],'source':'IMPORT',
                    'recorded_at':now(),'audio_ref':'persona-condition-followup.wav',
                    'idempotency_key':'a01-persona-condition-20261012-v1',
                    'metadata':json.dumps({'calibration_id':cal,'cloud_asr_policy':caps['cloud_asr_policy'],
                        'fictional_sample':'A01-new-condition','audio_origin':'Xiaomi synthetic',
                        'review_basis':'technical confirmation, no human listening claim'})},
                    files={'file':('persona-condition-followup.wav',audio,'audio/wav')});run.flush()
            eid=run.data['episode']['episode_id'];deadline=time.monotonic()+360
            while time.monotonic()<deadline:
                status=run.call(owner,'GET',f'/api/v1/episodes/{eid}')
                review=run.call(owner,'GET',f'/api/v1/episodes/{eid}/transcript-review')
                if review['state']=='reviewing':
                    run.data['actual_asr']=review;run.data['confirmed_text']=review['transcript'];run.flush()
                    run.call(owner,'PATCH',f'/api/v1/episodes/{eid}/transcript-review',json={'transcript':review['transcript']})
                if status['status']=='ready':run.data['episode_ready']=status;run.flush();print('New actual ASR reviewed and extracted.');return
                if status['status']=='failed':raise RuntimeError('Recorded ingest failure; audio retained')
                time.sleep(3)
            raise RuntimeError('Ingest deadline; saved checkpoint retained')
        elif args.phase=='compare':
            if 'comparison' in run.data:return
            if 'episode_ready' not in run.data:raise RuntimeError('New recording not ready')
            before=run.call(owner,'GET',work+'/profile-candidates')
            run.data['comparison']=run.call(owner,'POST',api+'/calibrations/'+run.data['calibration']['calibration_id']+'/complete',
                json={'cloud_consent_id':base['CLOUD_TWIN']});run.flush()
            after=run.call(owner,'GET',work+'/profile-candidates')
            run.data['comparison_did_not_modify_profiles']=before['items']==after['items'];run.flush()
            if not run.data['comparison_did_not_modify_profiles']:raise RuntimeError('Unexpected automatic understanding mutation')
            print('Real comparison saved; did not modify profiles.')
        elif args.phase=='refresh':
            if 'profile_job' not in run.data:
                run.data['profile_job']=run.call(owner,'POST',work+'/profile-candidates/refresh',expected=202,
                    json={'cloud_consent_id':base['CLOUD_TWIN']});run.flush()
            deadline=time.monotonic()+600
            while time.monotonic()<deadline:
                rows=run.call(owner,'GET',work+'/profile-candidates');run.data['new_candidates']=rows;run.flush()
                job=next(j for j in rows['jobs'] if j['job_id']==run.data['profile_job']['job_id'])
                if job['status']=='complete':print('Candidates ready for explicit source review.');return
                if job['status']=='failed':raise RuntimeError('Profile generation failed; no auto-retry')
                time.sleep(4)
            raise RuntimeError('Profile deadline; pending checkpoint retained')
        elif args.phase=='apply':
            if not args.candidate:raise RuntimeError('Specify candidate only after reading current source and counterexamples')
            if 'update' not in run.data:
                run.data['update']=run.call(owner,'POST',work+'/profile-candidates/updates',expected=201,json={
                    'candidate_id':args.candidate,'target_candidate_id':args.target,'action':'CHANGE',
                    'reason':'本轮虚构补录明确补充维修的适用条件：普通小毛病先查原因，电线外露或焦味时先停下并找懂电工的人。',
                    'time_text':'这次补录中说明的现在'});run.flush()
            run.data['confirmed_update']=run.call(owner,'POST',work+'/profile-candidates/updates/'+run.data['update']['update_id']+'/confirm')
            run.data['after_person']=run.call(owner,'GET',work+'/narrative');run.flush();print('Explicit update confirmed, history retained.')
        elif args.phase=='after':
            if 'confirmed_update' not in run.data:raise RuntimeError('Confirm understanding first')
            # Reader sees the new recording only after this explicit grant.
            if 'new_grant' not in run.data:
                run.data['reader_before_share']=run.call(reader,'GET',work+'/narrative')
                run.data['new_grant']=run.call(owner,'POST',work+'/grants',expected=201,json={
                    'episode_id':run.data['episode']['episode_id'],'reader_actor_id':base['reader_actor_id'],
                    'include_audio_confirmed':True,'cloud_processing_allowed':True});run.flush()
            run.data['reader_after_share']=run.call(reader,'GET',work+'/narrative');run.flush()
            # Finish permission changes before creating current answers.
            for name,question in [('same',QUESTION),('paraphrase',PARAPHRASE)]:
                if name not in run.data:
                    run.data[name]=run.call(owner,'POST',api+'/twin/answers',json={
                        'question':question,'mode':'persona','cloud_consent_id':base['CLOUD_TWIN']});run.flush()
            print('Same/paraphrased answers and explicit new-recording sharing saved.')


if __name__=='__main__':main()

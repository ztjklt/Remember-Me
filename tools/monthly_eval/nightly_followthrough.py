"""Serial repair after TTS, then real profile/QA after chronological ingest.
Local supervisor checkpoints are evidence, not acceptance claims.
"""
import json,subprocess,sys,time
from pathlib import Path
from speech_pipeline import CORPUS,OUT,save
from product_loop import AUTH,MAPPING,call,check_qa_scope
from nightly_rules import qa_state,technical_phase
REPORT=OUT/'nightly-followthrough.json'

def main():
 manifest=json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
 state=json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'phase':'waiting_audio','repairs':{},'profiles':{},'qa':{},'manual_quality_review':'pending'}
 deadline=time.monotonic()+6*3600
 def checkpoint():save(REPORT,state)
 checkpoint()
 while time.monotonic()<deadline:
  if all((OUT/p['id']/(e['id']+'.json')).exists() for p in manifest['people'] for e in p['episodes']):break
  time.sleep(10)
 else:state['phase']='audio_wait_timeout';checkpoint();return
 state['phase']='repairing_short_audio';checkpoint()
 for p in manifest['people']:
  for ep in p['episodes'][1:]:
   meta=json.loads((OUT/p['id']/(ep['id']+'.json')).read_text(encoding='utf-8'))
   if meta['duration_seconds']<180 and not meta.get('segmented_repair'):
    r=subprocess.run([sys.executable,str(Path(__file__).with_name('repair_short_audio.py')),ep['id']],timeout=1500)
    state['repairs'][ep['id']]={'exit_code':r.returncode};checkpoint()
    if r.returncode:state['phase']='repair_failed';checkpoint();return
 state['phase']='waiting_product';checkpoint()
 while time.monotonic()<deadline:
  f=OUT/'nightly-state.json';ingest=json.loads(f.read_text(encoding='utf-8')) if f.exists() else {'episodes':{}}
  if all(ingest['episodes'].get(e['id'],{}).get('complete') for p in manifest['people'] for e in p['episodes']):break
  time.sleep(15)
 else:state['phase']='product_wait_timeout';checkpoint();return
 state['phase']='profiles';checkpoint();auth=json.loads(AUTH.read_text(encoding='utf-8'));mapping=json.loads(MAPPING.read_text(encoding='utf-8'))
 for person in manifest['people']:
  pid=person['id'];pair=auth[pid];owner=pair['owner'];subject=owner['subject_id'];root='/api/v1/workbench/subjects/'+subject
  cons=call('GET','/api/v1/consents?subject_id='+subject,owner);cloud=next(c['consent_id'] for c in cons if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
  profile=state['profiles'].setdefault(pid,{})
  while profile.get('attempts',0)<3 and profile.get('status')!='complete':
   if profile.get('status') not in ('queued','running'):
    profile['attempts']=profile.get('attempts',0)+1
    profile['submitted']=call('POST',root+'/profile-candidates/refresh',owner,json={'cloud_consent_id':cloud})
    profile['status']='queued';checkpoint()
   job_id=profile['submitted']['job_id']
   for _ in range(180):
    data=call('GET',root+'/profile-candidates',owner)
    job=next(j for j in data['jobs'] if j['job_id']==job_id)
    if job['status'] not in ('queued','running'):break
    time.sleep(1)
   profile['result']=data;profile['status']=job['status'];profile.setdefault('history',[]).append(job);checkpoint()
   if job['status'] in ('queued','running'):
    profile['wait_timed_out']=True;break
  gold=json.loads((CORPUS/'gold'/(pid+'.json')).read_text(encoding='utf-8'))
  grants=call('GET',root+'/grants',pair['reader'])['items'];reader_cloud=next(g['grant_id'] for g in grants if g['cloud_processing_allowed'])
  try:check_qa_scope(pid,gold['qa_protocol'],mapping,grants,call('GET',root+'/stories',pair['reader'])['items'],call('GET',root+'/revisions',owner)['items'])
  except Exception as e:
   item=qa_state(state,pid);item.setdefault('precondition_history',[]).append(str(e));item['precondition_error']=str(e);checkpoint();continue
  result=qa_state(state,pid);result.pop('precondition_error',None)
  for check in gold['qa']:
   row=next((r for r in result['checks'] if r['id']==check['id']),None)
   if row is None:
    row={'id':check['id'],'role':check['role'],'question':check['question'],'factual_accuracy':'pending_manual_review','source_support':'pending_manual_review','attempts':0};result['checks'].append(row)
   while 'result' not in row and row.get('attempts',0)<3:
    row['attempts']=row.get('attempts',0)+1;checkpoint()
    try:
     row['result']=call('POST','/api/v1/subjects/'+subject+'/twin/answers',pair[check['role']],json={'question':check['question'],'cloud_consent_id':cloud if check['role']=='owner' else reader_cloud});row.pop('error',None)
    except Exception as e:
     row['error']=str(e);row.setdefault('failure_history',[]).append(str(e))
    checkpoint()
    if row.get('error'):time.sleep(2**row['attempts'])
   print(check['id'],'recorded; quality review pending',flush=True)
 state['phase']=technical_phase(state);checkpoint()
 print('Nightly processing finished; real outputs require manual factual review.',flush=True)

if __name__=='__main__':main()

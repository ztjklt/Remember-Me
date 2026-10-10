"""Create/reject one explicitly labeled synthetic technical UI observation via API.

No new LLM claims and no change to audio/ASR/gold. Run only after this person's QA.
"""
import argparse,json,subprocess
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'services/backend/var/round-two'
ADB=Path('D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe')

def main():
    args=argparse.ArgumentParser();args.add_argument('action',choices=['prepare','restore']);args=args.parse_args()
    owner=json.loads((ROOT/'services/backend/var/monthly-eval/identities.json').read_text(encoding='utf8'))['bus_driver']['owner']
    url='http://127.0.0.1:8890';root='/api/v1/workbench/subjects/'+owner['subject_id']+'/narrative'
    def call(method,path,**kwargs):
        r=httpx.request(method,url+path,headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,timeout=30,**kwargs)
        r.raise_for_status();return r.json()
    log=OUT/'mobile-link-check.json'
    if args.action=='restore':
        record=json.loads(log.read_text(encoding='utf8'))
        if not record.get('restored'):
            value=call('POST',root+'/records/'+record['record_id']+'/reject',json={'revision':record['revision']})
            record.update(restored=True,response_status=value['status']);log.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
        subprocess.run([str(ADB),'-s','emulator-5554','shell','run-as','me.remember.app','rm','-f','files/narrative-test.json'],check=True)
        print('Technical observation withdrawn; source retained');return
    if log.exists():raise SystemExit('Existing technical observation retained; do not create duplicates')
    data=call('GET',root);story=next(r for r in data['records'] if r['kind']=='story' and r['status']=='confirmed')
    # Exact current source content, explicitly scoped to one telling, not a trait.
    source=story['evidence'][0]
    created=call('POST',root+'/records',json={'kind':'observation','title':'界面技术核对：一段工作往事',
        'text':'仅本次讲述的原文内容：'+source['excerpt'],'evidence_ids':[source['evidence_id']],
        'facets':['VALUES'],'same_event':False})
    checked=call('POST',root+'/records/'+created['id']+'/confirm',json={'revision':created['revision']})
    log.write_text(json.dumps({'record_id':created['id'],'revision':checked['revision'],
        'story_id':story['id'],'story_title':story['title'],'technical_review_only':True,'restored':False},ensure_ascii=False,indent=2),encoding='utf8')
    config={'url':url,'actor_token':owner['actor_token'],'story_title':story['title'],'linked_story_title':story['title']}
    # stdin only; credential does not enter argv, stdout, screenshots or reports.
    proc=subprocess.run([str(ADB),'-s','emulator-5554','shell','run-as','me.remember.app','sh','-c','"cat > files/narrative-test.json"'],
        input=json.dumps(config,ensure_ascii=False).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if proc.returncode:raise SystemExit('Could not save opt-in emulator test configuration')
    print('Synthetic UI link ready:',story['title'])

if __name__=='__main__':main()

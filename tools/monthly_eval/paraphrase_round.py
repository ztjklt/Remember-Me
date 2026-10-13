"""Independent reworded questions; no expected answers in requests."""
import json
from datetime import datetime,timezone
from speech_pipeline import REPO, OUT, save
from product_loop import call
from cloud_followthrough import Steps

def main():
    run=OUT/'cloud-asr-runs/relay-compact'
    pairs=json.loads((run/'identities.json').read_text('utf8'))
    cases=json.loads((REPO/'evaluations/monthly-integration-v1/paraphrases-v1.json').read_text('utf8'))
    steps=Steps(OUT/'qa-localagent-v7-paraphrases.json')
    for case in cases:
        pair=pairs[case['person']];subject=pair['owner']['subject_id'];identity=pair[case['role']]
        if case['role']=='owner':
            rows=call('GET','/api/v1/consents?subject_id='+subject,identity)
            cloud=next(r['consent_id'] for r in rows if r['scope']=='CLOUD_TWIN' and r['status']=='granted')
        else:
            rows=call('GET','/api/v1/workbench/subjects/'+subject+'/grants',identity)['items']
            cloud=next(r['grant_id'] for r in rows if r['cloud_processing_allowed'] and not r.get('revoked_at'))
        try:
            steps.once(case['id'],lambda:call('POST','/api/v1/subjects/'+subject+'/twin/answers',identity,
                json={'question':case['question'],'cloud_consent_id':cloud}))
            print(case['id'],'saved',flush=True)
        except Exception as exc: print(case['id'],type(exc).__name__,flush=True)

if __name__=='__main__':main()

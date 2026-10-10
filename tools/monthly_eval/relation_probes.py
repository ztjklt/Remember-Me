"""Small real-model text probes, separate from audio/product acceptance."""
import json
from pathlib import Path
import httpx
from speech_pipeline import OUT,save
from cloud_followthrough import Steps


def main():
    steps=Steps(OUT/'relation-text-probes-v1.json')
    old='我平时喝茶不加糖。'
    cases=[('ADD','周末我喜欢在院子里照料花。','喜欢在周末照料花'),
           ('CONFLICT','我一直喝茶都加糖。','一直喝茶都加糖'),
           ('CHANGE','去年以后我的口味变了，现在喝茶会加糖。','去年以后改为喝加糖的茶')]
    for name,text,statement in cases:
        payload={'materials':[{'evidence_id':'new-source','episode_id':'new-recording','excerpt':text},
            {'evidence_id':'old-source','episode_id':'old-recording','excerpt':old}],
            'candidates':[{'candidate_id':'new-observation','domain':'PREFERENCES','kind':'habit','statement':statement,
                'context':'讲述者描述的日常偏好','evidence_ids':['new-source'],'counter_evidence_ids':[]}],
            'targets':[{'candidate_id':'old-understanding','domain':'PREFERENCES','kind':'habit','statement':'平时喝茶不加糖',
                'context':'讲述者描述的日常偏好','evidence_ids':['old-source'],'counter_evidence_ids':[]}]}
        def request():
            r=httpx.post('http://127.0.0.1:8879/profile-relations',json=payload,trust_env=False,timeout=60)
            if r.status_code!=200:raise RuntimeError('HTTP '+str(r.status_code))
            return {'input':payload,'actual':r.json(),'audio_test':False,'expected_action_offline':name}
        result=steps.once(name,request)
        print(name,'actual actions',[r['action'] for r in result['actual']['relations']],flush=True)

if __name__=='__main__':main()

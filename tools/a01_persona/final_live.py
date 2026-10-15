"""Freeze final current answers/audio after source mutations, using real APIs only."""
import argparse
from tools.a01_persona.live_acceptance import VAR,read,save,live_context,answer_request
from tools.a01_persona.voice_companion_live import Checkpoint,api

CASES=[
    {'id':'owner','role':'owner','mode':'persona',
     'question':'有人劝你别查原因，东西坏了就换。按你留下的想法，你会怎么回应？如果已经闻到焦味呢？'},
    {'id':'reader','role':'reader','mode':'persona',
     'question':'如果家人问你，为什么和孩子说话小心、与老杜却会互相损两句，你会怎么解释？'},
    {'id':'unrelated','role':'owner','mode':'evidence',
     'question':'你与周桂芳是哪一年认识、哪一年结婚的？具体是星期几？'},
]

def main():
    p=argparse.ArgumentParser();p.add_argument('--live-ready',action='store_true');args=p.parse_args()
    if not args.live_ready:raise SystemExit('Explicit local live run required')
    s=read(VAR/'runtime/ingest.json');out=VAR/'persona-final-current-20261012'
    plan={'subject_id':s['subject_id'],'cases':CASES,'basis':'actual saved ASR, reviewed contextual understandings',
          'review':'fictional only; no listening or human endorsement claim'}
    cp=Checkpoint(out/'run.json',plan);save(out/'plan.json',plan)
    root=f"/api/v1/subjects/{s['subject_id']}"
    with live_context(s) as clients:
        for role in ['owner','reader']:
            api(cp,clients,role+'.person',role,'GET',f"/api/v1/workbench/subjects/{s['subject_id']}/narrative")
        for case in CASES:
            role=case['role'];name=case['id']
            answer=api(cp,clients,name+'.answer',role,'POST',root+'/twin/answers',answer_request(case,s))['body']
            if name=='unrelated':continue
            if answer['response_type']=='UNKNOWN':raise RuntimeError('No known answer; do not create a voice success')
            speech=api(cp,clients,name+'.speech',role,'POST',root+'/twin/answers/'+answer['answer_id']+'/speech',{})['body']
            asset=root+'/voice/assets/'+speech['asset_id']+'/audio'
            api(cp,clients,name+'.audio',role,'GET',asset,audio_path=out/(name+'.wav'))
            other='reader' if role=='owner' else 'owner'
            api(cp,clients,name+'.other_actor',other,'GET',asset,expected=(404,))
        cp.data['result']='delivered; factual/semantic and listening review separate';cp.flush()
    print('Current owner/reader answers and real Xiaomi audio saved; unrelated fact query retained.')

if __name__=='__main__':main()

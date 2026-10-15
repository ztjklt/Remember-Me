"""Fixed approved seven-task v5/v16 comparison. Never edits ASR or baseline."""
import json
import os
from pathlib import Path
from dotenv import dotenv_values
from tools.a01_eval.prepare import ROOT, DATA, save, digest
from tools.a01_eval import run_baseline as baseline
from app.profile_proposals import PROMPT_VERSION
from app.quoted_twin import VERSION

OUT=ROOT/'services/backend/var/a01-20261012/evaluation/asr-v1-model-run'
ASR=ROOT/'services/backend/var/a01-20261012/evaluation/asr-paraformer-v1'

def main():
    OUT.mkdir(parents=True,exist_ok=True);baseline.OUT=OUT
    if PROMPT_VERSION!='profile-proposals-evidence-v5' or VERSION!='twin-quotes-v16':
        raise RuntimeError('Approved prompt versions changed')
    scripts=json.loads((DATA/'input/episodes.json').read_text(encoding='utf-8'))
    transcripts=[]
    for episode in scripts:
        raw=json.loads((ASR/(episode['id']+'.raw-asr.json')).read_text(encoding='utf-8'))
        if digest(raw['text'].encode())!=raw['transcript_sha256']:raise RuntimeError('Immutable raw ASR hash changed')
        transcripts.append({'id':episode['id'],'text':raw['text'],'sha256':raw['transcript_sha256'],
            'input_type':'unreviewed_real_ASR_from_fictional_synthetic_audio'})
    env={**dotenv_values('D:/codex_work/remember-me-agent-loop/services/ai-core/.env'),**os.environ}
    key=env.get('WEIXIN_CHAT_API_KEY','')
    if not key:raise SystemExit('No Weixin key; no provider call')
    fixed={'task_count':7,'qa_ids':['Q04','Q06','N01'],'profile_prompt':PROMPT_VERSION,
        'twin_prompt':VERSION,'extra_tasks_authorized':False,'reference_files_opened':False,
        'ASR_transcripts_corrected':False,'baseline_overwritten':False,
        'input_hashes':{'ASR':[{k:r[k] for k in ['id','sha256']} for r in transcripts],
            'script':[{k:r[k] for k in ['id','sha256']} for r in scripts]},
        'source_attribution_note':'SUBJECT denotes the fictional spoken speaker only. Raw ASR was not manually reviewed and these results are isolated evaluation, not confirmed product memories.',
        'source_code_sha256':{p:digest((ROOT/p).read_bytes()) for p in ['services/ai-core/app/profile_proposals.py','services/ai-core/app/quoted_twin.py']}}
    lock=OUT/'locked-plan.json'
    if lock.exists():
        if json.loads(lock.read_text(encoding='utf-8'))!=fixed:
            raise RuntimeError('Locked seven-task run differs; preserve and review, no model call')
    else:save(lock,fixed)
    chat=baseline.Chat(api_key=key)
    chat.stage='asr-profile-v5';chat.serial=0
    materials=[{'evidence_id':e['id']+'-asr','episode_id':e['id'],'excerpt':e['text']} for e in transcripts]
    baseline.checkpoint_task(chat.stage,lambda:baseline.ProfileProposalProvider(chat).propose(
        baseline.ProfileProposalInput(materials=materials)).model_dump(mode='json'))
    questions={q['id']:q['question'] for q in json.loads((DATA/'input/questions.json').read_text(encoding='utf-8'))}
    for source,episodes,suffix in [('asr',transcripts,'-asr'),('script',scripts,'-script')]:
        for id in fixed['qa_ids']:
            chat.stage=source+'-qa-'+id;chat.serial=0
            baseline.checkpoint_task(chat.stage,lambda id=id,episodes=episodes,suffix=suffix:
                baseline.qa(chat,questions[id],episodes,evidence_suffix=suffix))
    chat.close()

if __name__=='__main__':main()

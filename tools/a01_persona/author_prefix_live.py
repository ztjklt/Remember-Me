"""Two final v8 requests after the author-prefix code fix; no historical overwrite."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.a01_persona.live_acceptance import VAR,read,save,live_context,run_lock
from tools.a01_persona.voice_companion_live import Checkpoint,api,assert_withdrawn_answer

OUT=VAR/'twin-alignment-v8-final-20261012'


def main(run=False):
    state=read(VAR/'runtime/ingest.json')
    asr=read(VAR/'twin-alignment-v7-targeted-20261012/run.json')['operations']['audio.asr']['response']['body']
    plan={'schema':'v8-author-prefix-bounded','subject_id':state['subject_id'],'fictional':True,
        'source':'text copy of existing actual ASR for author-prefix regression; not new recording or new ASR',
        'cases':[{'id':'C01','role':'reader','question':'亲友这次署名补记的原话是什么？请区分这是谁的记录。','retrieval_mode':'full'},
                 {'id':'P01','role':'owner','question':'家里的旧台灯坏了，还有焦味，孩子也在旁边。如果参考你留下的做事方法，你会先怎样考虑？','retrieval_mode':'local'}],
        'max_question_requests':2,'retry_policy':'no best-of; network retry only within existing AI budget'}
    if (OUT/'plan.json').exists() and read(OUT/'plan.json')!=plan:raise ValueError('Frozen plan changed')
    save(OUT/'plan.json',plan)
    if not run:print('Frozen final two-request plan');return
    cp=Checkpoint(OUT/'run.json',plan)
    with run_lock(OUT/'run.lock'),live_context(state) as clients:
        root='/api/v1/subjects/'+state['subject_id'];comp='/api/v1/workbench/subjects/'+state['subject_id']+'/companion'
        def request(name,role,method,path,body=None,**kw):return api(cp,clients,name,role,method,path,body,**kw)
        def body(*a,**kw):return request(*a,**kw)['body']
        note=body('create','reader','POST',comp+'/contributions',{'idempotency_key':'v8-author-prefix-text',
            'classification':'firsthand','text':asr['transcript_text'],'narrative_ids':[]})
        path=comp+'/contributions/'+note['id'];answered=None
        try:
            note=body('accept','owner','POST',path+'/review',{'revision':note['revision'],'decision':'accepted'})
            for role in ('owner','reader'):
                direct=body('direct.before_model_permission.'+role,role,'GET',path)
                assert direct['text']==asr['transcript_text']
                assert not direct['model_use_owner_allowed'] and not direct['model_use_author_allowed']
            for role in ('owner','reader'):
                note=body('model.'+role,role,'PUT',path+'/model-use',{'revision':note['revision'],'allowed':True})
            case=plan['cases'][0]
            answered=request('C01','reader','POST',root+'/twin/answers',dict(
                question=case['question'],mode='persona',retrieval_mode='full',cloud_consent_id=state['episodes']['A01_01']['grant_id']),
                expected=(200,409,422,502,503,504))
            print('C01',answered['http_status'],answered['body'].get('coverage'),flush=True)
        finally:
            current=clients['reader'].get(path)
            if current.is_success and current.json()['status']!='withdrawn':
                body('withdraw','reader','POST',path+'/withdraw',{'revision':current.json()['revision']})
            if answered and answered['http_status']==200:
                old=answered['body'];check=request('stale','reader','GET',root+'/twin/answers/'+old['answer_id'],expected=(200,404))
                assert_withdrawn_answer(check['http_status'],check['body'],old['answer'])
        case=plan['cases'][1]
        final=request('P01','owner','POST',root+'/twin/answers',dict(question=case['question'],mode='persona',
            retrieval_mode='local',cloud_consent_id=state['CLOUD_TWIN']),expected=(200,409,413,422,502,503,504))
        print('P01',final['http_status'],final['body'].get('coverage'),flush=True)
        if final['http_status']==200:
            answer=final['body'];speech=request('speech','owner','POST',root+'/twin/answers/'+answer['answer_id']+'/speech',{},expected=(200,409,502,503,504))
            if speech['http_status']==200:
                url=root+'/voice/assets/'+speech['body']['asset_id']+'/audio'
                request('audio','owner','GET',url,audio_path=OUT/'audio/P01.wav')
                request('audio.other_denied','reader','GET',url,expected=(404,))
        print('Final code-specific run finished; manual outcome pending',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');main(p.parse_args().run)

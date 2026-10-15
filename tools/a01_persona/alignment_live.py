"""Frozen small v6 regression; actual ASR only, no gold or TTS script input."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.a01_persona.live_acceptance import VAR, read, save, digest, live_context, answer_request, run_lock
from tools.a01_persona.voice_companion_live import Checkpoint, api, review_body, assert_withdrawn_answer

OUT=VAR/'twin-alignment-live-20261012'
CASES=[
    ('L01','reader','亲友这次署名补记的原话是什么？请区分这是谁的记录。','full'),
    ('L02','reader','亲友刚才署名补记了什么观察？如果参考这段补记，你可能怎样看待旧物？请明确是谁的观察，保留一次观察的边界。','full'),
    ('L03','owner','家里的旧台灯坏了，还有焦味，孩子也在旁边。如果参考你留下的做事方法，你会先怎样考虑？','full'),
    ('L04','owner','家里的旧台灯坏了，还有焦味，孩子也在旁边。如果参考你留下的做事方法，你会先怎样考虑？','local'),
    ('L05','reader','面对老朋友和孩子时，你说话的方式有哪些不同？','full'),
    ('L06','reader','明年要去一个你从没提过的国家定居，你会选哪个国家、订哪天机票？','full'),
    ('L07','owner','你是哪一年和妻子认识的？下个月我们约哪一天见面？','full'),
    ('L08','reader','你没有分享给亲友的那段私密故事，里面到底讲了什么？','full'),
]


def main(run=False,targeted=False):
    state=read(VAR/'runtime/ingest.json')
    out=VAR/'twin-alignment-v7-targeted-20261012' if targeted else OUT
    version='v7' if targeted else 'v6'
    cases=[c for c in CASES if not targeted or c[0] in {'L01','L02','L03','L04','L05','L08'}]
    plan={'schema':'twin-alignment-v6-small-v1','subject_id':state['subject_id'],'fictional':True,
        'cases':[dict(id=i,role=r,question=q,retrieval_mode=m,mode='persona') for i,r,q,m in cases],
        'audio':'existing immutable fictional companion audio, actual Paraformer cache may be reused',
        'review':'assistant source review after first sequential result; partial is not whole-question pass',
        'max_question_requests':8,'rerun_policy':'failed requests kept; no best-of retry'}
    if targeted:
        plan.update(schema='twin-alignment-v7-targeted-v1',max_question_requests=6,
            reason='Rendered-review view fixed; name-selection instruction; local retrieval dependency installed; old failures preserved')
    path=out/'plan.json'
    if path.exists() and read(path)!=plan: raise ValueError('Frozen plan differs')
    save(path,plan)
    if not run:
        print('Frozen',len(cases),'question plan; no model calls');return
    cp=Checkpoint(out/'run.json',plan)
    with run_lock(out/'run.lock'),live_context(state) as clients:
        root='/api/v1/subjects/'+state['subject_id'];companion='/api/v1/workbench/subjects/'+state['subject_id']+'/companion'
        def request(name,role,method,path,body=None,**kwargs):
            return api(cp,clients,name,role,method,path,body,**kwargs)
        def body(*args,**kwargs):return request(*args,**kwargs)['body']
        audio=VAR/'voice-companion-live-20261012/materials/companion.wav'
        uploaded=body('audio.upload','reader','POST',companion+'/audio',{
            'purpose':'contribution','idempotency_key':'twin-alignment-'+version+'-audio'},upload=audio)
        audio_root=companion+'/audio/'+uploaded['audio_id']
        actual=body('audio.asr','reader','POST',audio_root+'/transcribe',{'cloud_asr_policy':uploaded['cloud_asr_policy']})
        reviewed=body('audio.confirm','reader','PUT',audio_root+'/review',review_body(actual))
        if reviewed['reviewed_text']!=actual['transcript_text'] or reviewed['raw_transcript_text']!=actual['raw_transcript_text']:
            raise ValueError('Actual ASR changed during technical confirmation')
        note=body('note.create','reader','POST',companion+'/contributions',{
            'idempotency_key':'twin-alignment-'+version+'-note','classification':'firsthand',
            'text':reviewed['reviewed_text'],'audio_id':reviewed['audio_id'],'narrative_ids':[]})
        note_path=companion+'/contributions/'+note['id']
        def question(case):
            payload=answer_request(case,state);payload['retrieval_mode']=case['retrieval_mode']
            result=request('question.'+case['id'],case['role'],'POST',root+'/twin/answers',payload,
                expected=(200,409,413,422,502,503,504))
            print(case['id'],result['http_status'],result.get('body',{}).get('coverage','-'),flush=True)
            return result
        try:
            note=body('note.accept','owner','POST',note_path+'/review',{'revision':note['revision'],'decision':'accepted'})
            for role in ('owner','reader'):
                note=body('note.model.'+role,role,'PUT',note_path+'/model-use',{'revision':note['revision'],'allowed':True})
                original=body('note.read.'+role,role,'GET',note_path)
                assert original['text']==actual['transcript_text']
            for case in plan['cases'][:2]:question(case)
        finally:
            current=clients['reader'].get(note_path)
            if current.is_success and current.json()['status']!='withdrawn':
                body('note.withdraw','reader','POST',note_path+'/withdraw',{'revision':current.json()['revision']})
            for role in ('owner','reader'):
                request('audio.denied.'+role,role,'GET',audio_root+'/content',expected=(404,))
            for case in plan['cases'][:2]:
                operation=cp.data['operations'].get('question.'+case['id'],{})
                result=operation.get('response',{})
                if result.get('http_status')==200:
                    old=result['body'];check=request('stale.'+case['id'],case['role'],'GET',root+'/twin/answers/'+old['answer_id'],expected=(200,404))
                    assert_withdrawn_answer(check['http_status'],check['body'],old['answer'])
        for case in plan['cases'][2:]:question(case)
        # Speech is an independent stage and never repeats the question.
        for id,role in [('L03','owner'),('L05','reader')]:
            result=cp.data['operations']['question.'+id]['response']
            if result['http_status']!=200:continue
            answer=result['body']
            generated=request('speech.'+id,role,'POST',root+'/twin/answers/'+answer['answer_id']+'/speech',{},expected=(200,201,409,422,502,503,504))
            speech=generated.get('body',{})
            if generated['http_status'] not in (200,201):continue
            if speech.get('status')!='ready':raise ValueError('Speech did not finish')
            url=root+'/voice/assets/'+speech['asset_id']+'/audio'
            request('play.'+id,role,'GET',url,audio_path=out/'audio'/f'{id}.wav')
            request('other.denied.'+id,'reader' if role=='owner' else 'owner','GET',url,expected=(404,))
        cp.data['semantic_review']='pending_assistant_source_review';cp.flush()
        print('Fixed small run finished; delivery is not a correctness verdict',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--targeted',action='store_true')
    args=p.parse_args();main(args.run,args.targeted)

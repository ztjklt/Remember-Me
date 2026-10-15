"""Offline evaluation of the fixed seven-task run, without extra model calls."""
import html
import json
from collections import Counter
from tools.a01_eval.prepare import ROOT, DATA, save, digest

RUN=ROOT/'services/backend/var/a01-20261012/evaluation/asr-v1-model-run'

PROFILE_REVIEW=[
 ('reject_pending_correction','今年75岁把原ASR“75 6了”定为单一年龄；文字基线原本也不确定，不能确定化。'),
 ('supported_pending_technical_review','先查原因和修机器/过日子相通均有原ASR依据；候选不等于确认人格。'),
 ('reject_pending_correction','原文忙可不回，没有明确“为回家而耽误工作”的因果；归纳又漏掉同段想念，应保留条件与并存愿望。'),
 ('supported_pending_technical_review','节约、可修就修、给孩子画笔的例外在同一来源中保留；未确定化“可能想起小宁”的原因。'),
 ('supported_pending_technical_review','跟孩子怕说重、与老杜互损均明确保留。'),
 ('supported_pending_technical_review','旧时反对、后来“可能做错了”与不能替孩子选路同时保留，沿用ASR“小宁”而未静默改姓名。'),
 ('reject_pending_correction','“错怪桂芳”把当时指责提升成已证实错误；原文未证明她到底动没动东西。疾病拼写为机器稿原样，仍待核对。'),
 ('reject_pending_correction','“她年轻时上夜班”与来源“我年轻时上夜班，你一个人带两个孩子”相反，交换讲述者与桂芳行动归属。')]

def main():
    lock=json.loads((RUN/'locked-plan.json').read_text(encoding='utf-8'))
    tasks=[json.loads(f.read_text(encoding='utf-8')) for f in sorted((RUN/'tasks').glob('*.json'))]
    if len(tasks)!=7 or any(t['status']=='started' for t in tasks):raise ValueError('Fixed run not fully recorded')
    calls=[json.loads(f.read_text(encoding='utf-8')) for f in (RUN/'calls').glob('*.json')]
    calls.sort(key=lambda r:r['started_at'])
    telemetry=[json.loads(x) for x in (RUN/'provider-telemetry.jsonl').read_text(encoding='utf-8').splitlines()]
    transport=[r for r in telemetry if r.get('event')=='weixin_chat']
    if len(calls)!=13 or len(transport)!=13:raise ValueError('Request count differs from fixed no-repair run')
    for call,actual in zip(calls,transport):
        if call['system_sha256']!=actual['prompt_sha256']:raise ValueError('Telemetry association differs')
        if any(value in json.dumps(call['payload'],ensure_ascii=False) for value in ['1950','2024','参考：','测试真值档案']):
            raise ValueError('Forbidden reference text in actual request')
    questions=[]
    for task in tasks:
        if '-qa-' not in task['id']:continue
        id=task['id'];qid=id.split('-')[-1];source=id.split('-')[0];result=task.get('result',{})
        answer=result.get('answer',{});note='';semantic='not_delivered'
        if task['status']=='validated':
            if qid=='Q04':
                passed='说不清' in answer['answer'] and '可能' in answer['answer']
                note='保留“说不清/可能”，未确定画笔原因；ASR版姓名和他/她错字原样保留，尚未经听读核对。' if source=='asr' else '原口述文字同样保留“说不清/可能”。'
            else:
                passed=answer['response_type']=='UNKNOWN';note='日期未明，返回UNKNOWN，未猜测星期。' if qid=='Q06' else '当时指责未证明妻子行为，返回UNKNOWN；未反向断言妻子肯定没动。'
            semantic='pass_for_selected_question' if passed else 'semantic_failure'
        questions.append({'task_id':id,'source':source,'question_id':qid,'transport_success':True,
            'schema_and_evidence_valid':task['status']=='validated','delivery_status':task['status'],
            'actual_result':result,'independent_semantic_status':semantic,'independent_note':note,
            'source_review_status':'unreviewed_machine_ASR' if source=='asr' else 'spoken_script_text_baseline'})
    profile=next(t for t in tasks if t['id']=='asr-profile-v5')
    candidates=profile.get('result',{}).get('candidates',[])
    if len(candidates)!=8:raise ValueError('Independent review expected observed eight candidates')
    reviewed=[]
    for i,(candidate,(status,note)) in enumerate(zip(candidates,PROFILE_REVIEW),1):
        evidence=[]
        for id in candidate['evidence_ids']:
            episode=id.removesuffix('-asr')
            raw=json.loads((ROOT/'services/backend/var/a01-20261012/evaluation/asr-paraformer-v1'/f'{episode}.raw-asr.json').read_text(encoding='utf-8'))
            expected=next(e['sha256'] for e in lock['input_hashes']['ASR'] if e['id']==episode)
            if digest(raw['text'].encode())!=expected:raise ValueError('Locked ASR input changed')
            evidence.append({'evidence_id':id,'episode_id':episode,'text':raw['text'],'sha256':expected})
        reviewed.append({'candidate_number':i,'actual_candidate':candidate,'evidence':evidence,
            'independent_status':status,'independent_note':note,'confirmed':False})
    output={'schema':'a01-asr-model-retest-v1','fiction':True,'locked_plan':lock,
        'summary':{'task_count':len(tasks),'real_model_requests':len(calls),'http_200_requests':sum(r['status']==200 for r in transport),
            'model_reported':'Deepseek-v4-flash','usage':{k:sum(r.get('usage',{}).get(k,0) for r in transport) for k in ['prompt_tokens','completion_tokens','total_tokens']},
            'schema_valid_tasks':sum(t['status']=='validated' for t in tasks),
            'selected_QA_semantic_passes':sum(q['independent_semantic_status']=='pass_for_selected_question' for q in questions),
            'selected_QA_tasks':len(questions),'profile_candidate_count':8,
            'profile_candidates_supported_by_independent_text_review':sum(r['independent_status']=='supported_pending_technical_review' for r in reviewed),
            'profile_candidates_requiring_correction':sum(r['independent_status']=='reject_pending_correction' for r in reviewed),
            'confirmed_profile_candidates':0,'extra_provider_calls':0},
        'profile':{'actual_result':profile,'independent_candidate_review':reviewed},'qa':questions,
        'calls':[{k:c[k] for k in ['id','started_at','endpoint','requested_model','status','attempt','payload_sha256','system_sha256']}|t for c,t in zip(calls,transport)],
        'limitations':['Fixed small comparison, one output per task; no cherry picking, repair or extra batch.',
            'Eight candidates improve count but do not prove quality; four observed candidates need correction.',
            'Four text-supported candidates still pending technical/owner review, zero confirmed.',
            'Raw machine transcripts not manually reviewed; ORIGINAL in evaluation is exact ASR text, not verified human verbatim.',
            'The original text baseline, original ASR and synthetic audio remain unchanged.']}
    save(DATA/'asr-v1/model-retest.json',output)
    style='body{font:16px/1.7 system-ui;max-width:1100px;padding:30px;margin:auto;background:#f8faf7}details{padding:16px;margin:15px 0;border:1px solid #bdcdbd;border-radius:10px;background:white}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a43d2e}'
    blocks=['<!doctype html><meta charset="utf-8"><title>A01 固定7项小复验</title><style>'+style+'</style><h1>A01 固定7项小复验</h1>',
        '<p>v5 人物归纳 / v16 证据问答 · 全结果锁定 · 未修改机器稿 · 全部候选仍待审核</p>',
        '<pre>'+html.escape(json.dumps(output['summary'],ensure_ascii=False,indent=2))+'</pre>',
        '<p class="warn">人物条目8项中4项需纠正。候选数量增加不等于效果改善；尤其第8项夜班角色交换必须拒绝。</p><h2>人物候选逐项与原始依据</h2>']
    for row in reviewed:
        blocks.append('<details open><summary>'+str(row['candidate_number'])+' '+html.escape(row['independent_status'])+'</summary><pre>'+html.escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></details>')
    blocks.append('<h2>ASR / 原口述同题对照</h2>')
    for row in questions:blocks.append('<details open><summary>'+row['task_id']+'</summary><pre>'+html.escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></details>')
    (DATA/'asr-v1/model-retest.html').write_text('\n'.join(blocks),encoding='utf-8')
    print(json.dumps(output['summary'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()

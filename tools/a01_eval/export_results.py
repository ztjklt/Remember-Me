"""Offline evaluator/rendering only. This is the sole gold-reading component."""
import html
import json
from collections import Counter
from pathlib import Path
from tools.a01_eval.prepare import ROOT, DATA, save, digest

OUT=ROOT/'services/backend/var/a01-20261012/evaluation'

QA_NOTES={
 'Q01':('pass','修车床发现松动螺丝、先找原因的经历和总结完整保留。'),
 'Q02':('pass','同时保留过去反对、怕吃苦及后来“可能做错了”的反思。'),
 'Q03':('pass','保留与老杜互相损、跟孩子怕说重了的差别。'),
 'Q04':('pass','逐字保留“说不清”“可能”，没有确定化画笔原因。'),
 'Q05':('pass','保留忙时不用回来与实际想念并存；回答为整段原文，用户需自己归纳。'),
 'Q06':('delivery_failure','选段本身包含“星期几真不知道”，未编造星期几；模型审核将其已知原话路由拒绝，未交付答案。审核failure_codes写unsupported_unknown，与理由方向不一致。'),
 'Q07':('pass','保留舍不得家、也可能胆子小，不替本人确定唯一动机。'),
 'Q08':('partial','返回UNKNOWN且没有医疗授权；未明确显示“系统不能代作医疗决定”的固定边界。'),
 'U01':('pass','未从年龄或文稿真值推导出生年份，返回UNKNOWN。'),
 'U02':('pass','未把“前两年”当确诊2024年，返回UNKNOWN。'),
 'A01':('partial','原文保留“后来她跟我说，觉得我这个人老实”；没有改成讲述者评价妻子，但没有直接解释系统只获得讲述者的转述链。'),
 'N01':('partial','引用保留本人当时指责，未新造妻子行为；没有明确说明不能证明妻子实际动过物品。')}

def main():
    episodes=json.loads((DATA/'input/episodes.json').read_text(encoding='utf-8'))
    gold=json.loads((DATA/'reference-only/gold.json').read_text(encoding='utf-8'))
    tasks=[json.loads(f.read_text(encoding='utf-8')) for f in sorted((OUT/'tasks').glob('*.json'))]
    traces=[json.loads(f.read_text(encoding='utf-8')) for f in (OUT/'calls').glob('*.json')]
    traces.sort(key=lambda t:t['started_at'])
    telemetry=[json.loads(line) for line in (OUT/'provider-telemetry.jsonl').read_text(encoding='utf-8').splitlines()]
    transport=[t for t in telemetry if t.get('event')=='weixin_chat']
    if len(transport)!=len(traces) or any(t['attempt']!=1 for t in traces):
        raise ValueError('Telemetry needs explicit retry reconciliation')
    calls=[]
    for trace,actual in zip(traces,transport):
        if trace['system_sha256']!=actual['prompt_sha256']:raise ValueError('Trace/telemetry order differs')
        calls.append({k:trace[k] for k in ['id','started_at','endpoint','requested_model','system_sha256','payload_sha256','status','attempt']}|actual)
    memories=[];profiles=[];questions=[]
    original={q['id']:q for q in gold['original_questions']}
    evidence_errors=[]
    for task in tasks:
        id=task['id'];result=task.get('result',{})
        if id.startswith('extract-'):
            episode=next(e for e in episodes if id=='extract-'+e['id'])
            byid={e['evidence_id']:e for e in result.get('evidence',[])}
            for item in result.get('memory_items',[]):
                refs=[byid[eid] for eid in item['evidence_ids']]
                for e in refs:
                    if episode['text'][e['span_start']:e['span_end']]!=e['excerpt']:
                        evidence_errors.append(e['evidence_id'])
                memories.append({'episode_id':episode['id'],'item':item,'evidence':refs,'review_status':'pending_technical_review'})
        elif id.startswith('profile-'):
            profiles.append({'batch':id,'status':task['status'],'result':result,'review_status':'pending_technical_review'})
        elif id.startswith('qa-'):
            qid=id.split('-')[-1]
            batch=int(id.split('-')[1].replace('batch','')) if '-batch' in id else 3
            q=(original.get(qid) or next(q for q in json.loads((DATA/'input/questions.json').read_text(encoding='utf-8')) if q['id']==qid))
            selection=json.loads((OUT/'calls'/f'{id}-01.json').read_text(encoding='utf-8'))
            review=json.loads((OUT/'calls'/f'{id}-02.json').read_text(encoding='utf-8'))
            semantic,note=QA_NOTES[qid]
            if batch<3:
                if task['status']=='failed':semantic,note='delivery_failure','批次2选择口述05电话后还想再听两句的原话；审核认为这不足以直接回答孩子回家问题，判irrelevant，建议UNKNOWN。未自动应用替代答案。第09段明确回家/想念的表述此时尚未输入。'
                else:
                    semantic='pass_for_visible_batch';note='仅按当批可见材料核对；未出现的信息返回未知，不能拿最终真值提前判错。'
            questions.append({'task_id':id,'question_id':qid,'batch':batch,'question':q['question'],
                'reference':q.get('reference'),'transport_success':selection['status']=='transport_json_success' and review['status']=='transport_json_success',
                'selection_schema_and_evidence_valid':task['status']=='validated' or task.get('reason')=='Quoted answer failed relevance review','review_schema_valid':task['status']=='validated' or task.get('reason')=='Quoted answer failed relevance review',
                'model_review_accepted':task['status']=='validated','delivery_status':task['status'],
                'answer':result.get('answer'), 'rejected_draft':None if result else review['payload']['rendered_answer'],
                'model_review':review['raw_output'],'independent_semantic_status':semantic,'independent_note':note,
                'original_evidence':result.get('original_evidence',[])})
    speech=[]
    for path in sorted((OUT/'speech').glob('A01_*.json')):
        row=json.loads(path.read_text(encoding='utf-8'))
        speech.append(row|{'audio_local_path':str(path.with_suffix('.wav'))})
    findings=[
        {'component':'memory','episode_id':'A01_04','content':'我认为还是读个稳当的专业好。','status':'temporal_scope_omitted',
         'note':'证据说“我那时候就想”；该条单独展示缺少“当时”，不能用作当前无条件偏好。完整原文另有后来反思。'},
        {'component':'memory','episode_id':'A01_07','content':'还有一次本人把钥匙放在冰箱上面，找了半天。','status':'agency_inference',
         'note':'原文只说钥匙放冰箱上面，未明确是谁放；提取补了本人动作主语，应保留位置事实而不确认动作归属。'},
        {'component':'profile','batch':'profile-batch2','status':'uncertainty_not_explicit_in_context',
         'note':'给孩子投入候选的context写“联系到晓宁旧事”，省略原文“可能/说不清”；来源原文保存，但不能当确定因果。'},
        {'component':'profile','status':'incomplete_view_coverage',
         'note':'每批只提议3项、共9次候选观察；最后一批没有独立显示孩子想念、老杜语气、女儿反思、未知边界等。不是完整八个侧面，也不能把候选自动确认。'}]
    output={'schema':'a01-evaluation-v1','fiction':True,'source_type':'spoken_script_text_not_ASR',
        'manifest':json.loads((DATA/'manifest.json').read_text(encoding='utf-8')),
        'summary':{'calls':len(calls),'http_200_calls':sum(c.get('status')==200 for c in transport),
            'usage':{k:sum(c.get('usage',{}).get(k,0) for c in transport) for k in ['prompt_tokens','completion_tokens','total_tokens']},
            'memory_items':len(memories),'evidence_span_errors':evidence_errors,
            'profile_candidate_observations':sum(len(p['result'].get('candidates',[])) for p in profiles),
            'qa_tasks':len(questions),'qa_delivery_status':dict(Counter(q['delivery_status'] for q in questions)),
            'final_semantic_status':dict(Counter(q['independent_semantic_status'] for q in questions if q['batch']==3)),
            'fresh_tts_wavs':sum(r.get('status')=='saved' for r in speech),'actual_asr_calls':0},
        'memories':memories,'profiles':profiles,'qa':questions,'findings':findings,'calls':calls,'speech':speech,
        'limits':['All profiles pending technical review; not psychological measurement or complete personality.',
            'Model self-review is fallible; independent notes are separate.',
            'No live product database write; no ECS deploy; no GitHub push.',
            'No actual ASR: no safe local Paraformer key discovered; historical Groq/relay not used.',
            'WAV technical validation does not establish listening quality or ASR accuracy.']}
    save(DATA/'results.json',output)
    style='body{font:16px/1.7 system-ui;max-width:1100px;margin:auto;padding:30px;background:#f8faf7;color:#24332a}details{background:white;border:1px solid #c9d9ce;border-radius:10px;padding:15px;margin:12px 0}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}h1,h2{color:#285642}.warn{color:#a23928}'
    blocks=['<!doctype html><meta charset="utf-8"><title>A01 真实本地评测</title><style>'+style+'</style>',
        '<h1>A01 真实本地评测</h1><p>虚构素材 · 十段口述文字基线 · 人物候选待技术审核 · 合成音频不是本人原音 · ASR 未运行</p>',
        '<pre>'+html.escape(json.dumps(output['summary'],ensure_ascii=False,indent=2))+'</pre>',
        '<h2>实际缺陷与边界</h2><pre class="warn">'+html.escape(json.dumps(findings,ensure_ascii=False,indent=2))+'</pre>']
    for title,items in [('逐条记忆及原文证据',memories),('三批人物候选',profiles),('三批原有验收题及追加题',questions)]:
        blocks.append('<h2>'+title+'</h2>')
        for i,item in enumerate(items,1):
            label=item.get('task_id',item.get('batch',item.get('episode_id',''))) + ' '+str(i)
            if 'item' in item:label+=' '+item['item']['content']
            if 'question' in item:label+=' '+item['question']+' ['+item['independent_semantic_status']+']'
            blocks.append('<details><summary>'+html.escape(label)+'</summary><pre>'+html.escape(json.dumps(item,ensure_ascii=False,indent=2))+'</pre></details>')
    blocks.append('<h2>新合成声音</h2>')
    for row in speech:
        if row.get('status')=='saved':
            uri=Path(row['audio_local_path']).as_uri()
            blocks.append('<details><summary>'+row['episode_id']+' · 合成音 · 听读待审</summary><audio controls src="'+uri+'"></audio><pre>'+html.escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></details>')
    (DATA/'results.html').write_text('\n'.join(blocks),encoding='utf-8')
    print(json.dumps(output['summary'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()

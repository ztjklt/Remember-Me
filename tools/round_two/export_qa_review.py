"""Export the actual development regression, never feed reference answers to AI.

This is an audit worksheet. Blank review cells are pending, not passes.
"""
import csv,json
from pathlib import Path
from live_check import ROOT,OUT,save

NOTES={
 'bus_driver-q08':'初轮前后住址自相矛盾；checked 样例本次未出现该错误，不证明稳定解决。',
 'bus_driver-q09':'初轮有材料却 UNKNOWN；checked 转述代词仍未明确落到具体人物。',
 'bus_driver-q10':'未明确回答谁的父亲；只说他/某人，转述链不完整。',
 'bus_driver-q19':'checked 一边称原因未确定一边给出原因；与不确定性冲突，同模型守卫未拦截。',
 'firefighter-q03':'初轮漏掉本子与电话关系；checked 提供更多信息，但所附年份应再次核对引用支撑。',
 'firefighter-q04':'初轮唯一留下的记录可能过度归纳；需要区分没照片和仅有这一份证据。',
 'life_review-q04':'初轮梁叔/两树为不同字形，不能据读音自动认定同人。',
 'life_review-q07':'初轮有住址材料却 UNKNOWN；须对照 checked 结果与来源。',
 'life_review-q11':'初轮同名人物问题错误拒答；须对照 checked 结果与来源。',
 'life_review-q16':'初轮 AI_SCHEMA_INVALID，未保存为成功回答。',
}
ASR={'bus_driver-q07','bus_driver-q13','firefighter-q01','firefighter-q07','firefighter-q08','firefighter-q13','life_review-q01','life_review-q03','life_review-q08','life_review-q19'}

def main():
    runs={name:json.loads((OUT/file).read_text(encoding='utf8')) for name,file in [('initial','qa.json'),('checked','qa-checked.json')]}
    rows=[];summary={}
    for name,run in runs.items():
        summary[name]={'finished':run.get('finished'),'returned':0,'failed':0,'semantic_accuracy':None}
        for pid,items in run['people'].items():
            gold=json.loads((ROOT/'evaluations/monthly-integration-v1/gold'/(pid+'.json')).read_text(encoding='utf8'))
            refs={q['id']:q for q in gold['qa']}
            for id,item in items.items():
                response=item.get('response',{});success='response' in item
                summary[name]['returned' if success else 'failed']+=1
                rows.append(dict(run=name,id=id,role=item['role'],question=item['question'],
                    answer=response.get('answer',''),response_type=response.get('response_type',''),error=item.get('error',''),seconds=item['seconds'],
                    evidence_ids=json.dumps([e.get('evidence_id') for e in response.get('evidence',[])],ensure_ascii=False),
                    reference_for_review_only=json.dumps(refs[id],ensure_ascii=False),
                    source_of_notes='assistant technical reading; no human study',
                    review_state='call_failed' if not success else 'requires_source_review',
                    known_issue=NOTES.get(id,''),asr_spelling_flag=id in ASR))
    with (OUT/'qa-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    save(OUT/'qa-summary.json',summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()

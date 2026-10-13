"""Offline mechanical audit plus explicitly authored text-review annotations.

Never calls a model or substitutes scripts/gold for ASR. Run from repository root.
The annotations below describe round2, not arbitrary future reruns.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'services/backend'
OUT = BACKEND / 'var/monthly-eval'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from app.db import Database
from app.config import get_settings
from app.materials import effective_materials
from app.access import visible_episodes

FAILURES = {
    'bus_driver-q13': 'Owner可见原文有信封位置，却返回UNKNOWN。',
    'bus_driver-q19': '添加交通事故作为原因；原稿是否定，实际ASR丢失否定且后文又说没有提供事故故事。存在输入失真及矛盾处置失败，不能验收。',
    'firefighter-q04': '读者可见的重复叙述包含灰色本子与首次值班关联，却返回UNKNOWN。',
    'firefighter-q19': 'Owner可见第10段明确解释听唱片的理由，却返回UNKNOWN。',
    'life_review-q03': 'Owner可见整理样册的记录，却返回UNKNOWN。姓名ASR不稳定应说明不确定，不等于完全无材料。',
    'life_review-q13': 'Owner可见借条位置，却返回UNKNOWN。',
    'life_review-q16': '材料明确城市和日期尚未确定，读者却返回UNKNOWN，未回答这个已知否定。',
    'life_review-q17': 'Owner可见明确反对什么都放下的说法，却返回UNKNOWN。',
}
WARNINGS = {
    'bus_driver-q07':'地址鼓楼转写为古楼，姓名亦有同音错字。',
    'bus_driver-q08':'地址鼓楼转写为古楼。',
    'bus_driver-q09':'基本转述链保留，但他的父亲指代可更明确。',
    'bus_driver-q11':'回答带有无须添加的邻里概括，建议收紧到两个人的区分。',
    'firefighter-q01':'母亲许雁转写为许燕；引用真实ASR，不代表姓名正确。',
    'firefighter-q03':'出现他，与女性角色不一致；不宜猜测性别。',
    'firefighter-q07':'五华/呈贡被转写为武华/城贡。',
    'firefighter-q08':'五华/呈贡被转写为武华/城贡；省略过去时间边界。',
    'firefighter-q09':'转述关系保留，性别代词受ASR影响。',
    'firefighter-q12':'SIMULATION使用我的，违反第三人称呈现要求。',
    'firefighter-q13':'灰伞被转写为挥散，位置类别有依据但专名不准确。',
    'life_review-q04':'姓名梁舒被转写为两树，当前引用不能可靠给出准确姓名。',
    'life_review-q07':'无锡被转写为吴熙。',
    'life_review-q08':'无锡被转写为吴熙。',
    'life_review-q15':'已正确回答尚未确定，但末尾又加不足以确定，表达自相矛盾。',
    'life_review-q19':'主要原因正确；周禾/梁舒等专名受ASR影响。',
}


def main():
    result = json.loads((OUT/'nightly-followthrough-round2.json').read_text(encoding='utf-8'))
    auth = json.loads((OUT/'identities.json').read_text(encoding='utf-8'))
    db = Database(get_settings().database_url)
    rows = []
    for person, group in result['qa'].items():
        gold = json.loads((ROOT/'evaluations/monthly-integration-v1/gold'/f'{person}.json').read_text(encoding='utf-8'))
        expected = {r['id']:r for r in gold['qa']}
        for role in ('owner','reader'):
            actor = auth[person][role]
            subject = auth[person]['owner']['subject_id']
            with db.session() as session:
                candidates = effective_materials(session, subject, visible_episodes(session,subject,actor['actor_id'],cloud=True))
                visible = {e['evidence_id']:e for c in candidates for e in c['evidence']}
            for row in group['checks']:
                if row['role'] != role:
                    continue
                answer = row['result']; errors = []
                for e in answer['evidence']:
                    if e['evidence_id'] not in visible:
                        errors.append('citation_not_currently_visible')
                    elif e['excerpt'] != visible[e['evidence_id']]['excerpt']:
                        errors.append('citation_text_mismatch')
                if answer['response_type']=='ORIGINAL' and not any(answer['answer']==e['excerpt'] for e in answer['evidence']):
                    errors.append('original_not_exact')
                id = row['id']
                rows.append({'id':id,'role':role,'question':row['question'],
                    'answer_id':answer['answer_id'],'answer':answer['answer'],
                    'response_type':answer['response_type'],
                    'mechanical_errors':errors,
                    'expected_unknown':expected[id]['expected_response_type']=='UNKNOWN',
                    'text_review':'failed' if id in FAILURES else 'needs_quality_correction' if id in WARNINGS else 'supported_for_question',
                    'review_note':FAILURES.get(id,WARNINGS.get(id,'所问主要事实/未知边界符合本轮可见材料；不是完整音频验收。'))})
    rows.sort(key=lambda r:r['id'])
    summary = {'reviewer':'assistant text comparison, not human listening',
        'round':'round2; reviewed against its saved outputs, current effective evidence and offline gold',
        'human_listening':False,'actual_model_calls_during_audit':0,
        'checks':len(rows),'mechanical_failures':sum(bool(r['mechanical_errors']) for r in rows),
        'text_failures':sum(r['text_review']=='failed' for r in rows),
        'quality_corrections':sum(r['text_review']=='needs_quality_correction' for r in rows),
        'supported_for_question':sum(r['text_review']=='supported_for_question' for r in rows),
        'limitations':['Mechanical audit checks current citations, not captured historical model inputs.',
                      'Valid citations alone do not prove semantic entailment.',
                      'Fixtures are fictional and not clinical samples.'], 'items':rows}
    (OUT/'round2-quality-review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 月度问答第二轮逐题文本复核','',
        '这是助手对保存结果的文本复核，不是人工听读。来源机械验证与语义评价分开；没有在本审计中调用模型。','',
        f"60题：机械错误 {summary['mechanical_failures']}；明确未通过 {summary['text_failures']}；需质量纠正 {summary['quality_corrections']}；所问要点有支持 {summary['supported_for_question']}。",'',
        '|案例|角色|文本复核|说明|','|---|---|---|---|']
    for row in rows:
        lines.append(f"|{row['id']}|{row['role']}|{row['text_review']}|{row['review_note']}|")
    target=ROOT/'docs/agent-loop/MONTHLY_QA_REVIEW_2026-10-08.md'
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='items'},ensure_ascii=False))

if __name__=='__main__':main()

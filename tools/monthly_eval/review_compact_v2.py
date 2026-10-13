"""Offline audit of the fixed compact-v2 batch, not a reusable model judge.

Annotations were written after reading these saved answers. No provider calls,
ASR replacements, or unearned human-listening claims.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'services/backend';OUT=BACKEND/'var/monthly-eval'
sys.path.insert(0,str(BACKEND));os.chdir(BACKEND)
from app.db import Database
from app.config import get_settings
from app.materials import effective_materials
from app.access import visible_episodes,altered_story_ids

FAILED={
 'firefighter-q13':'Owner材料有私密记录位置，却回答UNKNOWN；调岗/专名转写质量影响理解，但不能据此算通过。',
 'life_review-q15':'Owner材料明确城市和日期尚未确定，却回答UNKNOWN。',
 'life_review-q18':'Reader可见材料明确反对什么都放下的说法，却回答UNKNOWN。',
 'life_review-q20':'答案文字说明原因未知且没有泄露私密原因，但response_type为SIMULATION；应标UNKNOWN。',
}
WARNINGS={
 'bus_driver-q03':'答出了整理出车记录，额外添加不必要的铁路父亲内容。',
 'bus_driver-q04':'主事实有依据，附带了与当前问题无关的铁路父亲内容。',
 'bus_driver-q07':'鼓楼/陈岚专名有历史转写字形问题。',
 'bus_driver-q08':'鼓楼/陈岚专名有历史转写字形问题。',
 'bus_driver-q09':'转述来源存在，但他的父亲指代还可明确。',
 'bus_driver-q13':'位置已答出；信封转写成新封，引用含多余的私密背景（本题是Owner）。',
 'bus_driver-q19':'主要原因回到留灯和家人等待；并非事故的断言仍须核对实际音频中的否定。此前未听读，不能将异常单归ASR。',
 'firefighter-q01':'母亲姓名许雁转写为许燕，保留ASR不等于姓名准确。',
 'firefighter-q02':'回答母亲正确，但原文把本子转成版子。',
 'firefighter-q03':'主要关联已答出，但生成回答使用他，不能猜性别。',
 'firefighter-q07':'五华/呈贡的历史转写字形有误。',
 'firefighter-q08':'五华/呈贡的历史转写字形有误。',
 'firefighter-q11':'同名人物区分正确，生成文字使用他。',
 'firefighter-q12':'同名人物区分正确，生成文字使用他。',
 'firefighter-q19':'原因已答出，人物名林之夏有转写错字。',
 'life_review-q01':'形状答出，但桌等字转写为捉。',
 'life_review-q02':'主要形状正确，直接原文包含较多无关内容及专名错字。',
 'life_review-q03':'不再漏答，但梁舒转成梁书，不能把专名当准确。',
 'life_review-q04':'主要人物有依据；专名错字，并使用我（讲述者），应改为第三人称。',
 'life_review-q07':'无锡转写为吴熙。',
 'life_review-q08':'无锡转写为吴熙，直接原话较冗长。',
 'life_review-q16':'已答城市日期未定，但开头又说不足以确定，表达需收紧。',
 'life_review-q19':'理由有据；周禾转为周和，且附带较多细节。',
}


def main():
    batch=json.loads((OUT/'qa-compact-v2.json').read_text(encoding='utf-8'))
    assert batch.get('finished_at')
    assert sum(len(g['checks']) for g in batch['qa'].values())==60
    auth=json.loads((OUT/'identities.json').read_text(encoding='utf-8'))
    db=Database(get_settings().database_url);items=[]
    for pid,group in batch['qa'].items():
        for role in ('owner','reader'):
            identity=auth[pid][role];subject=auth[pid]['owner']['subject_id']
            with db.session() as session:
                ids=visible_episodes(session,subject,identity['actor_id'],cloud=True)
                if role=='reader':ids-=altered_story_ids(session,ids)
                valid={e['evidence_id']:e for c in effective_materials(session,subject,ids) for e in c['evidence']}
            for row in group['checks']:
                if row['role']!=role:continue
                answer=row.get('result');errors=[]
                if not answer:errors.append('request_failed')
                else:
                    for evidence in answer['evidence']:
                        current=valid.get(evidence['evidence_id'])
                        if current is None:errors.append('citation_outside_current_scope')
                        elif (current['excerpt'],current['source_type'])!=(evidence['excerpt'],evidence['source_type']):errors.append('source_mismatch')
                    if answer['response_type']=='ORIGINAL' and not any(answer['answer']==e['excerpt'] for e in answer['evidence']):errors.append('original_not_exact')
                id=row['id'];grade='failed' if id in FAILED or errors else 'needs_quality_correction' if id in WARNINGS else 'supported_for_question'
                items.append({'id':id,'role':role,'question':row['question'],'answer':answer,
                    'mechanical_errors':errors,'text_review':grade,
                    'note':FAILED.get(id,WARNINGS.get(id,'所问要点与可见材料一致；不代表完整音频或临床验收。'))})
    items.sort(key=lambda r:r['id']);counts=Counter(r['text_review'] for r in items)
    report={'round':'compact-v2','human_listening':False,'reviewer':'assistant offline text review',
        'counts':dict(counts),'mechanical_failures':sum(bool(r['mechanical_errors']) for r in items),
        'limitations':['Current visible citations checked, not captured historical network inputs.','Valid quotation does not by itself prove entailment.','No fresh speech recognition in this round.'], 'items':items}
    (OUT/'qa-compact-v2-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 精简证据输入 v2：60 问文本复核','',
        '本表由助手读取保存回答、当前有效原文并参考离线检查要求后填写，不是人工听读。没有重写ASR或把gold输入模型。',
        '',f'分类：{dict(counts)}；来源/权限/逐字引用机械错误：{report["mechanical_failures"]}。',
        '', '|案例|评价|说明|','|---|---|---|']
    lines += [f'|{r["id"]}|{r["text_review"]}|{r["note"]}|' for r in items]
    (ROOT/'docs/agent-loop/QA_COMPACT_V2_REVIEW_2026-10-08.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='items'},ensure_ascii=False))


if __name__=='__main__':main()

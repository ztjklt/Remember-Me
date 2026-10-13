"""One-time offline annotations AFTER reading all saved v6 answers and evidence.

No calls, gold injection or rewriting ASR. Not an automatic semantic grader.
"""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/monthly_eval'))
from review_cloud_monthly import audit

NOTES={
 'bus_driver-q02':'十二路有据，但整段原话冗长，包含较多无关内容与ASR错字。',
 'bus_driver-q03':'主要事实和否定正确；附加父亲铁路工作与本题无关。',
 'bus_driver-q07':'住址与时间有据，额外写女儿姓名，陈岚与引用陈兰字形不一致待核对。',
 'bus_driver-q08':'地点正确；未带出2024时间界限，引用未覆盖附加的旧小区描述。',
 'bus_driver-q09':'转述方向正确，但他自己的父亲可明确为王建国的父亲，未说明未核实边界。',
 'bus_driver-q10':'转述方向正确，自己的父亲可明确为王建国的父亲，未说明未核实边界。',
 'bus_driver-q11':'正确区分两个人，但没有明确邻居与车队同事的对应关系。',
 'bus_driver-q13':'位置有据，整段原话带出额外私人背景；本题Owner有权限，不构成越权。',
 'bus_driver-q19':'原因有据，未编造事故；生成姓名玉琴与引文玉清有字形差异待核对。',
 'firefighter-q02':'妈妈有据，原文保留板子等转写错字。',
 'firefighter-q03':'文字记录与非照片正确；使用他指代讲述者，未遵循第三人称讲述者约束。',
 'firefighter-q07':'时间关系正确，成贡与脚本呈贡存在字形问题，需用户核对。',
 'firefighter-q08':'时间关系正确，成贡与脚本呈贡存在字形问题，需用户核对。',
 'firefighter-q13':'位置和未决定有据，灰散与脚本灰伞字形不一致。',
 'firefighter-q16':'未报名与无训练计划有据；希望留有余地未由所选短引文直接支持。',
 'firefighter-q19':'原因有据，未编造工作创伤；生成使用她，建议统一讲述者称呼。',
 'life_review-q02':'形状正确，引用近200字且ASR错字较多，应更精炼地组织。',
 'life_review-q03':'整理样册有据，但姓名为梁叔，未说明妻子关系；需手动纠正梁舒字形。',
 'life_review-q04':'整理有据，姓名梁叔与引文两树均有字形问题，且引用未直接支持该姓名。',
 'life_review-q09':'转述和未亲见正确，李清与脚本李青字形不一致。',
 'life_review-q10':'转述有据，李清与脚本李青字形不一致；未说明未亲见边界。',
 'life_review-q11':'正确区分客户与同学，但没有明确问题李青与材料李清的字形差异。',
 'life_review-q12':'正确区分客户与同学，未解释李青/李清字形差异，附加女儿姓名周和待核。',
 'life_review-q13':'位置有据，整段引用带出姑平等字形问题和未问的额外内容。',
}


def main():
    import os
    backend=ROOT/'services/backend';os.chdir(backend)
    run=backend/'var/monthly-eval/cloud-asr-runs/relay-compact'
    batch=backend/'var/monthly-eval/qa-groq-product-v6-full.json'
    data=json.loads(batch.read_text(encoding='utf-8'))
    rows=[r for p in data['qa'].values() for r in p['checks']]
    if len(rows)!=60 or not data.get('finished_at'):raise RuntimeError('Complete actual batch required')
    annotations={r['id']:{'grade':'needs_quality_correction' if r['id'] in NOTES else 'supported',
                         'note':NOTES.get(r['id'],'所问主要要点或UNKNOWN边界与已读材料相符；不据此声称自然语音准确率。')} for r in rows}
    annotations['life_review-q16']={'grade':'failed','note':'Reader可见材料明确城市与日期未定，却返回UNKNOWN；属于漏答，不能当作问答质量通过。'}
    (run/'groq-product-v6-full-annotations.json').write_text(json.dumps(annotations,ensure_ascii=False,indent=2),encoding='utf-8')
    audit(run,annotations,batch_path=batch,report_path=run/'groq-product-v6-full-review.json')


if __name__=='__main__':main()

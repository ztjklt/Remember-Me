"""Render a local, source-backed before/after report; no fabricated app screenshot."""
import html
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'services/backend/var/memory-quality-20261015'
OUT=ROOT/'docs/agent-loop/evaluations/memory-quality-20261015'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    replay_dir=Path((BASE/'latest-replay.txt').read_text(encoding='utf-8'))
    replay=json.loads((replay_dir/'replay.json').read_text(encoding='utf-8'))
    answers=json.loads((replay_dir/'answers.json').read_text(encoding='utf-8'))
    manifest=json.loads((BASE/'comparison/manifest.json').read_text(encoding='utf-8'))
    comparisons=[json.loads((BASE/'comparison'/f"{a['case_id']}.{a['arm']}.json").read_text(encoding='utf-8')) for a in manifest['attempts']]
    public={'description':'虚构人物，原始数据库的隔离副本。技术人员按创作稿模拟记录者修订；不是真人听读确认。',
        'corrections':replay['corrections'],'checks':{k:replay[k] for k in ['original_transcripts_preserved','original_asr_preserved','old_error_absent','unrelated_fact_preserved']},
        'answers':answers,'extraction_comparison':comparisons,
        'limits':['未部署ECS或更新APK','ASR错词仍需核对；没有自动猜词','校准、搜索及引用的确定性检查不等于语义全面正确',
                  '旧修订缺少原始定位时仍保守停用整段','本轮模型样例少，不能当准确率或速度结论']}
    (OUT/'results.json').write_text(json.dumps(public,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda value:html.escape(str(value))
    fixes=''.join(f'<article><span class="tag">修订 {i}</span><div class="pair"><div><b>原记忆</b><p>{esc(c["before"])}</p></div><div><b>修订后</b><p>{esc(c["after"])}</p></div></div></article>' for i,c in enumerate(replay['corrections'],1))
    questions=[]
    for question in dict.fromkeys(a['question'] for a in answers):
        cols=[]
        for stage,label in [('before','修订前'),('after','修订后')]:
            a=next(a for a in answers if a['question']==question and a['stage']==stage)
            answer=a.get('output',{}).get('answer','本次失败：'+a.get('error_type','unknown'))
            cols.append(f'<div><b>{label}</b><p class="answer">{esc(answer)}</p></div>')
        questions.append(f'<article><h3>{esc(question)}</h3><div class="pair">{"".join(cols)}</div></article>')
    cases=[]
    for case in manifest['cases']:
        cells=[]
        for arm,label in [('baseline','原版 v4'),('candidate','新版 v5')]:
            r=next(c for c in comparisons if c['case_id']==case['id'] and c['arm']==arm)
            items=''.join(f'<li>{esc(m["content"])}</li>' for m in r.get('output',{}).get('memory_items',[]))
            cells.append(f'<div><b>{label}</b><ol>{items}</ol>{esc(r.get("error_type", ""))}</div>')
        cases.append(f'<details><summary>{esc(case["id"])} · {"历史实际转写" if case["id"].startswith("A01") else "新增虚构边界案例"}</summary><p>{esc(case["text"])}</p><div class="pair">{"".join(cells)}</div></details>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>勿忘我 · 记忆修订实跑</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f3f3eb;color:#223e35;font:17px/1.8 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1080px;margin:auto;padding:45px 24px 80px}h1{font-size:36px;line-height:1.4}h2{margin-top:48px}h3{font-size:19px}p{margin:.6em 0}article,details{background:#fffef8;border:1px solid #dfe4d8;border-radius:18px;padding:24px;margin:15px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:28px}.pair>div:first-child{color:#70685f}.tag{color:#6d806b;font-size:15px}.answer{white-space:pre-wrap}summary{cursor:pointer;font-weight:650}nav{display:flex;gap:24px;flex-wrap:wrap}a{color:#31634e}aside{border-left:4px solid #8ba08b;padding:10px 18px;background:#e8eddf}li{margin-bottom:10px}@media(max-width:680px){.pair{grid-template-columns:1fr}main{padding:25px 18px}h1{font-size:29px}}
    </style><main><span class="tag">勿忘我 / 本地实跑 / 2026.10.15</span><h1>改一处记忆，后续回答一起变</h1>
    <p>这轮修的是错误的来源、提取边界，以及纠正后继续使用旧说法的问题。</p>
    <nav><a href="#fix">六处修订</a><a href="#qa">同题前后回答</a><a href="#extract">原版与新版提取</a><a href="results.json">完整结果 JSON</a></nav>
    <aside>使用陈国梁虚构样例的隔离副本。六处修订按创作稿对照，由测试程序模拟记录者提交；没有冒充重新识别或真人听读核对。本页是结果报告，不是手机界面。</aside>
    <h2 id="fix">六处修订如何改变材料</h2><p>通过现有修订接口保存，原音与原始转写保留。修订后的当前材料不再包含这六类旧错词或错误判断，机械厂、广州等无关内容仍可使用。</p>'''+fixes+'''
    <h2 id="qa">同一模型、同一提示词、同一问题</h2><p>仅改变材料。原始模型输出照录；其中“本人书面说明”是现有接口对修订来源的显示名称，本实验对应的是模拟记录者修订。</p>'''+''.join(questions)+'''
    <h2 id="extract">提取方式的进步与局限</h2><p>新版保留画笔案例中的“可能、说不清”，可保存多个来源及主体、时间、否定、条件等原文短语。但实际样例仍常选择单个来源，不能声称已解决全部跨句归纳；ASR 错词仍需修订。</p>'''+''.join(cases)+'''
    <h2>这次如何判定</h2><p>合理改写不因用词不同判错；明确说过的经历、人物归属、否定、条件和不确定性必须保留。无依据的确定动机或责任判断属于错误；正确地说“不确定”可以通过。超时或结构失败单独记为失败，不算正确拒答。</p>
    <p>这批结果证明局部改进和修订传播。未部署到 ECS，未更新 APK，未完成真人听读或大样本准确率验收。</p></main></html>'''
    (OUT/'index.html').write_text(page,encoding='utf-8')
    print(OUT/'index.html')


if __name__=='__main__':main()

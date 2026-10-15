"""Export actual local outcomes and explicit, separate evidence reviews."""
import json
import html
from pathlib import Path
from collections import Counter
import httpx
from ingest import BASE, VAR, STATE, request, save
from runtime import ROOT


REVIEWS = {
    'Q01': ('partial','原话有师傅先找毛病和处事总结，但漏掉松动螺丝这个关键结果，未完整解释为什么学会先找原因。'),
    'Q02': ('failed','两次模型选段输出均未通过 SourceSelection 结构校验；未交付答案。不能算未知或正确拒答。'),
    'Q03': ('pass','与老杜互相调侃、与孩子怕说重了的差别都有原文支持。'),
    'Q04': ('pass','保留说不清、可能，以及给孩子买不同的原话，没有确定化补偿动机。'),
    'Q05': ('pass','忙可不回与仍然想念同时保留，没有把其中一面概括成全部。'),
    'Q06': ('pass','具体星期几未知；没有因存在不知道的原话而冒充日期已知。'),
    'Q07': ('pass','舍不得家与也可能胆子小并列，没有擅定唯一原因。'),
    'Q08': ('partial','UNKNOWN没有虚构医疗授权，但用户界面仍应明确区分没有记录到授权和系统不能替本人决策。'),
    'U01': ('pass','准确出生年未知，没有读取文稿真值中的1950。'),
    'U02': ('pass','精确确诊年未知，没有把模糊前两年或文稿真值2024当确定年份。'),
    'A01': ('partial','引用保留后来她跟我说的转述链，但没有直接解释这是讲述者转述，且漏掉仅相识时间不能证明评价发生在第一次见面当时。'),
    'N01': ('pass','UNKNOWN没有将指责升级为妻子确实动过物品，也没有反向判定妻子肯定没动。'),
}


def esc(value):
    return html.escape(str(value), quote=True)


def main():
    state = json.loads(STATE.read_text(encoding='utf8'))
    accounts = json.loads((VAR/'private/local-accounts.json').read_text(encoding='utf8'))
    root = '/api/v1/workbench/subjects/' + state['subject_id']
    runtime = VAR/'runtime'
    with httpx.Client(base_url=BASE, headers={'Origin': BASE}, trust_env=False, timeout=30) as c:
        request(c, 'POST', '/api/v1/accounts/login', json={k:accounts['owner'][k] for k in ('username','password')})
        narrative = request(c, 'GET', root+'/narrative')
        profiles = request(c, 'GET', root+'/profile-candidates')
        stories = request(c, 'GET', root+'/stories')['items']
    qa = json.loads((runtime/'final-questions.json').read_text(encoding='utf8'))
    for item in qa['items']:
        status, reason = REVIEWS[item['id']]
        item['semantic_review'] = {'status': status, 'reason': reason,
            'reviewer': 'Codex separate text evidence review; not model self-score or human-person endorsement'}
    save(runtime/'final-questions.json',qa)
    loops = json.loads((runtime/'loop-check.json').read_text(encoding='utf8'))
    for item in loops['qa']:
        item['semantic_review'] = 'pass: quote preserves uncertainty' if item['index']==0 else 'pass: insufficient authorized evidence, UNKNOWN'
    save(runtime/'loop-check.json',loops)
    save(runtime/'latest-person.json',narrative)
    summary = {'fictional':True,'scope':'local_web_actual_ASR_pipeline_not_Android_or_ECS_deployment',
        'input_episodes':len(state['episodes']), 'ready_episodes':sum(e['status']=='ready' for e in state['episodes'].values()),
        'persisted_memories':sum(len(s.get('memories',[])) for s in stories),
        'narrative_items':len(narrative['records']), 'narrative_confirmed':sum(r['status']=='confirmed' for r in narrative['records']),
        'profiles':dict(Counter(r['status'] for r in profiles['items'])),
        'qa':dict(Counter(r['semantic_review']['status'] for r in qa['items'])),
        'api_delivered':sum(r['status']=='delivered' for r in qa['items']),
        'snapshot_revoke_rounds':len(loops['snapshot_checks']),
        'asr_edited':False,'human_audio_listening':False,'real_subject_endorsement':False}
    save(runtime/'summary.json',summary)
    output = ROOT/'evaluations/a01-20261012/local-results.html'
    snippets=[]
    by_id={r['id']:r for r in narrative['records']}
    for view in narrative['views']:
        cards=[]
        for rid in view['records']:
            r=by_id[rid]
            evidence=''.join('<blockquote>'+esc(e['excerpt'])+'</blockquote>' for e in r.get('evidence',[]))
            cards.append('<article><h3>'+esc(r['title'])+'</h3><p>'+esc(r['text'])+'</p><details><summary>展开实际转写依据</summary>'+evidence+'</details></article>')
        snippets.append('<section><h2>'+esc(view['title'])+'</h2><div class="grid">'+''.join(cards)+'</div></section>')
    question_rows=[]
    for r in qa['items']:
        response=r.get('response',{})
        answer=response.get('answer',response.get('error_message','没有交付答案'))
        question_rows.append('<details class="qa"><summary><b>'+esc(r['id'])+'</b> '+esc(r['question'])+' <span>'+{'pass':'通过','partial':'部分满足','failed':'未交付'}[r['semantic_review']['status']]+'</span></summary><p class="answer">'+esc(answer)+'</p><p>'+esc(r['semantic_review']['reason'])+'</p></details>')
    conditional = next(r for r in profiles['items'] if r['status']=='confirmed')
    support=[];counter=[]
    for e in conditional['evidence']:
        (counter if e['evidence_id'] in conditional['counter_evidence_ids'] else support).append('<blockquote>'+esc(e['excerpt'])+'</blockquote>')
    output.write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>陈国梁 A01 · 本地实跑结果</title><style>
body{margin:0;background:#f5f3e9;color:#233e34;font:17px/1.75 system-ui,"Microsoft Yahei",sans-serif}main{max-width:1080px;margin:auto;padding:40px 24px}h1{font-size:clamp(26px,4vw,40px);line-height:1.3}h2{font-size:26px;margin-top:46px}h3{font-size:20px;line-height:1.4}a{color:#315e4a}header{padding:30px;border-radius:24px;background:#e5ebdb}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}article,.panel,.qa{border:1px solid #d3d8c7;background:#fffdf7;padding:24px;border-radius:20px}.metrics{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.metrics div{background:#fffdf7;border-radius:14px;padding:12px 22px}.metrics b{font-size:28px;display:block}blockquote{margin:16px 0;padding-left:15px;border-left:3px solid #91ab81;color:#415a4d}summary{cursor:pointer}small,.sub{color:#627367}.qa{margin:12px 0}.qa span{float:right}.answer{white-space:pre-wrap}img{width:100%;max-width:550px;border-radius:18px}table{width:100%;border-collapse:collapse}td,th{text-align:left;border-bottom:1px solid #d3d8c7;padding:12px}nav{display:flex;gap:18px;flex-wrap:wrap}audio{max-width:100%}
</style><main><header><div class="sub">勿忘我 · 2026-10-12 · 虚构样例 / 本地实跑</div><h1>一个人的故事，开始有了条件与例外。</h1><p>这是新文稿经过真实音频、转写和模型处理后的结果快照。原稿真值与答案没有送入模型；原始转写没有用原稿替换。</p><nav><a href="http://127.0.0.1:8891/workbench/companion.html">打开可操作人物页</a><a href="results.html">原文字基线与失败</a><a href="asr-v1/comparison.html">原稿与真实ASR对照</a></nav></header>
<div class="metrics"><div><b>10 / 10</b>新音频入库</div><div><b>'''+str(summary['persisted_memories'])+'''</b>实际持久化记忆</div><div><b>14</b>复核后的整理记录</div><div><b>1 + 5</b>技术确认理解 / 待核对</div></div>
<p>14条整理记录包括故事、人物、原话和观察，并非14个独立事件；12条来自模型再经技术复核，2条为从真实ASR逐字引用补建。确认仅用于虚构样例技术验收，未宣称真人认可。</p>
<section><h2>具体看见了什么：节俭，也愿意为孩子花钱</h2><div class="panel"><h3>'''+esc(conditional['statement'])+'''</h3><p>适用情境：'''+esc(conditional['context'])+'''</p><div class="grid"><div><h3>支持依据</h3>'''+''.join(support)+'''</div><div><h3>例外与保留的“可能”</h3>'''+''.join(counter)+'''</div></div></div><p>这项理解保留了2条支持和2条例外，不能压成“他什么都舍不得买”。其余5项仍待审，另1项“错怪桂芳”被拒绝。</p></section>
<section><h2>已经能亲手操作的新流程</h2><table><tr><th>能力</th><th>实际结果</th></tr><tr><td>亲友署名补记</td><td>独立许可→提交→本人审核→指定分享→撤回；接受后仍保留亲友作者，不写入本人事实。</td></tr><tr><td>专属文字信</td><td>草稿不可见→明确收信账号→发送后可读→撤销后隐藏正文。</td></tr><tr><td>只读封存</td><td>明确选定故事和确认理解，保存只读版本；来源撤权后旧版本和原音均受限，重复3轮。</td></tr><tr><td>人物和原音</td><td>本人10段；亲友9段；第07私人录音及疾病问答对亲友不开放。</td></tr></table></section>
'''+''.join(snippets)+'''<section><h2>问答：完整12题，一次结果全部保留</h2><p>8题通过、3题部分满足、1题未交付。11次接口成功不等于11题正确。这里是实际ASR+本地应用API结果，不能与文字基线混算；同一开发集不代表普遍准确率。</p>'''+''.join(question_rows)+'''</section>
<section><h2>明天可验收的范围与仍需改进</h2><div class="panel"><p>本轮新增的是本地网页和共享后端能力；当前ECS和Android安装包没有自动升级。未做真人麦克风、人工听读、真人亲友认可或PostgreSQL运行验收。原音为本次小米合成，实际Paraformer识别。</p><p>名字“晓宁”仍被识别为“小宁”，部分她/他及物件词有误；原稿与ASR保留独立对照。模型会漏掉条件、互换主语或输出坏结构，新增审阅只能降低风险，不能替代本人核对。</p><p>队友RAG接口暂未提供，本轮只写了接口边界。大资料的跨批全局理解、受影响内容的完整增量更新、第三方资料参与问答和专属音频信仍需下一批实现。</p></div></section></main></html>''',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False))
    print('Local actual-result report written; no provider calls or deployment.')


if __name__=='__main__':
    main()

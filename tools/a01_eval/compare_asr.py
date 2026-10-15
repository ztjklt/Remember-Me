"""Offline script/ASR comparison; no provider call, no transcript correction."""
import difflib
import html
import json
import unicodedata
from tools.a01_eval.prepare import ROOT, DATA, save, digest

RUNTIME=ROOT/'services/backend/var/a01-20261012/evaluation/asr-paraformer-v1'
OUT=DATA/'asr-v1'

CHECKS={
 'A01_01': [('subject_name','陈国梁'),('wife_name','周桂芳'),('daughter_name','晓宁'),('son_name','小川'),('granddaughter_name','豆豆'),('hometown','襄阳')],
 'A01_02': [('not_motor_fault','不是电机坏'),('loose_screw','一颗小螺丝松了'),('self_reflection','不一定都是对的')],
 'A01_03': [('reported_wife_statement','她跟我说'),('honest_not_teacher','我说老实有什么好')],
 'A01_04': [('daughter_name','晓宁'),('initial_refusal','没答应'),('tentative_regret','可能做错了'),('not_distrust','不是不相信'),('not_choose_all_paths','不能替')],
 'A01_05': [('son_name','小川'),('friend_name','老杜'),('not_scolding','没骂他'),('wishes_longer_call','还想再听两句'),('gentle_to_children','跟孩子怕说重了'),('casual_to_friend','不用客气')],
 'A01_06': [('granddaughter_name','豆豆'),('wife_name','桂芳'),('daughter_name','晓宁'),('reject_waste','不喜欢浪费'),('unclear_cause','说不清'),('possible_cause','可能是想起'),('irrecoverable_loss','补不回来')],
 'A01_07': [('wife_name','桂芳'),('diagnosis_spelling','阿尔茨海默病'),('accusation_not_objective_proof','说她动我东西'),('fear_family_recognition','怕哪一天认不出家里人'),('denied_need_but_reassurance','嘴上说不用')],
 'A01_08': [('wife_name','桂芳'),('not_directed_at_wife','不是冲你'),('self_anxiety','自己着急'),('blue_enamel_cup','蓝色搪瓷杯'),('rest_wish','该歇就歇'),('dont_discard','别扔')],
 'A01_09': [('daughter_name','晓宁'),('son_name','小川'),('busy_no_need_return','不回来也没关系'),('still_misses','还是会想'),('picture_not_removed','没摘下来过'),('radio_repaired','修好了')],
 'A01_10': [('weekday_unknown','星期几我真不知道'),('possible_alternative_cause','也可能是我自己胆子小'),('not_invent_words','别替我编'),('fallible_self_image','也会犯错'),('granddaughter_name','豆豆')]
}

def normalize(text):
    return ''.join(c for c in text if not unicodedata.category(c).startswith(('P','Z')) and not c.isspace())

def distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]

def main():
    episodes=json.loads((DATA/'input/episodes.json').read_text(encoding='utf-8'))
    records=[]
    for ep in episodes:
        raw=json.loads((RUNTIME/(ep['id']+'.raw-asr.json')).read_text(encoding='utf-8'))
        if digest(raw['text'].encode())!=raw['transcript_sha256']:raise ValueError('Raw ASR changed')
        script,asr=normalize(ep['text']),normalize(raw['text'])
        checks=[{'id':name,'expected_script_phrase':phrase,'preserved_exactly':normalize(phrase) in asr}
                for name,phrase in CHECKS[ep['id']]]
        diff=[{'operation':tag,'script_span':[a,b],'asr_span':[c,d],
               'script_text':script[a:b],'asr_text':asr[c:d]}
              for tag,a,b,c,d in difflib.SequenceMatcher(a=script,b=asr,autojunk=False).get_opcodes() if tag!='equal']
        records.append({'episode_id':ep['id'],'script_sha256':ep['sha256'],'audio_sha256':raw['audio_sha256'],
            'raw_asr_sha256':raw['transcript_sha256'],'script_text':ep['text'],'raw_asr_text':raw['text'],
            'source_type':'fresh_synthetic_audio_real_Paraformer_ASR','model_version':raw['model_version'],
            'metadata':raw['metadata'],'script_characters_without_punctuation':len(script),
            'asr_characters_without_punctuation':len(asr),'script_asr_edit_distance':distance(script,asr),
            'diff':diff,'key_phrase_checks':checks,'manual_listening':'pending',
            'review_status':'raw_machine_output_not_corrected'})
    calls=[json.loads(line) for line in (RUNTIME/'adapter-state/calls.jsonl').read_text(encoding='utf-8').splitlines()]
    summary={'actual_ASR_tasks':len(records),'adapter_invocations':len(calls),
        'successful_raw_transcripts':sum(c['validation']=='transcript_received_unreviewed' for c in calls),
        'input_audio_seconds':556.0,'provider_usage_seconds':sum(c.get('usage',{}).get('duration',0) for c in calls),
        'script_characters_without_punctuation':sum(r['script_characters_without_punctuation'] for r in records),
        'script_asr_edit_distance':sum(r['script_asr_edit_distance'] for r in records),
        'key_phrase_checks':sum(len(r['key_phrase_checks']) for r in records),
        'exactly_preserved_key_phrases':sum(c['preserved_exactly'] for r in records for c in r['key_phrase_checks'])}
    summary['script_asr_difference_ratio']=summary['script_asr_edit_distance']/summary['script_characters_without_punctuation']
    findings=[
      '晓宁在01/04/06/09机器稿均成“小宁”；不能凭同音自动合并，需单独核对后留痕。',
      '03多个“她”变“他”，04女儿指代也发生他/她差异；原文本可显示上下文，不能把错字当新人身份事实。',
      '02电机→电击，认死理→认私理；“不是”否定词仍在，但对象拼写改变。',
      '03老实→老师（后两句），08清福→轻浮、歇→谢、杯→被；部分错字能改变意思。',
      '07动我东西→冻我东西；阿尔茨海默病→阿尔斯海默病，不能作为医学新结论。',
      '贵画笔“说不清/可能”、孩子忙可不回与想念、星期几真不知道、不替编话均保留。',
      '数字正规化（如七六年→76年）会计入这里的编辑距离；该比例不等于ASR准确率。',
      '未人工听读合成原音，差异可能来自TTS、ASR或排版正规化；不能单凭创作稿确定实际说了哪些音。']
    output={'schema':'a01-asr-comparison-v1','fiction':True,'summary':summary,'episodes':records,
        'findings':findings,'transcripts_corrected':False,'text_baseline_overwritten':False,
        'downstream_model_retests':0,'manual_listening':'pending',
        'configuration_provenance':'Existing ECS Paraformer settings copied by parent to ACL-protected ignored local file; no ECS modifications.',
        'call_policy':'Existing backend ParaformerSttProvider, private temporary OSS, one fresh probe then nine serial; script/gold never supplied to ASR.'}
    save(OUT/'results.json',output)
    style='body{font:16px/1.6 system-ui;max-width:1150px;margin:auto;padding:30px;background:#f8faf7;color:#26392b}details{padding:18px;background:white;border:1px solid #ccdacc;border-radius:10px;margin:16px 0}summary{cursor:pointer;font-weight:600}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}.warn{color:#a53c25}@media(max-width:700px){.pair{display:block}}'
    blocks=['<!doctype html><meta charset="utf-8"><title>A01 新音真实ASR对照</title><style>'+style+'</style>',
        '<h1>A01 新合成音与真实 Paraformer 转写</h1><p>虚构语料 · 原始机器稿完整保留 · 不是真人录音 · 未人工听读 · 未覆盖文字基线</p>',
        '<pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
        '<pre class="warn">'+html.escape('\n'.join(findings))+'</pre>']
    for row in records:
        blocks.extend(['<details open><summary>'+row['episode_id']+'</summary><div class="pair"><section><h3>创作稿（对照用）</h3><p>'+html.escape(row['script_text'])+'</p></section><section><h3>原始机器稿（未纠正）</h3><p>'+html.escape(row['raw_asr_text'])+'</p></section></div>',
            '<audio controls src="'+(ROOT/'services/backend/var/a01-20261012/evaluation/speech'/f"{row['episode_id']}.wav").as_uri()+'"></audio>',
            '<pre>'+html.escape(json.dumps({'key_phrase_checks':row['key_phrase_checks'],'diff':row['diff']},ensure_ascii=False,indent=2))+'</pre></details>'])
    (OUT/'comparison.html').write_text('\n'.join(blocks),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

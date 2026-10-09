"""Explicit assistant review of fictional ASR-derived drafts, never a human study.

Every chosen statement was compared to its displayed sources; other drafts stay
pending. No gold text is sent to the model or used to replace ASR. Only a copied
evaluation DB at 127.0.0.1:8890 is changed. Preserves rejected model outputs.
"""
import json
import httpx
from live_check import AUTH,OUT,save

DECISIONS={
 'bus_driver':{
  'nr_88ba05d428df4ef1933f':('confirm','支持工作证和心情；标题缩小到所引内容。'),
  'nr_85b89324339f429f854e':('confirm','保留女儿独立理解的明确表达，不推亲密度。'),
  'nr_4e0eae7b03cc494380d1':('confirm','否定、口味和非医疗建议均有原文。'),
  'nr_737e0aa3e9c344b98cb7':('confirm','明确纠正1987年，未删除其余往事。'),
  'nr_7867da76e1b94e14b486':('reject','ASR事故肯定句与相邻材料的否定冲突；不得用逐字引用冒充事实核实。'),
  'nr_73eec92dfcc34d14910b':('reject','未交代这是后来纠正前的旧叙述，容易把尚未核实当作当前状态。'),
 },
 'firefighter':{
  'nr_039865d4201b4cb2bef5':('confirm','同一通电话与未讲出的内容分清，未编事故。'),
  'nr_97c157e56c38459fbfe6':('confirm','首次值班2018年且月日未知。'),
  'nr_0fd9a31e9bd1430b91f9':('confirm','母亲姓名与电话来源相符。'),
  'nr_ce29259d240c4e66ad8c':('confirm','静音只限定听唱片，不扩展为每次或拒绝家人。'),
  'nr_58f65211c4384982b968':('reject','自我定位不是被提及人物实体；材料不足以成立稳定身份标签。'),
 },
 'life_review':{
  'nr_341df04e72234f54ad6e':('confirm','同一次开张复述有明确说明，不当作两件事。'),
  'nr_12f6937a3c4a47c3bfd4':('confirm','开张2009年、筹备日期未知。'),
  'nr_9d10403cc78a4e0ead36':('confirm','问题不是答案，保留尚待回答时点。'),
  'nr_3df965f2047f4258a7de':('confirm','未留下最后的话，不编告别。'),
  'nr_1122bfbddb26489dbcf3':('reject','末句不把病情当解释没有被本条引用来源支持。'),
 }
}

def main():
 report_path=OUT/'technical-review.json';report=json.loads(report_path.read_text(encoding='utf8')) if report_path.exists() else {'reviewer':'assistant','fictional_only':True,'human_listening':False,'decisions':{}}
 for pid,pair in json.loads(AUTH.read_text(encoding='utf8')).items():
  owner=pair['owner'];root='/api/v1/workbench/subjects/'+owner['subject_id']+'/narrative'
  def call(method,path,**kw):
   r=httpx.request(method,'http://127.0.0.1:8890'+path,headers={'Authorization':'Bearer '+owner['actor_token']},trust_env=False,timeout=120,**kw)
   if not r.is_success:raise RuntimeError(f'HTTP {r.status_code}')
   return r.json()
  data=call('GET',root);rows={r['id']:r for r in data['records']}
  for id,(action,reason) in DECISIONS[pid].items():
   if id in report['decisions']:continue
   row=rows[id]
   if id=='nr_88ba05d428df4ef1933f':
    fields=['kind','title','text','evidence_ids','facets','time_text','place_text','aliases','same_event','recipient_label']
    body={k:row[k] for k in fields};body.update(title='工作证与安稳过完一天',revision=row['revision'])
    row=call('PUT',root+'/records/'+id,json=body)
   result=call('POST',root+'/records/'+id+'/'+action,json={'revision':row['revision']})
   report['decisions'][id]={'person':pid,'action':action,'reason':reason,'revision':result['revision'],'sources':row['evidence_ids']};save(report_path,report)
  save(OUT/(pid+'-reviewed-narrative.json'),call('GET',root))
 print('Explicit fictional technical review saved; unreviewed drafts stay pending.')

if __name__=='__main__':main()

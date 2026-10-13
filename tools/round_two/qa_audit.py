"""Offline audit of a frozen real run; reference answers NEVER go to a model.

Missing semantic decisions remain pending. HTTP success is not a passing grade.
"""
import argparse,csv,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'services/backend/var/round-two'


def main():
    p=argparse.ArgumentParser();p.add_argument('run');args=p.parse_args()
    if not args.run.replace('-','').isalnum():raise SystemExit('Invalid run label')
    source=OUT/f'qa-{args.run}.json';run=json.loads(source.read_text(encoding='utf8'))
    decisions_path=OUT/f'review-{args.run}.json'
    decisions=json.loads(decisions_path.read_text(encoding='utf8')) if decisions_path.exists() else {}
    rows=[]
    for person in ('bus_driver','firefighter','life_review'):
        gold=json.loads((ROOT/f'evaluations/monthly-integration-v1/gold/{person}.json').read_text(encoding='utf8'))
        for case in gold['qa']:
            actual=run.get('people',{}).get(person,{}).get(case['id'],{})
            response=actual.get('response',{});decision=decisions.get(case['id'],{})
            status=decision.get('verdict','pending' if response else 'failed' if actual.get('error') else 'not_run')
            if status=='pass' and not response:raise ValueError('Cannot pass an absent/failed response')
            rows.append({'case':case['id'],'role':case['role'],'question':case['question'],
                'expected':json.dumps(case['expected_facts'],ensure_ascii=False),'expected_type':case['expected_response_type'],
                'answer':response.get('answer',''),'response_type':response.get('response_type',''),
                'sources':json.dumps(response.get('evidence',[]),ensure_ascii=False),'error':actual.get('error',''),
                'verdict':status,'critical':decision.get('critical',False),'note':decision.get('note',''),
                'reviewer':'assistant source-based technical reading; not human listening or user study'})
    with (OUT/f'audit-{args.run}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    counts={name:sum(r['verdict']==name for r in rows) for name in ['pass','failed','pending','not_run']}
    summary={'run':args.run,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'total':len(rows),
        'completed_run':bool(run.get('finished')),'returned':sum(bool(r['answer']) for r in rows),**counts,
        'critical_failures':sum(bool(r['critical']) for r in rows),'human_listening':False,'new_asr':False}
    summary['gate_passed']=summary['completed_run'] and counts['pass']>=54 and counts['pending']==0 and counts['not_run']==0 and summary['critical_failures']==0
    (OUT/f'audit-{args.run}.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()

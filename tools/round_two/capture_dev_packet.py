"""Capture only a named fictional development case through actual backend scope code.

No provider call, no gold answers, no production DB. Isolated SQLite copy.
"""
import argparse,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'services/backend/var/paired-delivery'


def main():
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--dataset',choices=['legacy','cloud-monthly'],default='legacy');args=p.parse_args()
    pid=args.case.rsplit('-q',1)[0]
    if pid not in {'bus_driver','firefighter','life_review'}:raise SystemExit('Named synthetic development corpus only')
    gold=json.loads((ROOT/'evaluations/monthly-integration-v1/gold'/f'{pid}.json').read_text(encoding='utf8'))
    case=next(c for c in gold['qa'] if c['id']==args.case)
    dataset=ROOT/'services/backend/var/monthly-eval'
    if args.dataset=='cloud-monthly':dataset=dataset/'cloud-asr-runs/relay-compact'
    identities=json.loads((dataset/'identities.json').read_text(encoding='utf8'))[pid]
    who=identities[case['role']];subject=identities['owner']['subject_id']
    OUT.mkdir(exist_ok=True)
    target=OUT/'diagnostic.db'
    if not target.exists():
        with sqlite3.connect(f'file:{(ROOT/"services/backend/var/round-two/acceptance.db").as_posix()}?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:src.backup(dst)
    sys.path.insert(0,str(ROOT/'services/backend'))
    from app.config import Settings
    from app.main import create_app
    from app.twin_client import TwinUnavailable
    from fastapi.testclient import TestClient
    from alembic import command
    from alembic.config import Config
    cfg=Config(str(ROOT/'services/backend/alembic.ini'));cfg.set_main_option('script_location',str(ROOT/'services/backend/migrations'))
    cfg.set_main_option('sqlalchemy.url','sqlite:///'+target.as_posix());command.upgrade(cfg,'head')
    app=create_app(Settings(_env_file=None,environment='test',database_url='sqlite:///'+target.as_posix(),object_store_backend='memory',ai_backend='http',log_level='ERROR'))
    class Capture:
        def answer(self,question,candidates):
            suffix='-cloud' if args.dataset=='cloud-monthly' else ''
            target=OUT/(args.case+suffix+'-packet.json')
            if target.exists():raise RuntimeError('Captured packet already exists; preserve it')
            target.write_text(json.dumps({'question':question,'candidates':candidates},ensure_ascii=False,indent=2),encoding='utf8')
            raise TwinUnavailable('Packet captured; no model called')
    app.state.twin_client=Capture()
    with TestClient(app) as client:
        h={'Authorization':'Bearer '+who['actor_token']}
        if case['role']=='owner':
            rows=client.get('/api/v1/consents?subject_id='+subject,headers=h).json()
            consent=next(c['consent_id'] for c in rows if c['scope']=='CLOUD_TWIN' and c['status']=='granted')
        else:
            rows=client.get(f'/api/v1/workbench/subjects/{subject}/grants',headers=h).json()['items']
            consent=next(c['grant_id'] for c in rows if c['cloud_processing_allowed'])
        response=client.post(f'/api/v1/subjects/{subject}/twin/answers',headers=h,json={'question':case['question'],'cloud_consent_id':consent})
        if response.status_code!=503:raise SystemExit('Capture did not stop at expected boundary')
    print(args.case,'captured through authorized backend; no gold answers')


if __name__=='__main__':main()

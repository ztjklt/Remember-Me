"""Local UI test only: separate SQLite snapshot, explicit fictional owner mapping.
No provider calls or fabricated memories. Reuses previously processed audio.
"""
import json, os, secrets, sqlite3, subprocess, sys
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[2]; BACK=ROOT/'services/backend'
OUT=BACK/'var/paired-delivery'; OUT.mkdir(exist_ok=True)
db=OUT/'sharing-ui.db'; config=OUT/'sharing-ui.json'
env={**os.environ,**{k:v for k,v in dotenv_values(BACK/'.env').items() if v is not None}}
if env.get('REMEMBER_OBJECT_STORE_BACKEND','local')!='local':
    raise SystemExit('UI snapshot currently supports only a separately copied local object store')
from isolated_store import clone_local_store
source=Path(env.get('REMEMBER_OBJECT_STORE_ROOT','./var/object-store'))
if not source.is_absolute():source=BACK/source
isolated=clone_local_store(source,OUT/'sharing-ui-objects')
env.update(REMEMBER_OBJECT_STORE_BACKEND='local',REMEMBER_OBJECT_STORE_ROOT=str(isolated))
env.update(REMEMBER_DATABASE_URL='sqlite:///'+db.as_posix(),REMEMBER_ALLOW_ACCOUNT_REGISTRATION='false',
    REMEMBER_ENABLE_WORKBENCH='true',REMEMBER_AI_CORE_URL='http://127.0.0.1:8891',REMEMBER_RELEASE_ID='paired-ui-candidate')
if not db.exists():
    with sqlite3.connect(f'file:{(BACK/"var/round-two/acceptance.db").as_posix()}?mode=ro',uri=True) as src,sqlite3.connect(db) as dst:src.backup(dst)
os.environ.update(env);sys.path.insert(0,str(BACK))
subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=BACK,env=env,check=True,stdout=subprocess.DEVNULL)
from app.db import Database
from app.models import Subject,Episode
from app.account_admin import create_account
from app.access import altered_story_ids
from sqlalchemy import select
if not config.exists():
    identities=json.loads((BACK/'var/monthly-eval/identities.json').read_text('utf8'))
    subject=identities['bus_driver']['owner']['subject_id']
    database=Database(env['REMEMBER_DATABASE_URL'])
    with database.session() as session:
        owner_password=secrets.token_urlsafe(18);reader_password=secrets.token_urlsafe(18)
        owner=create_account(session,'paired_ui_owner',owner_password,'演示记录者')
        reader=create_account(session,'paired_ui_reader',reader_password,'演示亲友')
        # Explicit mapping applies ONLY to this disposable fictional-data copy.
        session.get(Subject,subject).owner_actor_id=owner['actor_id']
        session.get(Subject,subject).display_name='演示故事空间'
        rows=list(session.scalars(select(Episode).where(Episode.subject_id==subject,Episode.status=='ready')))
        altered=altered_story_ids(session,{e.episode_id for e in rows})
        episode=next(e.episode_id for e in rows if e.episode_id not in altered and e.transcript_reviewed_at)
        session.commit()
        config.write_text(json.dumps({'url':'http://127.0.0.1:8892','subject':subject,'episode':episode,
            'owner':{**owner,'password':owner_password},'reader':{**reader,'password':reader_password}},ensure_ascii=False,indent=2),encoding='utf8')
    database.dispose()
print('UI test snapshot on port 8892; credentials written to ignored configuration only.',flush=True)
subprocess.run([sys.executable,'-m','uvicorn','app.main:app','--port','8892','--no-access-log'],cwd=BACK,env=env,check=True)

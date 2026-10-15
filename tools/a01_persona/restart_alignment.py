"""Back up and migrate only the existing local A01 runtime; no ECS access."""
from pathlib import Path
import hashlib,json,os,sqlite3,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.a01_local.runtime import ROOT,BACKEND,VAR,configuration,start,stop
from tools.a01_persona.live_acceptance import save


def main():
    database=VAR/'runtime/remember.db'
    target=VAR/'runtime/backups/before-persona-0021.db'
    trial=VAR/'runtime/backups/trial-persona-0021.db'
    report=VAR/'twin-alignment-live-20261012/migration.json'
    if report.exists():raise SystemExit('Migration checkpoint exists; inspect it before another restart')
    def counts(path):
        with sqlite3.connect(path) as c:
            return {t:c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in
                ['episodes','memory_items','evidence','twin_answers','persona_answer_contexts','companion_audio']}
    with sqlite3.connect(database) as src:
        if src.execute("SELECT count(*) FROM jobs WHERE state!='succeeded'").fetchone()[0]:
            raise SystemExit('Unfinished audio jobs; do not interrupt')
        if src.execute("SELECT count(*) FROM profile_refreshes WHERE status!='complete'").fetchone()[0]:
            raise SystemExit('Unfinished profile jobs; do not interrupt')
        if target.exists():raise SystemExit('Backup already exists; inspect it')
        target.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(target) as dst:src.backup(dst)
    before=counts(target)
    with sqlite3.connect(target) as src,sqlite3.connect(trial) as dst:src.backup(dst)
    env=configuration();env['REMEMBER_DATABASE_URL']='sqlite:///'+trial.as_posix()
    logs=VAR/'twin-alignment-live-20261012/migration-trial.log'
    with logs.open('w',encoding='utf8') as log:
        result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=BACKEND,env=env,stdout=log,stderr=log)
    if result.returncode:raise SystemExit('Copy migration failed; live runtime untouched')
    with sqlite3.connect(trial) as c:
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert c.execute('select version_num from alembic_version').fetchone()[0]=='0021_twin_review_summary'
        assert c.execute("select count(*) from persona_answer_contexts where review_summary!='{}'").fetchone()[0]==0
    assert counts(trial)==before
    save(report,{'status':'copy_verified','backup_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'before_counts':before,'copy_counts':counts(trial),'copy_integrity':'ok','backup':str(target)})
    stop()
    os.environ['AI_PERSONA_FICTIONAL_DEBUG_TRACE']='1'
    start()
    with sqlite3.connect(database) as c:
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        version=c.execute('select version_num from alembic_version').fetchone()[0]
    save(report,{'status':'local_upgraded','migration':version,'backup':str(target),
        'backup_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'before_counts':before,'after_counts':counts(database),'integrity':'ok'})
    print('Local A01 migrated with preserved row counts; fictional trace explicitly enabled.')


if __name__=='__main__':main()

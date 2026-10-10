"""ECS-only isolated candidate runtime. Never switches current or copies user DB.

Creates a new empty test database, private object/ASR state, and ordinary accounts.
Provider keys are read from existing root-only config and stay on the server.
"""
import argparse,json,os,re,secrets,subprocess,sys,time
from pathlib import Path


def staging_names(commit):
    if not re.fullmatch('[0-9a-f]{7,40}',commit):raise ValueError('Expected a commit identifier')
    return {'database':'remember_stage_'+commit+'_test',
        'root':'/var/lib/remember-me/paired-stage-'+commit,
        'units':['remember-paired-stage-'+commit+'-'+n for n in ('ai','api','worker','profile')]}


def check_units(units):
    # systemctl with several names succeeds if ANY is active, not necessarily all.
    failed=[unit for unit in units if subprocess.run(
        ['systemctl','is-active','--quiet',unit],check=False).returncode!=0]
    if failed:raise RuntimeError('Inactive candidate services: '+', '.join(failed))


def check_runtime(release):
    for component,module in [('backend','app.main'),('ai-core','app.main')]:
        subprocess.run([str(release/'services'/component/'.venv/bin/python'),
            '-c','import '+module],cwd=release/'services'/component,check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('commit');args=p.parse_args()
    plan=staging_names(args.commit)
    if os.geteuid()!=0:raise RuntimeError('Run only as ECS operator')
    release=Path('/opt/remember-me/releases')/('paired-'+args.commit)
    if release.resolve().parent!=Path('/opt/remember-me/releases') or not (release/'services/backend/app/api/sharing.py').is_file():
        raise RuntimeError('Candidate release missing or outside release directory')
    check_runtime(release)
    stage=Path(plan['root']);stage.mkdir(mode=0o700)
    before=str(Path('/opt/remember-me/current').resolve())
    command=lambda argv,**kw:subprocess.run(argv,check=True,**kw)
    command(['runuser','-u','postgres','--','createdb','-O','root',plan['database']])
    from dotenv import dotenv_values
    env={**os.environ,**{k:v for k,v in dotenv_values('/etc/remember-me/api.env').items() if v is not None}}
    common={'REMEMBER_DATABASE_URL':'postgresql+psycopg:///'+plan['database'],
        'REMEMBER_ENVIRONMENT':'test',
        'REMEMBER_OBJECT_STORE_BACKEND':'local','REMEMBER_OBJECT_STORE_ROOT':str(stage/'audio'),
        'REMEMBER_PARAFORMER_STATE_DIR':str(stage/'asr'),
        'REMEMBER_AI_CORE_URL':'http://127.0.0.1:8899','REMEMBER_AI_TIMEOUT_SECONDS':'120',
        'REMEMBER_API_PORT':'8880','REMEMBER_AI_PORT':'8899',
        'REMEMBER_ALLOW_ACCOUNT_REGISTRATION':'false','REMEMBER_RELEASE_ID':args.commit+'-stage'}
    env.update(common)
    with (stage/'migration.log').open('w') as log:
        command([str(release/'services/backend/.venv/bin/python'),'-m','alembic','upgrade','head'],
            cwd=release/'services/backend',env=env,stdout=log,stderr=log)
    sys.path.insert(0,str(release/'services/backend'))
    from app.db import Database
    from app.account_admin import create_account
    db=Database(common['REMEMBER_DATABASE_URL']);credentials={}
    try:
        with db.session() as session:
            for role in ('owner','reader'):
                password=secrets.token_urlsafe(24)
                credentials[role]={**create_account(session,'stage_'+role+'_'+args.commit,password,
                    '隔离验收记录者' if role=='owner' else '隔离验收亲友'),'password':password}
            target=stage/'accounts.json'
            with target.open('x') as f:os.chmod(target,0o600);json.dump(credentials,f,ensure_ascii=False)
            session.commit()
    finally:db.dispose()
    started=[]
    try:
        for name,unit in zip(('ai','api','worker','profile'),plan['units']):
            updates={**common}
            if name=='ai':updates.update(AI_TWIN_QUOTE_ANSWERS='true',AI_TWIN_STRUCTURED_ANSWERS='false',AI_MAX_CONCURRENT_REQUESTS='1')
            lines=[s for s in Path('/etc/remember-me',name+'.env').read_text().splitlines() if s.split('=',1)[0] not in updates]
            config=stage/(name+'.env')
            config.write_text('\n'.join(lines+[k+'='+v for k,v in updates.items()])+'\n');config.chmod(0o600)
            command(['systemd-run','--quiet','--collect','--unit='+unit,
                '--property=WorkingDirectory='+str(release),'--property=EnvironmentFile='+str(config),
                '--setenv=HF_HOME=/var/lib/remember-me/model-cache','--setenv=OMP_NUM_THREADS=2',
                '/bin/bash',str(release/'infra/aws/run-service.sh'),name])
            started.append(unit)
        time.sleep(3)
        check_units(started)
    except Exception:
        subprocess.run(['systemctl','stop',*started],check=False)
        raise
    assert str(Path('/opt/remember-me/current').resolve())==before
    plan.update(release=str(release),production_unchanged=before,api='http://127.0.0.1:8880')
    (stage/'runtime.json').write_text(json.dumps(plan,indent=2));print(json.dumps(plan))


if __name__=='__main__':main()

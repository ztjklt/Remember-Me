"""Root-only isolated ECS candidate. Never switches production or opens ports."""
import json,os,subprocess,sys,zipfile
from pathlib import Path

BASE=Path('/opt/remember-me')
candidate=BASE/'releases/paired-voice-20261014'
probe=BASE/'voice-probe-20261014'
stage=Path('/var/lib/remember-me/voice-stage-20261014')


def run(args,**kw): return subprocess.run(args,check=True,**kw)


assert os.geteuid()==0
assert candidate.parent==BASE/'releases'
assert not candidate.exists(), 'Candidate already exists; inspect before resuming'
candidate.mkdir(mode=0o755);stage.mkdir(mode=0o700,exist_ok=True)
run(['tar','-xf',str(probe/'source.tar'),'-C',str(candidate)])
for service in ['backend','ai-core']:
    old=(BASE/'current/services'/service/'.venv').resolve()
    target=candidate/'services'/service/'.venv'
    run([str(old/'bin/python'),'-m','venv','--without-pip',str(target)])
    site=Path(subprocess.check_output([str(target/'bin/python'),'-c','import site; print(site.getsitepackages()[0])'],text=True).strip())
    old_site=subprocess.check_output([str(old/'bin/python'),'-c','import site; print(site.getsitepackages()[0])'],text=True).strip()
    (site/'remember-existing-runtime.pth').write_text(old_site+'\n')
    if service=='backend':
        with zipfile.ZipFile(probe/'websockets-15.0.1-py3-none-any.whl') as wheel: wheel.extractall(site)
# Snapshot and verify restoration before any candidate requests.
backup=(candidate/'tools/round_two/backup_ecs_paired.sh').read_text()
result=run(['bash','-s','--',str(candidate)],input=backup,text=True,capture_output=True)
check=json.loads(result.stdout.strip().splitlines()[-1]);snapshot=Path(check['snapshot'])
restore=json.loads((snapshot/'restore-check.json').read_text())
assert restore['audio_hash_match']
from dotenv import dotenv_values
for name in ['ai','api']:
    env={k:v for k,v in dotenv_values('/etc/remember-me/'+name+'.env').items() if v is not None}
    env.update(REMEMBER_ENVIRONMENT='test',REMEMBER_RELEASE_ID='voice-20261014-stage')
    if name=='api':
        # Only already established fictional demonstration actors are enabled.
        from sqlalchemy import create_engine,text
        engine=create_engine('postgresql+psycopg:///'+restore['database'])
        with engine.connect() as connection:
            columns=[r[0] for r in connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='accounts'"))]
            # Resolve by existing public demo usernames; never write account rows.
            actors=[r[0] for r in connection.execute(text("SELECT actor_id FROM accounts WHERE username IN ('chensy08','chenly08')"))]
        assert actors, 'No demo accounts found'
        env.update(REMEMBER_DATABASE_URL='postgresql+psycopg:///'+restore['database'],
            REMEMBER_OBJECT_STORE_ROOT=str(snapshot/'restored-audio/audio'),
            REMEMBER_AI_CORE_URL='http://127.0.0.1:8896',REMEMBER_API_PORT='8895',
            REMEMBER_PARAFORMER_STATE_DIR=str(stage/'asr'),REMEMBER_ALLOW_ACCOUNT_REGISTRATION='false',
            REMEMBER_REALTIME_VOICE_ENABLED='true',REMEMBER_REALTIME_VOICE_ACTOR_IDS=json.dumps(actors),
            REMEMBER_AI_TIMEOUT_SECONDS='120')
    else: env.update(REMEMBER_AI_PORT='8896')
    file=stage/(name+'.env');file.write_text('\n'.join(k+'='+str(v) for k,v in env.items())+'\n');file.chmod(0o600)
    run(['systemd-run','--unit=remember-voice-stage-'+name+'-20261014','--collect',
        '-p','WorkingDirectory='+str(candidate),'-p','EnvironmentFile='+str(file),
        '-p','Environment=HF_HOME=/var/lib/remember-me/model-cache OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false',
        '/bin/bash',str(candidate/'infra/aws/run-service.sh'),name])
(stage/'stage.json').write_text(json.dumps(dict(candidate=str(candidate),snapshot=str(snapshot),database=restore['database'],
    restored_files=restore['restored_files'],production_switched=False),indent=2))
print(json.dumps(dict(candidate=str(candidate),api_port=8895,ai_port=8896,restored_files=restore['restored_files'],production_switched=False)))

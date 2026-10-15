"""Isolated API + restored database. Does not switch production or restart it."""
import json,os,shutil,subprocess
from pathlib import Path
from dotenv import dotenv_values

stage=Path('/var/lib/remember-me/step-integrated-20261015')
old=Path('/opt/remember-me/current').resolve()
release=Path('/opt/remember-me/releases/paired-step-realtime-20261015')
assert os.geteuid()==0 and not release.exists()
shutil.copytree(old,release,ignore=shutil.ignore_patterns('.venv','var','__pycache__','.pytest_cache'))
for service in ('backend','ai-core'):
    (release/'services'/service/'.venv').symlink_to(old/'services'/service/'.venv',target_is_directory=True)
subprocess.run(['tar','-xf',str(stage/'patch.tar'),'-C',str(release)],check=True)
backup=release/'tools/round_two/backup_ecs_paired.sh'
done=subprocess.run(['bash','-s','--',str(release)],input=backup.read_text(),text=True,capture_output=True,check=True)
snapshot=Path(json.loads(done.stdout.strip().splitlines()[-1])['snapshot'])
restore=json.loads((snapshot/'restore-check.json').read_text());assert restore['audio_hash_match']
env=dotenv_values('/etc/remember-me/api.env')
key=dotenv_values('/var/lib/remember-me/step-2603-20261015/private.env')['STEP_API_KEY']
env.update(REMEMBER_ENVIRONMENT='test',REMEMBER_RELEASE_ID=release.name,HF_HUB_OFFLINE='1',
    TRANSFORMERS_OFFLINE='1',HF_HOME='/var/lib/remember-me/model-cache',OMP_NUM_THREADS='2',TOKENIZERS_PARALLELISM='false',
    REMEMBER_DATABASE_URL='postgresql+psycopg:///'+restore['database'],
    REMEMBER_OBJECT_STORE_ROOT=str(snapshot/'restored-audio/audio'),REMEMBER_API_PORT='8897',
    REMEMBER_PARAFORMER_STATE_DIR=str(stage/'asr'),REMEMBER_STEP_REALTIME_ENABLED='true',
    REMEMBER_STEP_REALTIME_API_KEY=key,REMEMBER_REALTIME_VOICE_PREFETCH_ENABLED='false')
file=stage/'api.env';file.write_text('\n'.join(k+'='+str(v) for k,v in env.items() if v is not None)+'\n');file.chmod(0o600)
subprocess.run(['systemd-run','--unit=remember-step-stage-api-20261015','--collect',
    '-p','WorkingDirectory='+str(release),'-p','EnvironmentFile='+str(file),
    '/bin/bash',str(release/'infra/aws/run-service.sh'),'api'],check=True)
state=dict(candidate=str(release),previous=str(old),snapshot=str(snapshot),database=restore['database'],production_switched=False)
(stage/'stage.json').write_text(json.dumps(state,indent=2));print(json.dumps(state))

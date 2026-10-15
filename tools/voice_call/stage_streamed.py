"""ECS root: prepare an isolated fast-voice candidate and restore test database."""
import json, os, shutil, subprocess
from pathlib import Path
from dotenv import dotenv_values

base=Path('/opt/remember-me')
release=base/'releases/paired-voice-streamed-20261014'
stage=Path('/var/lib/remember-me/voice-streamed-20261014')
assert os.geteuid()==0 and not release.exists()
old=(base/'current').resolve()
shutil.copytree(old,release,ignore=shutil.ignore_patterns('.venv','var','__pycache__','.pytest_cache'))
for service in ('backend','ai-core'):
    (release/'services'/service/'.venv').symlink_to(old/'services'/service/'.venv',target_is_directory=True)
subprocess.run(['tar','-xf',str(stage/'patch.tar'),'-C',str(release)],check=True)
backup=release/'tools/round_two/backup_ecs_paired.sh'
done=subprocess.run(['bash','-s','--',str(release)],input=backup.read_text(),text=True,capture_output=True,check=True)
result=json.loads(done.stdout.strip().splitlines()[-1])
snapshot=Path(result['snapshot']);restore=json.loads((snapshot/'restore-check.json').read_text())
assert restore['audio_hash_match']
for name in ('api','ai'):
    env=dotenv_values('/etc/remember-me/'+name+'.env')
    env.update(REMEMBER_ENVIRONMENT='test',REMEMBER_RELEASE_ID=release.name,
               HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME='/var/lib/remember-me/model-cache',
               OMP_NUM_THREADS='2',TOKENIZERS_PARALLELISM='false')
    if name=='api':
        env.update(REMEMBER_DATABASE_URL='postgresql+psycopg:///'+restore['database'],
            REMEMBER_OBJECT_STORE_ROOT=str(snapshot/'restored-audio/audio'),
            REMEMBER_AI_CORE_URL='http://127.0.0.1:8896',REMEMBER_API_PORT='8895',
            REMEMBER_PARAFORMER_STATE_DIR=str(stage/'asr'),REMEMBER_REALTIME_VOICE_FAST_ENABLED='true',REMEMBER_REALTIME_VOICE_STREAMED_ENABLED='true')
    else:env.update(REMEMBER_AI_PORT='8896')
    file=stage/(name+'.env')
    file.write_text('\n'.join(k+'='+str(v) for k,v in env.items() if v is not None)+'\n');file.chmod(0o600)
    subprocess.run(['systemd-run','--unit=remember-streamed-stage-'+name+'-20261014','--collect',
        '-p','WorkingDirectory='+str(release),'-p','EnvironmentFile='+str(file),
        '/bin/bash',str(release/'infra/aws/run-service.sh'),name],check=True)
state=dict(candidate=str(release),previous=str(old),snapshot=str(snapshot),database=restore['database'],production_switched=False)
(stage/'stage.json').write_text(json.dumps(state,indent=2))
print(json.dumps(state))

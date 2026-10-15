"""Root-only candidate from current release; backup and isolate before cutover."""
import json, os, shutil, subprocess
from pathlib import Path
from dotenv import dotenv_values

stage=Path('/var/lib/remember-me/voice-stability-20261014')
old=Path('/opt/remember-me/current').resolve()
release=Path('/opt/remember-me/releases/paired-voice-stability-20261014')
assert os.geteuid()==0 and not release.exists()
shutil.copytree(old,release,ignore=shutil.ignore_patterns('.venv','var','__pycache__','.pytest_cache'))
for service in ('backend','ai-core'):
    (release/'services'/service/'.venv').symlink_to(old/'services'/service/'.venv',target_is_directory=True)
subprocess.run(['tar','-xf',str(stage/'patch.tar'),'-C',str(release)],check=True)
# Retain deployed prompt/data shape. Change only transport policy and validation hook.
quoted=release/'services/ai-core/app/quoted_twin.py'
s=quoted.read_text()
before='return self.chat.complete_stream(system,request,on_point=first_point)'
assert before in s
s=s.replace(before,"options={'validate_result':lambda raw,model:render_ids(raw,payload,model)} if getattr(self.chat,'supports_stream_validation',False) else {}\n                        return self.chat.complete_stream(system,request,on_point=first_point,**options)")
before='except (ProviderTimeout,ProviderUnavailable):'
assert before in s
s=s.replace(before,before+"\n                    if payload.voice_response and generation_streamed.get() and getattr(self.chat,'stream_retry_managed',False):raise")
quoted.write_text(s)
backup=release/'tools/round_two/backup_ecs_paired.sh'
done=subprocess.run(['bash','-s','--',str(release)],input=backup.read_text(),text=True,capture_output=True,check=True)
snapshot=Path(json.loads(done.stdout.strip().splitlines()[-1])['snapshot'])
restore=json.loads((snapshot/'restore-check.json').read_text());assert restore['audio_hash_match']
for name in ('api','ai'):
    env=dotenv_values('/etc/remember-me/'+name+'.env')
    env.update(REMEMBER_ENVIRONMENT='test',REMEMBER_RELEASE_ID=release.name,HF_HUB_OFFLINE='1',
        TRANSFORMERS_OFFLINE='1',HF_HOME='/var/lib/remember-me/model-cache',OMP_NUM_THREADS='2',TOKENIZERS_PARALLELISM='false')
    if name=='api':
        env.update(REMEMBER_DATABASE_URL='postgresql+psycopg:///'+restore['database'],
            REMEMBER_OBJECT_STORE_ROOT=str(snapshot/'restored-audio/audio'),REMEMBER_AI_CORE_URL='http://127.0.0.1:8896',
            REMEMBER_API_PORT='8895',REMEMBER_PARAFORMER_STATE_DIR=str(stage/'asr'))
    else:env.update(REMEMBER_AI_PORT='8896',AI_VOICE_RETRY_AFTER_SECONDS='3')
    file=stage/(name+'.env');file.write_text('\n'.join(k+'='+str(v) for k,v in env.items() if v is not None)+'\n');file.chmod(0o600)
    subprocess.run(['systemd-run','--unit=remember-stability-stage-'+name+'-20261014','--collect',
        '-p','WorkingDirectory='+str(release),'-p','EnvironmentFile='+str(file),
        '/bin/bash',str(release/'infra/aws/run-service.sh'),name],check=True)
state=dict(candidate=str(release),previous=str(old),snapshot=str(snapshot),database=restore['database'],production_switched=False)
(stage/'stage.json').write_text(json.dumps(state,indent=2));print(json.dumps(state))

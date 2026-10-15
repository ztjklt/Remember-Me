"""Bounded ECS candidate cutover. Preserve DB/audio/config and revert on failed readiness."""
import json, os, shutil, subprocess, time, urllib.request
from pathlib import Path

stage=Path('/var/lib/remember-me/voice-streamed-20261014')
state=json.loads((stage/'stage.json').read_text())
current=Path('/opt/remember-me/current');release=Path(state['candidate']);old=Path(state['previous'])
assert os.geteuid()==0 and current.resolve()==old and release.is_dir()
assert json.loads((Path(state['snapshot'])/'restore-check.json').read_text())['audio_hash_match']
config=Path('/etc/remember-me/api.env');backup=stage/'api.before-fast.env'
assert not backup.exists()
shutil.copy2(config,backup);backup.chmod(0o600)
services=['remember-me@'+name for name in ('api','ai','worker','profile')]
def switch(path):
    temp=current.with_name('current-fast-candidate')
    assert not temp.exists() and not temp.is_symlink()
    temp.symlink_to(path);os.replace(temp,current)
def ready():
    for _ in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8877/ready',timeout=2) as response:
                if json.load(response)['status']=='ready':return
        except Exception:pass
        time.sleep(1)
    raise RuntimeError('Readiness did not succeed')
subprocess.run(['systemctl','stop','remember-streamed-stage-api-20261014','remember-streamed-stage-ai-20261014'],check=True)
subprocess.run(['systemctl','stop',*services],check=True)
try:
    lines=[line for line in config.read_text().splitlines() if not line.startswith(('REMEMBER_REALTIME_VOICE_FAST_ENABLED=','REMEMBER_REALTIME_VOICE_STREAMED_ENABLED=','REMEMBER_RELEASE_ID='))]
    temp=config.with_suffix('.fast.tmp');temp.write_text('\n'.join(lines)+
        '\nREMEMBER_REALTIME_VOICE_FAST_ENABLED=true\nREMEMBER_REALTIME_VOICE_STREAMED_ENABLED=true\nREMEMBER_RELEASE_ID='+release.name+'\n');temp.chmod(0o600);os.replace(temp,config)
    switch(release)
    subprocess.run(['systemctl','start',*services],check=True);ready()
except Exception:
    subprocess.run(['systemctl','stop',*services],check=True)
    switch(old);shutil.copy2(backup,config)
    subprocess.run(['systemctl','start',*services],check=True);raise
state.update(production_switched=True,api_config_backup=str(backup))
(stage/'deployment.json').write_text(json.dumps(state,indent=2))
print(json.dumps(dict(current=str(current.resolve()),ready=True,database_migrated=False)))

"""Promote verified voice transport only; unchanged DB, audio, TLS and grants."""
import json, os, shutil, subprocess, time, urllib.request
from pathlib import Path

stage=Path('/var/lib/remember-me/voice-stability-20261014')
state=json.loads((stage/'stage.json').read_text())
current=Path('/opt/remember-me/current');old=Path(state['previous']);release=Path(state['candidate'])
assert os.geteuid()==0 and current.resolve()==old and release.is_dir()
assert json.loads((Path(state['snapshot'])/'restore-check.json').read_text())['audio_hash_match']
services=['remember-me@'+s for s in ('api','ai','worker','profile')]
backups={}
for name in ('api','ai'):
    file=Path('/etc/remember-me')/(name+'.env'); backup=stage/(name+'.before-stability.env')
    assert not backup.exists()
    shutil.copy2(file,backup);backup.chmod(0o600);backups[name]=backup

def switch(target):
    temp=current.with_name('current-stability-candidate')
    assert not temp.exists() and not temp.is_symlink()
    temp.symlink_to(target);os.replace(temp,current)

def ready():
    for _ in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8877/ready',timeout=2) as response:
                if json.load(response)['status']=='ready':return
        except Exception:pass
        time.sleep(1)
    raise RuntimeError('Readiness failed')

subprocess.run(['systemctl','stop','remember-stability-stage-api-20261014','remember-stability-stage-ai-20261014'],check=True)
subprocess.run(['systemctl','stop',*services],check=True)
try:
    for name in ('api','ai'):
        file=Path('/etc/remember-me')/(name+'.env')
        lines=[l for l in file.read_text().splitlines() if not l.startswith(('REMEMBER_RELEASE_ID=','AI_VOICE_HEDGE_AFTER_SECONDS=','AI_VOICE_RETRY_AFTER_SECONDS='))]
        lines.append('REMEMBER_RELEASE_ID='+release.name)
        if name=='ai':lines.append('AI_VOICE_RETRY_AFTER_SECONDS=3')
        temp=file.with_suffix('.stability.tmp');temp.write_text('\n'.join(lines)+'\n');temp.chmod(0o600);os.replace(temp,file)
    switch(release);subprocess.run(['systemctl','start',*services],check=True);ready()
except Exception:
    subprocess.run(['systemctl','stop',*services],check=True);switch(old)
    for name,backup in backups.items():shutil.copy2(backup,Path('/etc/remember-me')/(name+'.env'))
    subprocess.run(['systemctl','start',*services],check=True);raise
state.update(production_switched=True,current=str(current.resolve()),retry_after_seconds=3,total_model_budget_seconds=8)
(stage/'deployment.json').write_text(json.dumps(state,indent=2))
print(json.dumps(state))

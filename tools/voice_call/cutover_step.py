"""Promote additive opt-in API only. Keep original pipeline and all model services."""
import json,os,shutil,subprocess,time,urllib.request
from pathlib import Path
from dotenv import dotenv_values

stage=Path('/var/lib/remember-me/step-integrated-20261015')
state=json.loads((stage/'stage.json').read_text())
old=Path(state['previous']);release=Path(state['candidate']);current=Path('/opt/remember-me/current')
assert os.geteuid()==0 and current.resolve()==old
assert json.loads((Path(state['snapshot'])/'restore-check.json').read_text())['audio_hash_match']
rows=json.loads((stage/'round2-owner/results.json').read_text())
assert len(rows)==12 and all(r['ok'] for r in rows)
file=Path('/etc/remember-me/api.env');backup=stage/'api.before-step.env'
assert not backup.exists()
shutil.copy2(file,backup);backup.chmod(0o600)
key=dotenv_values('/var/lib/remember-me/step-2603-20261015/private.env')['STEP_API_KEY']
def switch(target):
    temp=current.with_name('current-step-candidate');assert not temp.exists() and not temp.is_symlink()
    temp.symlink_to(target);os.replace(temp,current)
def ready():
    for _ in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8877/ready',timeout=2) as r:
                if json.load(r)['status']=='ready':return
        except Exception:pass
        time.sleep(1)
    raise RuntimeError('API readiness failed')
subprocess.run(['systemctl','stop','remember-me@api'],check=True)
try:
    keys=('REMEMBER_RELEASE_ID=','REMEMBER_STEP_REALTIME_ENABLED=','REMEMBER_STEP_REALTIME_API_KEY=',
          'REMEMBER_REALTIME_VOICE_PREFETCH_ENABLED=')
    lines=[l for l in file.read_text().splitlines() if not l.startswith(keys)]
    lines+=['REMEMBER_RELEASE_ID='+release.name,'REMEMBER_STEP_REALTIME_ENABLED=true',
        'REMEMBER_STEP_REALTIME_API_KEY='+key,'REMEMBER_REALTIME_VOICE_PREFETCH_ENABLED=false']
    temp=file.with_suffix('.step.tmp');temp.write_text('\n'.join(lines)+'\n');temp.chmod(0o600);os.replace(temp,file)
    switch(release);subprocess.run(['systemctl','start','remember-me@api'],check=True);ready()
except Exception:
    subprocess.run(['systemctl','stop','remember-me@api'],check=True);switch(old);shutil.copy2(backup,file)
    subprocess.run(['systemctl','start','remember-me@api'],check=True);raise
state.update(production_switched=True,default_engine='pipeline',opt_in_engine='step_realtime',restarted_services=['api'])
(stage/'deployment.json').write_text(json.dumps(state,indent=2));print(json.dumps(state))

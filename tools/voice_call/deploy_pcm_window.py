"""Follow-up for a reproduced fixed-window PCM rejection; keep prior release."""
import json,os,shutil,subprocess,time,urllib.request
from pathlib import Path

stage=Path('/var/lib/remember-me/voice-stability-20261014')
current=Path('/opt/remember-me/current');old=current.resolve()
release=Path('/opt/remember-me/releases/paired-voice-stability2-20261014')
assert os.geteuid()==0 and old.name=='paired-voice-stability-20261014' and not release.exists()
shutil.copytree(old,release,ignore=shutil.ignore_patterns('.venv','var','__pycache__','.pytest_cache'))
for service in ('backend','ai-core'):
    (release/'services'/service/'.venv').symlink_to(old/'services'/service/'.venv',target_is_directory=True)
shutil.copy2(stage/'pcm_rate.py',release/'services/backend/app/pcm_rate.py')
shutil.copy2(stage/'test_pcm_rate.py',release/'services/backend/tests/test_pcm_rate.py')
api=release/'services/backend/app/api/voice_sessions.py';s=api.read_text()
before='window=time.monotonic(); byte_count=0';assert before in s
s=s.replace(before,'from ..pcm_rate import PcmRateLimiter\n        rate=PcmRateLimiter()')
before="now=time.monotonic()\n                if now-window>5: window=now; byte_count=0\n                byte_count+=len(pcm)\n                if byte_count>32_000*7: raise RealtimeFailure('AUDIO_RATE_LIMIT')"
assert before in s;s=s.replace(before,'rate.consume(len(pcm))');api.write_text(s)
env={**os.environ,'PYTHONPATH':str(release/'services/backend')+':/var/lib/remember-me/voice-next-20261014/test-deps'}
subprocess.run([str(release/'services/backend/.venv/bin/python'),'-m','pytest','tests/test_pcm_rate.py','-q'],cwd=release/'services/backend',env=env,check=True)
backup=release/'tools/round_two/backup_ecs_paired.sh'
done=subprocess.run(['bash','-s','--',str(release)],input=backup.read_text(),text=True,capture_output=True,check=True)
snapshot=Path(json.loads(done.stdout.strip().splitlines()[-1])['snapshot'])
assert json.loads((snapshot/'restore-check.json').read_text())['audio_hash_match']
services=['remember-me@'+name for name in ('api','ai','worker','profile')]
for name in ('api','ai'):
    backup=stage/(name+'.before-buffer.env');assert not backup.exists()
    shutil.copy2(Path('/etc/remember-me')/(name+'.env'),backup);backup.chmod(0o600)
def switch(target):
    temp=current.with_name('current-buffer-candidate');assert not temp.exists() and not temp.is_symlink()
    temp.symlink_to(target);os.replace(temp,current)
subprocess.run(['systemctl','stop',*services],check=True)
try:
    for name in ('api','ai'):
        file=Path('/etc/remember-me')/(name+'.env')
        lines=[l for l in file.read_text().splitlines() if not l.startswith('REMEMBER_RELEASE_ID=')]
        temp=file.with_suffix('.buffer.tmp');temp.write_text('\n'.join(lines)+'\nREMEMBER_RELEASE_ID='+release.name+'\n');temp.chmod(0o600);os.replace(temp,file)
    switch(release);subprocess.run(['systemctl','start',*services],check=True)
    for _ in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8877/ready',timeout=2) as r:
                if json.load(r)['status']=='ready':break
        except Exception:pass
        time.sleep(1)
    else:raise RuntimeError('Readiness failed')
except Exception:
    subprocess.run(['systemctl','stop',*services],check=True);switch(old)
    for name in ('api','ai'):shutil.copy2(stage/(name+'.before-buffer.env'),Path('/etc/remember-me')/(name+'.env'))
    subprocess.run(['systemctl','start',*services],check=True);raise
state=dict(current=str(current.resolve()),previous=str(old),snapshot=str(snapshot),database_migrated=False,pcm_burst_seconds=7,pcm_bytes_per_second=32000)
(stage/'buffer-deployment.json').write_text(json.dumps(state,indent=2));print(json.dumps(state))

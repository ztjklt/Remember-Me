"""Private localhost integration; never logs environment values or credentials."""
import json, subprocess, time
from pathlib import Path
import httpx

stage=Path('/var/lib/remember-me/voice-stability-20261014')
env=stage/'ai.env'
lines=[l for l in env.read_text().splitlines() if not l.startswith(('AI_VOICE_HEDGE_AFTER_SECONDS=','AI_VOICE_RETRY_AFTER_SECONDS='))]
env.write_text('\n'.join(lines)+'\nAI_VOICE_RETRY_AFTER_SECONDS=3\n');env.chmod(0o600)
subprocess.run(['systemctl','restart','remember-stability-stage-ai-20261014'],check=True)
time.sleep(3)
sample=json.loads(Path('/var/lib/remember-me/voice-next-20261014/packets.json').read_text())[1]
started=time.perf_counter()
with httpx.Client(timeout=20,trust_env=False) as client:
    response=client.post('http://127.0.0.1:8896/twin/voice-live',json=sample['payload'])
    response.raise_for_status()
    events=[json.loads(l) for l in response.text.splitlines() if l]
    assert events[-1]['type']=='final', [e.get('code',e['type']) for e in events]
    assert '淡' in events[-1]['result']['answer']
result=dict(ok=True,seconds=round(time.perf_counter()-started,3),events=events)
(stage/'integration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'ok':True,'seconds':result['seconds'],'types':[e['type'] for e in events]}))

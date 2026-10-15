"""Compare visible source scope, not answer quality, without printing credentials."""
import json
from pathlib import Path
import httpx

root=Path('/var/lib/remember-me/step-integrated-20261015');out={}
for role,file in [('owner','credentials.json'),('reader','reader-credentials.json')]:
    with httpx.Client(base_url='http://127.0.0.1:8897',trust_env=False,timeout=30) as h:
        r=h.post('/api/v1/accounts/login',json=json.loads((Path('/var/lib/remember-me/voice-stage-20261014')/file).read_text()));r.raise_for_status()
        h.headers['Authorization']='Bearer '+r.json()['actor_token']
        spaces=h.get('/api/v1/workbench/spaces').json()['items']
        subject=next(s['subject_id'] for s in spaces if s['role']==role and '陈守义' in s.get('display_name',s.get('name','')))
        r=h.get(f'/api/v1/subjects/{subject}/memory-search',params={'q':'旧水杯'});r.raise_for_status()
        out[role]=r.json()
        if role=='reader':
            g=h.get(f'/api/v1/workbench/subjects/{subject}/grants');g.raise_for_status()
            grants=g.json()['items']
            cup_episodes={x['episode_id'] for x in out['owner']['items'] if '杯' in json.dumps(x,ensure_ascii=False)}
            out['cup_scope']=dict(owner_cup_episode_count=len(cup_episodes),
                reader_cup_grants=[{'revoked':bool(x.get('revoked_at')),'cloud_allowed':x.get('cloud_processing_allowed',False)}
                    for x in grants if x['episode_id'] in cup_episodes])
(root/'visibility.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({role:dict(type=type(data).__name__,cup_present='杯' in json.dumps(data,ensure_ascii=False)) for role,data in out.items()}))

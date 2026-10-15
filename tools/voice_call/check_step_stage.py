"""Repeat fixed questions through real ASR, authorized retrieval and Step speech."""
import asyncio,json,shutil,sys,time,urllib.request
from pathlib import Path
from types import SimpleNamespace
import evaluate

root=Path('/var/lib/remember-me/step-integrated-20261015')
for _ in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8897/ready',timeout=2) as r:
            if json.load(r)['status']=='ready':break
    except Exception:pass
    time.sleep(1)
else:raise RuntimeError('Candidate API not ready')
role=sys.argv[1] if len(sys.argv)>1 else 'owner'
out=root/('round2-'+role);out.mkdir(exist_ok=True)
for f in (root/'round1').glob('*.wav'):
    if not f.name.startswith('answer-'):shutil.copy2(f,out/f.name)
questions=[('memory','你喜欢喝什么茶？'),('memory','刚才说的茶，浓一点还是淡一点？'),
    ('memory','第一次独立跑十二路是哪一年？'),('memory','为什么有一条记录说是一九八六年？'),
    ('memory','旧水杯有什么故事？'),('memory','他银行卡的密码是什么？')]
evaluate.CASES=questions if role=='reader' else questions*2
args=SimpleNamespace(output=str(out),env=str(root/'api.env'),
    credentials='/var/lib/remember-me/voice-stage-20261014/'+('reader-credentials.json' if role=='reader' else 'credentials.json'),
    base='http://127.0.0.1:8897',role=role,mode='evidence',response_speed='fast',engine='step_realtime',ca_file=None,limit=len(evaluate.CASES))
asyncio.run(evaluate.main(args))

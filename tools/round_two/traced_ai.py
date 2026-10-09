"""Local QA metadata only. Never record request/response bodies or exception text."""
import hashlib, json, re, sys, time
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'services/ai-core'))
from app.providers.weixin import WeixinChat
original=WeixinChat.complete
OUT=ROOT/'services/backend/var/round-two/twin-call-metadata'


def traced(self,system,payload):
    # Corpus labels cannot establish authorization to log personal materials.
    # Store no materials even when the caller labels them synthetic.
    if not system.startswith(('twin-points-v','twin-points-review-v')):
        return original(self,system,payload)
    OUT.mkdir(parents=True,exist_ok=True)
    version=re.match(r'twin-points-(?:review-)?v[0-9]+',system)
    record={'started':datetime.now(timezone.utc).isoformat(),
        'prompt_version':version.group(0) if version else 'unknown',
        'prompt_sha256':hashlib.sha256(system.encode()).hexdigest()}
    started=time.monotonic()
    path=OUT/(uuid4().hex+'.json')
    try:
        result,model=original(self,system,payload)
        record.update(status='returned',model=model)
        return result,model
    except Exception as exc:
        record['error_type']=type(exc).__name__
        record['status']='failed'
        raise
    finally:
        record['finished']=datetime.now(timezone.utc).isoformat()
        record['elapsed_seconds']=round(time.monotonic()-started,3)
        path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    WeixinChat.complete=traced
    import uvicorn
    uvicorn.run('app.main:app',host='127.0.0.1',port=8891)

"""Stage the exact reviewed backend/AI delta; preserve runtime config and data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT = Path('/opt/remember-me')
SERVICES = ['ai', 'api', 'worker', 'profile']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def switch(target):
    pending=ROOT/'current.highlights-next'
    assert not pending.exists() and not pending.is_symlink()
    pending.symlink_to(target); pending.replace(ROOT/'current')


def stage(payload, name):
    manifest=json.loads((payload/'manifest.json').read_text())
    previous=(ROOT/'current').resolve(); candidate=ROOT/'releases'/name
    assert previous.parent==ROOT/'releases' and not candidate.exists()
    for item in manifest['files']:
        path=Path(item['path'])
        assert not path.is_absolute() and '..' not in path.parts
        assert str(path).startswith(('services/backend/', 'services/ai-core/'))
        old=previous/path
        # Older Windows-authored deployments retain CRLF; compare source text
        # against Git's LF baseline without accepting any semantic drift.
        actual=hashlib.sha256(old.read_text(encoding='utf-8').encode()).hexdigest() if old.exists() else None
        assert actual==item['before'], f'Live source drift: {path}'
        assert digest(payload/'files'/path)==item['after']
    shutil.copytree(previous,candidate,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
    for item in manifest['files']:
        target=candidate/item['path']; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(payload/'files'/item['path'],target)
    record={'previous':str(previous),'candidate':str(candidate),'files':manifest['files'],'source_commit':manifest['source_commit']}
    (payload/'deployment.json').write_text(json.dumps(record,indent=2))
    print(json.dumps({'staged':str(candidate),'files':len(record['files'])}))


def validate(payload):
    record=json.loads((payload/'deployment.json').read_text()); candidate=Path(record['candidate'])
    for item in record['files']: assert digest(candidate/item['path'])==item['after']
    suites={'backend':['test_recording_highlights','test_paraformer_asr','test_worker','test_work3200_ingestion','test_transcript_correction'],
            'ai-core':['test_recording_highlights','test_memory_semantic_units','test_extractor','test_weixin']}
    for service, tests in suites.items():
        folder=candidate/'services'/service
        env={**os.environ,'PYTHONPATH':str(payload/'test-support')}
        with (payload/(service+'-tests.log')).open('w') as out:
            subprocess.run([str(folder/'.venv/bin/python'),'-m','pytest',*[f'tests/{t}.py' for t in tests],'-q',
                '--junitxml='+str(payload/(service+'-tests.xml'))],cwd=folder,env=env,stdout=out,stderr=out,check=True)
    record['validated']=True; (payload/'deployment.json').write_text(json.dumps(record,indent=2))
    print('Candidate backend and AI tests passed with isolated test databases.')


def activate(payload):
    record=json.loads((payload/'deployment.json').read_text()); candidate=Path(record['candidate'])
    assert record.get('validated') and str((ROOT/'current').resolve())==record['previous']
    for item in record['files']: assert digest(candidate/item['path'])==item['after']
    try:
        switch(candidate)
        for service in SERVICES: subprocess.run(['systemctl','restart','remember-me@'+service],check=True)
        for _ in range(45):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8877/ready',timeout=2) as r: assert r.status==200
                with urllib.request.urlopen('http://127.0.0.1:8879/health',timeout=2) as r: assert r.status==200
                for service in SERVICES: subprocess.run(['systemctl','is-active','--quiet','remember-me@'+service],check=True)
                record['activated']=True; (payload/'deployment.json').write_text(json.dumps(record,indent=2))
                print('Activated and ready; runtime credentials and data unchanged.'); return
            except Exception: time.sleep(1)
        raise RuntimeError('Candidate readiness failed')
    except Exception:
        switch(Path(record['previous']))
        for service in SERVICES: subprocess.run(['systemctl','restart','remember-me@'+service],check=True)
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['stage','validate','activate']);p.add_argument('--payload',type=Path,required=True)
    p.add_argument('--name',default='paired-highlights-20261016');args=p.parse_args()
    assert os.geteuid()==0 and args.name.startswith('paired-') and '/' not in args.name
    if args.action=='stage':stage(args.payload.resolve(),args.name)
    elif args.action=='validate':validate(args.payload.resolve())
    else:activate(args.payload.resolve())

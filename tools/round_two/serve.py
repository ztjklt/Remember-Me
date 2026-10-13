"""Isolated second-round acceptance against a SQLite backup, existing real providers.

No production DB, audio or existing service is changed. No keys on argv/stdout.
"""
import argparse, json, os, sqlite3, subprocess, sys, time
from pathlib import Path
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'services/backend'; AI=ROOT/'services/ai-core'; OUT=BACKEND/'var/round-two'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--structured-twin',action='store_true')
    parser.add_argument('--quoted-twin',action='store_true')
    parser.add_argument('--trace-twin-metadata',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    env={**os.environ,**{k:v for k,v in dotenv_values(BACKEND/'.env').items() if v is not None}}
    original=env.get('REMEMBER_DATABASE_URL','sqlite:///./var/agent-loop.db')
    if not original.startswith('sqlite:///'): raise SystemExit('Only explicit local SQLite backup is supported')
    source=Path(original.removeprefix('sqlite:///'))
    if not source.is_absolute(): source=BACKEND/source
    target=OUT/'acceptance.db'
    if not target.exists():
        with sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True) as src, sqlite3.connect(target) as dst: src.backup(dst)
    env.update(REMEMBER_DATABASE_URL='sqlite:///'+target.as_posix(),REMEMBER_AI_CORE_URL='http://127.0.0.1:8891',
        REMEMBER_AI_BACKEND='http',REMEMBER_ENABLE_WORKBENCH='true',REMEMBER_AI_TIMEOUT_SECONDS='120',NO_PROXY='localhost,127.0.0.1,::1')
    ai_env={**env,**{k:v for k,v in dotenv_values(AI/'.env').items() if v is not None}}
    if not ai_env.get('WEIXIN_CHAT_API_KEY'): raise SystemExit('Existing Weixin key missing')
    ai_env.update(AI_PROVIDER='weixin',AI_BASE_URL='https://chatapi.weixin.qq.com/openai/v1',AI_MODEL='Deepseek-v4-flash',
        AI_TIMEOUT_SECONDS='45',AI_MAX_CONCURRENT_REQUESTS='1',AI_NARRATIVE_TRACE_DIR='')
    ai_env['AI_TWIN_STRUCTURED_ANSWERS']='true' if args.structured_twin else 'false'
    ai_env['AI_TWIN_QUOTE_ANSWERS']='true' if args.quoted_twin else 'false'
    with (OUT/'migration.log').open('a',encoding='utf8') as log:
        subprocess.run([str(BACKEND/'.venv/Scripts/python.exe'),'-m','alembic','upgrade','head'],cwd=BACKEND,env=env,stdout=log,stderr=log,check=True)
    ai_command=[str(ROOT/'tools/round_two/traced_ai.py')] if args.trace_twin_metadata else ['-m','uvicorn','app.main:app','--port','8891']
    commands=[('ai',AI,ai_env,ai_command),
        ('backend',BACKEND,env,['-m','uvicorn','app.main:app','--port','8890']),
        ('profile',BACKEND,env,['-m','app.profile_worker'])]
    children=[];logs=[]
    try:
        for name,cwd,variables,args in commands:
            log=(OUT/(name+'.log')).open('a',encoding='utf8');logs.append(log)
            proc=subprocess.Popen([str(cwd/'.venv/Scripts/python.exe'),*args],cwd=cwd,env=variables,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0);children.append(proc)
        (OUT/'pids.json').write_text(json.dumps({'supervisor':os.getpid(),'children':[p.pid for p in children]}),encoding='utf8')
        print('Isolated workbench: http://127.0.0.1:8890/workbench/',flush=True)
        while all(p.poll() is None for p in children): time.sleep(1)
        raise RuntimeError('An acceptance service stopped; inspect round-two logs')
    finally:
        for p in children:
            if p.poll() is None: p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill()
        for log in logs:log.close()

if __name__=='__main__':main()

"""Start an isolated local real-provider runtime. Never changes ECS or Git."""
import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT/'services/backend'
VAR = BACKEND/'var/a01-20261012'


def configuration():
    private = json.loads((VAR/'private/paraformer.json').read_text(encoding='utf8'))
    source = dotenv_values('D:/codex_work/remember-me-agent-loop/services/ai-core/.env')
    key = os.environ.get('WEIXIN_CHAT_API_KEY') or source.get('WEIXIN_CHAT_API_KEY')
    if not key:
        raise SystemExit('Existing Weixin key missing; no substitute provider started.')
    env = dict(os.environ)
    # The desktop tool shell can carry a SOCKS proxy. The already verified
    # mainland Paraformer route is direct; don't inherit a different transport.
    for proxy_name in list(env):
        if proxy_name.lower() in {'http_proxy','https_proxy','all_proxy'}:env.pop(proxy_name)
    env.update(PYTHONUTF8='1', NO_PROXY='localhost,127.0.0.1,::1', REMEMBER_ENVIRONMENT='development',
        HF_HUB_OFFLINE='1', OMP_NUM_THREADS='1',
        REMEMBER_ALLOWED_HOSTS='["127.0.0.1","localhost","[::1]","10.0.2.2"]',
        REMEMBER_LOG_LEVEL='WARNING', REMEMBER_ENABLE_WORKBENCH='true',
        REMEMBER_ALLOW_ACCOUNT_REGISTRATION='true',
        REMEMBER_DATABASE_URL='sqlite:///'+(VAR/'runtime/remember.db').as_posix(),
        REMEMBER_OBJECT_STORE_BACKEND='local', REMEMBER_OBJECT_STORE_ROOT=str(VAR/'runtime/audio'),
        REMEMBER_STT_BACKEND='paraformer', REMEMBER_PARAFORMER_API_KEY=private['paraformer_api_key'],
        REMEMBER_PARAFORMER_BASE_URL=private['paraformer_base_url'],
        REMEMBER_PARAFORMER_STATE_DIR=str(VAR/'evaluation/asr-paraformer-v1/adapter-state'),
        REMEMBER_AI_BACKEND='http', REMEMBER_AI_CORE_URL='http://127.0.0.1:8892',
        REMEMBER_AI_TIMEOUT_SECONDS='100', REMEMBER_JOB_MAX_ATTEMPTS='3',
        AI_PROVIDER='weixin', WEIXIN_CHAT_API_KEY=key,
        AI_BASE_URL='https://chatapi.weixin.qq.com/openai/v1', AI_MODEL='Deepseek-v4-flash',
        AI_MODEL_VERSION='Deepseek-v4-flash', AI_TIMEOUT_SECONDS='45', AI_MAX_CONCURRENT_REQUESTS='1',
        AI_PROFILE_VERIFY_CANDIDATES='true', AI_PROFILE_TRACE_DIR=str(VAR/'runtime/profile-review'),
        AI_TWIN_QUOTE_ANSWERS='true', AI_TWIN_STRUCTURED_ANSWERS='false')
    speech=dotenv_values('D:/codex_work/remember-me-agent-loop/services/backend/.env.speech-eval')
    voice_key=os.environ.get('MIMO_API_KEY') or speech.get('MIMO_API_KEY')
    accounts=VAR/'private/local-accounts.json'
    if voice_key and accounts.exists():
        local=json.loads(accounts.read_text(encoding='utf8'))
        import sqlite3
        with sqlite3.connect(VAR/'runtime/remember.db') as database:
            row=database.execute('SELECT s.subject_id FROM subjects s JOIN accounts a ON a.actor_id=s.owner_actor_id '
                'WHERE a.username=? AND s.display_name=?',(local['owner']['username'],'陈国梁 · 虚构人物')).fetchone()
        subject=row[0] if row else None
        if subject:
            env.update(REMEMBER_VOICE_SYNTHETIC_BACKEND='xiaomi',REMEMBER_XIAOMI_VOICE_API_KEY=voice_key,
                REMEMBER_A01_VOICE_SUBJECT_ID=subject,
                REMEMBER_A01_VOICE_REFERENCE_PATH=str(VAR/'evaluation/speech/A01_01.wav'))
    return env


def start():
    for port in (8891, 8892):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))==0:
                raise SystemExit(f'Port {port} already active; inspect checkpoint, do not duplicate.')
    env = configuration()
    runtime=VAR/'runtime'; runtime.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=BACKEND,env=env,check=True)
    commands=[('api',BACKEND,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8891']),
        ('ai',ROOT/'services/ai-core',['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8892']),
        ('worker',BACKEND,['-m','app.worker']),('profile',BACKEND,['-m','app.profile_worker'])]
    rows=[]
    for name,cwd,args in commands:
        with (runtime/(name+'.log')).open('a',encoding='utf8') as log:
            process=subprocess.Popen([sys.executable,'-X','utf8',*args],cwd=cwd,env=env,
                stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        rows.append({'name':name,'pid':process.pid})
    (runtime/'processes.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    print('Local runtime starting: http://127.0.0.1:8891/workbench/companion.html')
    print('ASR Paraformer / text Deepseek-v4-flash; separate local DB, no ECS writes.')


def stop():
    import psutil
    checkpoint=VAR/'runtime/processes.json'
    if not checkpoint.exists(): return
    roots={str(BACKEND.resolve()).lower(),str((ROOT/'services/ai-core').resolve()).lower()}
    for row in json.loads(checkpoint.read_text(encoding='utf8')):
        try:
            process=psutil.Process(row['pid'])
            if str(Path(process.cwd()).resolve()).lower() not in roots:
                raise SystemExit('Saved PID no longer belongs to this runtime; not stopped.')
            children=process.children(recursive=True)
            for child in reversed(children):child.terminate()
            process.terminate();psutil.wait_procs(children+[process],timeout=5)
        except psutil.NoSuchProcess: pass
    print('Only saved local A01 processes stopped.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','restart']);args=parser.parse_args()
    if args.action in {'stop','restart'}:stop()
    if args.action in {'start','restart'}:start()

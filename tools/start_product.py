"""Local product entry. No secrets in argv/output; never starts a fake provider.

Run with the combined backend/AI environment. --check is read-only.
Optional --install-android uses one selected ADB device and loopback forwarding.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from urllib.request import build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT/'services/backend'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    p.add_argument('--install-android',action='store_true')
    p.add_argument('--serial')
    p.add_argument('--adb',default=shutil.which('adb'))
    a=p.parse_args()
    required=['fastapi','uvicorn','sqlalchemy','alembic','httpx','dotenv','opencc','filelock','boto3','pydantic_settings']
    missing=[name for name in required if importlib.util.find_spec(name) is None]
    if missing:raise SystemExit('Missing Python dependencies: '+', '.join(missing)+'. See docs/agent-loop/INSTALL_ANDROID.md')
    if not shutil.which('ffmpeg'):raise SystemExit('FFmpeg is required for cloud audio transport; no local ASR is used.')
    from dotenv import dotenv_values
    env={**os.environ,**{k:v for k,v in dotenv_values(BACKEND/'.env').items() if v is not None}}
    ai={**env,**{k:v for k,v in dotenv_values(ROOT/'services/ai-core/.env').items() if v is not None}}
    if env.get('REMEMBER_STT_BACKEND')!='groq' or not env.get('REMEMBER_GROQ_API_KEY'):
        raise SystemExit('Configure Groq ASR in the private backend .env; no fallback will be used.')
    if ai.get('AI_PROVIDER','weixin')!='weixin' or not ai.get('WEIXIN_CHAT_API_KEY'):
        raise SystemExit('Configure Weixin text model in the private server .env; no fallback will be used.')
    opener=build_opener(ProxyHandler({}))
    def running():
        try:
            with opener.open('http://127.0.0.1:8877/health',timeout=2) as r:
                result=json.load(r)
            with opener.open('http://127.0.0.1:8877/workbench/',timeout=2) as r:
                page=r.read(64000).decode('utf-8')
            return result.get('status')=='ok' and '勿忘我' in page and 'id="accountEnter"' in page
        except Exception:return False
    up=running()
    print(json.dumps({'dependencies':'ready','cloud_keys':'configured, values hidden',
                      'local_backend_running':up,'provider_calls_made':False}))
    if a.check:return
    if not up:
        import socket
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',8877))==0:raise SystemExit('Port 8877 belongs to another or incomplete service. Inspect it before restarting.')
        (BACKEND/'var').mkdir(exist_ok=True)
        # Read the configured path; never copy/delete/move a user's data directory.
        sys.path.insert(0,str(BACKEND))
        os.chdir(BACKEND)
        from app.config import Settings
        from sqlalchemy.engine import make_url
        url=make_url(Settings().database_url)
        if url.drivername=='sqlite' and url.database and Path(url.database).exists():
            backup=BACKEND/'var'/('before-product-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
            with sqlite3.connect(url.database) as source, sqlite3.connect(backup) as target:source.backup(target)
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=BACKEND,env=env,check=True)
        with (BACKEND/'var/product-launch.log').open('ab') as log:
            subprocess.Popen([sys.executable,'run_workbench.py'],cwd=BACKEND,env=env,stdout=log,stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                             start_new_session=os.name!='nt')
        for _ in range(60):
            if running():break
            time.sleep(1)
        else:raise SystemExit('Service did not become ready. Inspect services/backend/var/product-launch.log and service logs; do not start another copy.')
    if a.install_android:
        if not a.adb:raise SystemExit('ADB not found; supply --adb PATH and --serial DEVICE.')
        apk=ROOT/'output/remember-me/remember-me-local-debug.apk'
        if not apk.exists():apk=ROOT/'apps/android/app/build/outputs/apk/debug/app-debug.apk'
        if not apk.exists():raise SystemExit('Test APK missing. Build :app:assembleDebug first.')
        device=[a.adb]+(['-s',a.serial] if a.serial else [])
        subprocess.run(device+['reverse','tcp:8877','tcp:8877'],check=True)
        subprocess.run(device+['install','-r',str(apk)],check=True)
        subprocess.run(device+['shell','am','start','-n','me.remember.app/.MainActivity'],check=True)
    print('Ready: http://127.0.0.1:8877/workbench/ . Register an account; new spaces contain no demo stories.')
    print('Android USB/emulator requires the PC service and ADB forwarding. This is not a public online deployment.')


if __name__=='__main__':main()

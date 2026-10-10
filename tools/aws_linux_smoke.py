"""Actual Linux + PostgreSQL + TLS proxy smoke. No ASR/LLM calls or credentials.

Run inside the prepared Linux source tree with its backend Python. Only touches
a random schema in an explicitly named *_test database and temporary loopback
processes. The local CA is trusted by this client only, never installed globally.
"""
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'services/backend'


def main():
    database = 'remember_deploy_test'
    schema = 'proxy_test_' + uuid4().hex
    admin = create_engine('postgresql+psycopg:///' + database)
    for port in (18877, 18443):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    processes = []
    checks = []
    try:
        with tempfile.TemporaryDirectory(prefix='remember-proxy-') as directory:
            scratch = Path(directory)
            env = {**os.environ, 'REMEMBER_ENVIRONMENT': 'staging',
                'REMEMBER_DATABASE_URL': f'postgresql+psycopg:///{database}?options=-csearch_path%3D{schema}',
                'REMEMBER_ENABLE_WORKBENCH': 'true', 'REMEMBER_ALLOW_ACCOUNT_REGISTRATION': 'true',
                'REMEMBER_ALLOWED_HOSTS': '["localhost","127.0.0.1"]',
                'REMEMBER_OBJECT_STORE_BACKEND': 'local', 'REMEMBER_OBJECT_STORE_ROOT': str(scratch/'audio'),
                'REMEMBER_STT_BACKEND': 'http', 'REMEMBER_STT_URL': 'http://127.0.0.1:9',
                'REMEMBER_AI_BACKEND': 'http', 'REMEMBER_AI_CORE_URL': 'http://127.0.0.1:9',
                'REMEMBER_API_PORT': '18877', 'REMEMBER_DOMAIN': 'localhost:18443',
                'REMEMBER_UPSTREAM': '127.0.0.1:18877', 'XDG_DATA_HOME': str(scratch/'caddy-data'),
                'XDG_CONFIG_HOME': str(scratch/'caddy-config')}
            migration = subprocess.run([str(BACKEND/'.venv/bin/python'), '-m', 'alembic', 'upgrade', 'head'],
                cwd=BACKEND, env=env, capture_output=True)
            if migration.returncode:
                raise RuntimeError('Migration failed: '+migration.stderr.decode()[-2000:])
            config = '{\n admin off\n auto_https disable_redirects\n skip_install_trust\n}\n' + (
                ROOT/'infra/aws/Caddyfile').read_text().replace('    encode gzip', '    tls internal\n    encode gzip')
            path = scratch/'Caddyfile'; path.write_text(config)
            with (scratch/'services.log').open('w') as log:
                def api():
                    process = subprocess.Popen(['bash', str(ROOT/'infra/aws/run-service.sh'), 'api'],
                        env=env, stdout=log, stderr=log)
                    processes.append(process)
                    return process
                backend = api()
                processes.append(subprocess.Popen(['caddy','run','--config',str(path),'--adapter','caddyfile'],
                    env=env, stdout=log, stderr=log))
                cert = scratch/'caddy-data/caddy/pki/authorities/local/root.crt'
                deadline = time.monotonic()+30
                while not cert.exists():
                    if time.monotonic()>deadline or any(p.poll() is not None for p in processes):
                        raise RuntimeError('TLS proxy startup failed: '+(scratch/'services.log').read_text()[-3000:])
                    time.sleep(.2)
                context = ssl.create_default_context(cafile=str(cert))
                with httpx.Client(base_url='https://localhost:18443',verify=context,trust_env=False,timeout=10) as client:
                    while True:
                        try:
                            ready = client.get('/health')
                            if ready.status_code != 502: break
                        except httpx.TransportError: pass
                        if time.monotonic()>deadline: raise RuntimeError('Backend not ready')
                        time.sleep(.2)
                    assert client.get('/workbench/').status_code==200
                    assert client.get('/docs').status_code==404
                    checks += ['real TLS certificate verified', 'workbench served through proxy', 'API docs hidden']
                    credentials={'username':'tls_'+uuid4().hex[:12], 'password':uuid4().hex,
                                 'display_name':'TLS 虚构测试者'}
                    response=client.post('/api/v1/accounts/register',json=credentials,
                        headers={'Origin':'https://localhost:18443','X-Forwarded-Proto':'http','X-Forwarded-Host':'attacker.invalid'})
                    assert response.status_code==201, response.text
                    cookie=response.headers['set-cookie']
                    assert all(flag in cookie for flag in ('Secure','HttpOnly','SameSite=strict'))
                    spaces=client.get('/api/v1/workbench/spaces').json()['items']
                    assert len(spaces)==1 and spaces[0]['role']=='owner'
                    assert client.post('/api/v1/accounts/logout',headers={'Origin':'https://attacker.invalid'}).status_code==401
                    checks += ['HTTPS registration and secure cookie', 'forwarded-header spoof ignored by proxy',
                               'authenticated private space', 'cross-origin cookie write rejected']
                    backend.terminate(); backend.wait(10); backend=api()
                    deadline=time.monotonic()+20
                    while True:
                        resumed=client.get('/api/v1/workbench/spaces')
                        if resumed.status_code==200: break
                        if time.monotonic()>deadline: raise RuntimeError('Restart lost authenticated state')
                        time.sleep(.2)
                    assert resumed.json()['items']==spaces
                    checks.append('API restart preserves database and session')
                    # Restore into a separate disposable database, never over
                    # the running application or another developer's schemas.
                    restored = 'remember_restore_' + uuid4().hex + '_test'
                    dump = scratch/'database.dump'
                    subprocess.run(['pg_dump','-Fc','--no-owner','--no-acl','-n',schema,
                                    '-d',database,'-f',str(dump)],check=True,capture_output=True)
                    subprocess.run(['runuser','-u','postgres','--','createdb','-O','root',restored],
                                   check=True,capture_output=True)
                    recovered=create_engine('postgresql+psycopg:///'+restored)
                    try:
                        subprocess.run(['pg_restore','--no-owner','--no-acl','-d',restored,str(dump)],
                                       check=True,capture_output=True)
                        with recovered.connect() as conn:
                            assert conn.scalar(text(f'SELECT count(*) FROM {schema}.accounts'))==1
                            assert conn.scalar(text(f'SELECT subject_id FROM {schema}.subjects'))==spaces[0]['subject_id']
                        checks.append('pg_dump restored into independent database with account and owner space intact')
                    finally:
                        recovered.dispose()
                        subprocess.run(['runuser','-u','postgres','--','dropdb',restored],check=True,capture_output=True)
                    assert client.post('/api/v1/accounts/logout',headers={'Origin':'https://localhost:18443'}).status_code==200
                    assert client.get('/api/v1/workbench/spaces').status_code==401
                    checks.append('logout invalidates session')
                    login={key:credentials[key] for key in ('username','password')}
                    assert client.post('/api/v1/accounts/login',json=login).status_code==200
                    assert client.post('/api/v1/accounts/login',json=login,headers={'Origin':'https://attacker.invalid'}).status_code==422
                    direct=httpx.post('http://127.0.0.1:18877/api/v1/accounts/login',json=login,trust_env=False)
                    assert direct.status_code==422
                    checks += ['HTTPS login after restart', 'foreign origin rejected', 'plain HTTP login refused in staging']
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()
    print(json.dumps({'checks':checks, 'passed':len(checks), 'model_calls':0,
        'environment':'Ubuntu/PostgreSQL16/Caddy loopback TLS', 'public_deployment':False},ensure_ascii=False,indent=2))


if __name__=='__main__': main()

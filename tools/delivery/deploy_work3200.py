"""Apply only the reviewed hardware delta to a copy of the current ECS release.

Run on ECS as root, with a private payload folder. Stage/tests precede activation.
No database migration, model configuration rewrite, or firewall changes.
"""
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
CONFIG = Path('/etc/remember-me/api.env')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(payload, name):
    previous = (ROOT / 'current').resolve()
    assert previous.parent == ROOT / 'releases'
    candidate = ROOT / 'releases' / name
    assert not candidate.exists()
    backend = previous / 'services/backend'
    expected = {'config.py': '03e28461acdabba07c1bb90349928a6daa2fbcdccb3fb14e8135c7e996ed4f5d',
                'main.py': '995a9da034629e28531711c85d74729a87bda6a1ec29a294f05bde70654399b4'}
    for filename, sha in expected.items():
        assert digest(backend / 'app' / filename) == sha, 'Live source changed; inspect before staging'
    shutil.copytree(previous, candidate, symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    backend = candidate / 'services/backend'
    path = backend / 'app/config.py'
    content = path.read_text()
    anchor = "    allowed_hosts: list[str] = ['127.0.0.1', 'localhost', '[::1]', 'testserver']\n"
    assert content.count(anchor) == 1 and 'work3200_app_key' not in content
    path.write_text(content.replace(anchor, anchor + "    work3200_app_id: str = ''\n    work3200_app_key: SecretStr = SecretStr('')\n    work3200_environment: Literal['DEVELOPMENT', 'PRODUCTION'] = 'DEVELOPMENT'\n"))
    path = backend / 'app/main.py'
    content = path.read_text(); anchor = '    app.include_router(session.router)\n'
    assert content.count(anchor) == 1
    path.write_text(content.replace(anchor, anchor + '    from .api import hardware\n    app.include_router(hardware.router)\n'))
    for source, target in [('work3200.py', 'app/work3200.py'), ('hardware.py', 'app/api/hardware.py'), ('test_work3200_auth.py', 'tests/test_work3200_auth.py')]:
        shutil.copy2(payload / source, backend / target)
    shutil.copy2(CONFIG, payload / 'api.env.before')
    business = json.loads((payload / 'vendor-business.json').read_text())
    content = CONFIG.read_text()
    updates = {'REMEMBER_WORK3200_APP_ID': business['app_id'],
               'REMEMBER_WORK3200_APP_KEY': business['app_key'],
               'REMEMBER_WORK3200_ENVIRONMENT': 'DEVELOPMENT'}
    lines = [line for line in content.splitlines() if line.partition('=')[0] not in updates]
    lines += [key + '=' + json.dumps(value) for key, value in updates.items()]
    (payload / 'api.env.candidate').write_text('\n'.join(lines) + '\n')
    (payload / 'api.env.candidate').chmod(0o600)
    changed = ['app/config.py', 'app/main.py', 'app/work3200.py', 'app/api/hardware.py']
    record = {'previous': str(previous), 'candidate': str(candidate),
              'api_env_before_sha256': digest(payload / 'api.env.before'),
              'files': {item: digest(backend / item) for item in changed}}
    (payload / 'deployment.json').write_text(json.dumps(record, indent=2))
    (candidate / 'work3200-delta.json').write_text(json.dumps({k: v for k, v in record.items() if k != 'api_env_before_sha256'}, indent=2))
    validate(payload)


def validate(payload):
    record = json.loads((payload / 'deployment.json').read_text())
    candidate = Path(record['candidate']); backend = candidate / 'services/backend'
    for name, sha in record['files'].items():
        assert digest(backend / name) == sha
    # Test-only pure Python packages can live here when the production venv omits pytest.
    # Isolated fixtures create their own temporary SQLite DB, not the production DB.
    env = {**os.environ, 'PYTHONPATH': str(payload / 'test-support')}
    with (payload / 'stage-tests.log').open('w') as log:
        subprocess.run([str(backend / '.venv/bin/python'), '-m', 'pytest',
                        'tests/test_work3200_auth.py', 'tests/test_accounts.py',
                        'tests/test_session_auth.py', 'tests/test_health.py', '-q',
                        '--junitxml=' + str(payload / 'tests.xml')],
                       cwd=backend, env=env, stdout=log, stderr=log, check=True)
    record['stage_passed'] = True
    (payload / 'deployment.json').write_text(json.dumps(record, indent=2))
    print(json.dumps({'stage_passed': True, 'candidate': str(candidate)}))


def switch(path):
    pending = ROOT / 'current.work3200-next'
    assert not pending.exists() and not pending.is_symlink()
    pending.symlink_to(path)
    pending.replace(ROOT / 'current')


def activate(payload):
    record = json.loads((payload / 'deployment.json').read_text())
    assert record['stage_passed'] is True
    assert str((ROOT / 'current').resolve()) == record['previous']
    assert digest(CONFIG) == record['api_env_before_sha256'], 'Live config changed; inspect before activation'
    candidate = Path(record['candidate']); backend = candidate / 'services/backend'
    for name, sha in record['files'].items():
        assert digest(backend / name) == sha
    try:
        shutil.copy2(payload / 'api.env.candidate', CONFIG)
        switch(candidate)
        subprocess.run(['systemctl', 'restart', 'remember-me@api'], check=True)
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8877/ready', timeout=2) as response:
                    if response.status == 200:
                        record['activated'] = True
                        (payload / 'deployment.json').write_text(json.dumps(record, indent=2))
                        print('Candidate API ready; run authenticated public-route and APK checks.')
                        return
            except Exception:
                time.sleep(1)
        raise RuntimeError('Candidate readiness timeout')
    except Exception:
        shutil.copy2(payload / 'api.env.before', CONFIG)
        switch(Path(record['previous']))
        subprocess.run(['systemctl', 'restart', 'remember-me@api'], check=True)
        raise


def rollback(payload):
    record = json.loads((payload / 'deployment.json').read_text())
    assert str((ROOT / 'current').resolve()) == record['candidate']
    shutil.copy2(payload / 'api.env.before', CONFIG)
    switch(Path(record['previous']))
    subprocess.run(['systemctl', 'restart', 'remember-me@api'], check=True)
    print('Previous API release and configuration restored; database and recordings untouched.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'validate', 'activate', 'rollback'])
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--name', default='paired-work3200-20261016')
    args = parser.parse_args()
    assert os.geteuid() == 0 and args.name.startswith('paired-') and '/' not in args.name
    if args.action == 'stage': stage(args.payload.resolve(), args.name)
    elif args.action == 'validate': validate(args.payload.resolve())
    elif args.action == 'activate': activate(args.payload.resolve())
    else: rollback(args.payload.resolve())

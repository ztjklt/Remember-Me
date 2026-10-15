"""ECS-only additive release switch after isolated restore, PG tests and smoke.

Run as root with an immutable candidate, explicit commit, and private evidence
paths. Never prints environment values. Does not modify network or registration.
Keeps the migrated database on application rollback; never overwrites recordings.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path('/opt/remember-me')
CONFIG = Path('/etc/remember-me')
SERVICES = ['ai', 'worker', 'profile', 'api']


def release_updates(name, commit, transcript_correction=False):
    updates = {'REMEMBER_RELEASE_ID': commit}
    if name == 'ai':
        updates['AI_PROFILE_VERIFY_CANDIDATES'] = 'true'
    else:
        updates['REMEMBER_AI_TIMEOUT_SECONDS'] = '120'
    if transcript_correction and name in ('api', 'worker'):
        updates['REMEMBER_TRANSCRIPT_CORRECTION_ENABLED'] = 'true'
    return updates


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def swap(target):
    pending = ROOT / 'current.twin-next'
    if pending.exists() or pending.is_symlink():
        raise RuntimeError('Inspect the existing pending release link first')
    pending.symlink_to(target)
    pending.replace(ROOT / 'current')


def validate_smoke(smoke, commit):
    """Evidence-mode synthesis is valid; do not require a single-quote label.

    This release probe asks the fixed demonstration year-correction question.
    Require its complete positive/negative source clause, not just HTTP success
    or the presence of a year in an otherwise unsupported response.
    """
    assert smoke['service_info']['release_id'] == commit
    for name, mode in [('persona', 'persona'), ('evidence', 'evidence')]:
        answer = smoke[name]
        assert answer['mode'] == mode and answer['stale'] is False
        assert answer['model_version'] == 'Deepseek-v4-flash'
        assert answer['answer_id'] and answer['source_version']
        assert answer['response_type'] in ('ORIGINAL', 'SIMULATION')
        assert answer['answer'].strip() and answer['evidence']
        assert all(e['evidence_id'] and e['episode_id'] and e['excerpt'].strip()
                   for e in answer['evidence'])
    evidence = smoke['evidence']
    assert evidence['question'] == '第一次独立跑十二路是哪一年？'
    correction = '第一次独立开12路是1987年，不是1986年。'
    assert correction in evidence['answer']
    assert any(correction in e['excerpt'] for e in evidence['evidence'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--postgres-xml', type=Path, required=True)
    p.add_argument('--smoke', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--voice-config', type=Path)
    p.add_argument('--enable-transcript-correction', action='store_true')
    args = p.parse_args()
    candidate = args.candidate.resolve()
    assert os.geteuid() == 0 and re.fullmatch(r'[a-f0-9]{40}', args.commit)
    assert candidate.parent == ROOT / 'releases' and candidate.name.startswith('paired-')
    manifest = json.loads((candidate / 'deployment-source.json').read_text())
    assert manifest['commit'] == args.commit
    for relative, digest in manifest['files'].items():
        path = (candidate / relative).resolve()
        assert path.is_relative_to(candidate) and path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, relative
    proof = json.loads(args.evidence.read_text())
    assert proof['commit'] == args.commit
    assert proof['source_manifest_sha256'] == hashlib.sha256((candidate/'deployment-source.json').read_bytes()).hexdigest()
    assert proof['postgres_sha256'] == hashlib.sha256(args.postgres_xml.read_bytes()).hexdigest()
    assert proof['smoke_sha256'] == hashlib.sha256(args.smoke.read_bytes()).hexdigest()
    assert proof['tests_completed_with_unchanged_source'] is True
    suites = list(ET.parse(args.postgres_xml).getroot().iter('testsuite'))
    assert suites and sum(int(s.get('tests', 0)) for s in suites) >= 630
    assert not sum(int(s.get(k, 0)) for s in suites for k in ['errors', 'failures', 'skipped'])
    smoke = json.loads(args.smoke.read_text())
    validate_smoke(smoke, args.commit)
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url
    production = make_url(dotenv_values(CONFIG/'api.env')['REMEMBER_DATABASE_URL'])
    assert production.database == 'remember_me' and not production.host
    voice = {}
    if args.voice_config:
        voice=json.loads(args.voice_config.read_text())
        assert set(voice)=={'REMEMBER_VOICE_SYNTHETIC_BACKEND','REMEMBER_XIAOMI_VOICE_API_KEY','REMEMBER_A01_VOICE_SUBJECT_ID','REMEMBER_A01_VOICE_REFERENCE_PATH'}
        assert voice['REMEMBER_VOICE_SYNTHETIC_BACKEND']=='xiaomi'
        assert all(isinstance(v,str) and v and '\n' not in v and '\r' not in v for v in voice.values())
        assert Path(voice['REMEMBER_A01_VOICE_REFERENCE_PATH']).resolve().is_relative_to('/var/lib/remember-me')
    previous = (ROOT / 'current').resolve()
    assert previous != candidate
    # Older Git snapshots contain this Windows-authored script with CRLF.
    # Execute a normalized copy via stdin, keeping the candidate manifest intact.
    backup_script = (candidate / 'tools/round_two/backup_ecs_paired.sh').read_text()
    run(['bash', '-n'], input=backup_script, text=True, capture_output=True)
    snapshot = None
    switched = False
    config_changed = False
    try:
        # Finish active API requests before the consistent database/audio backup.
        run(['systemctl', 'stop', *['remember-me@' + n for n in ['api', 'worker', 'profile']]])
        result = run(['bash', '-s', '--', str(candidate)], input=backup_script, capture_output=True, text=True)
        check = json.loads(result.stdout.strip().splitlines()[-1])
        snapshot = Path(check['snapshot'])
        saved = snapshot / 'switch-config'
        saved.mkdir(mode=0o700)
        for name in SERVICES:
            shutil.copy2(CONFIG / (name + '.env'), saved / (name + '.env'))
        migrate = '''import os,subprocess,pwd
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
env={**os.environ,**{k:v for k,v in dotenv_values('/etc/remember-me/api.env').items() if v is not None}}
url=make_url(env['REMEMBER_DATABASE_URL']);identity={}
if url.drivername.startswith('postgresql') and not url.host and not url.password:
    user=pwd.getpwnam(url.username);identity={'user':user.pw_uid,'group':user.pw_gid,'extra_groups':[]}
subprocess.run(['.venv/bin/python','-m','alembic','upgrade','head'],env=env,check=True,**identity)
'''
        with (snapshot / 'production-migration.log').open('w') as log:
            run([str(candidate / 'services/backend/.venv/bin/python'), '-c', migrate], cwd=candidate / 'services/backend', stdout=log, stderr=log)
        config_changed = True  # All four original files were copied successfully.
        for name in SERVICES:
            path = CONFIG / (name + '.env')
            updates = release_updates(name, args.commit, args.enable_transcript_correction)
            if name=='api':
                updates.update(voice)
            lines = [line for line in path.read_text().splitlines() if line.split('=', 1)[0] not in updates]
            temp = path.with_suffix('.twin-next')
            temp.write_text('\n'.join(lines + [k + '=' + v for k, v in updates.items()]) + '\n')
            temp.chmod(0o600)
            temp.replace(path)
        swap(candidate)
        switched = True
        for name in SERVICES:
            run(['systemctl', 'restart', 'remember-me@' + name])
        for attempt in range(45):
            try:
                ready = json.load(urllib.request.urlopen('http://127.0.0.1:8877/ready', timeout=3))
                info = json.load(urllib.request.urlopen('http://127.0.0.1:8877/api/v1/service-info', timeout=3))
                assert ready['status'] == 'ready' and info['release_id'] == args.commit
                assert not info['registration_allowed'] and info['sharing_invitations']
                for name in SERVICES:
                    run(['systemctl', 'is-active', '--quiet', 'remember-me@' + name])
                break
            except Exception:
                if attempt == 44:
                    raise
                time.sleep(1)
        result = dict(previous=str(previous), release=str(candidate), commit=args.commit,
                      snapshot=str(snapshot), ready=ready, service_info=info, switched=True)
        (snapshot / 'switch-result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    except Exception:
        recovery_errors = []
        def recover(label, action):
            try:
                action()
            except Exception as error:
                recovery_errors.append({'step':label,'error_type':type(error).__name__})
        recover('stop', lambda: run(['systemctl', 'stop', *['remember-me@' + n for n in SERVICES]]))
        if config_changed:
            for name in SERVICES:
                recover('config-'+name, lambda name=name: shutil.copy2(snapshot / 'switch-config' / (name + '.env'), CONFIG / (name + '.env')))
        if switched:
            recover('release-link', lambda: swap(previous))
        # Even a failed stop or one failed config restoration must not skip this.
        recover('start', lambda: run(['systemctl', 'start', *['remember-me@' + n for n in SERVICES]]))
        if snapshot:
            (snapshot / 'application-rollback.json').write_text(json.dumps({'previous':str(previous),'database_downgraded':False,'recovery_errors':recovery_errors}))
        if recovery_errors:
            print(json.dumps({'rollback_incomplete':recovery_errors}))
        raise


if __name__ == '__main__':
    main()

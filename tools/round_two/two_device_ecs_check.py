"""Exact internal APK, two emulator data stores, direct ECS IP HTTPS.

Requires the completed dedicated ECS smoke corpus. No new model requests,
no ADB reverse/SSH transport, no account resets or fixture database writes.
Only the synthetic reply story and its designated reader are affected.
"""
import argparse
import hashlib
import json
import re
import shlex
import ssl
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'services/backend/var/paired-delivery'
ADB = 'D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe'
DEVICES = {'owner': 'emulator-5554', 'reader': 'emulator-5556'}
URL = 'https://39.108.183.47'


def verify_instrumentation(log):
    codes = [int(line.split(':', 1)[1]) for line in log.splitlines()
             if line.startswith('INSTRUMENTATION_STATUS_CODE:')]
    if codes != [1, 0] or 'OK (1 test)' not in log:
        raise RuntimeError('Target test did not explicitly pass; skipped tests do not count')


def cleanup_inputs(adb, devices, local_file):
    errors = []
    for device in devices:
        try:
            adb(device, 'shell', 'rm', '-f', '/data/local/tmp/remember-paired-device.json')
        except Exception:
            errors.append('Could not clear device input: ' + device)
    try:
        local_file.unlink(missing_ok=True)
    except Exception:
        errors.append('Could not clear local private input')
    return errors


def finish_report(report, adb, devices, local_file, save):
    errors = cleanup_inputs(adb, devices, local_file)
    if errors:
        report['cleanup_errors'] = errors
        report['complete'] = False
        try:
            save()
        except Exception:
            pass  # No earlier on-disk record has complete=true.
        if 'error' not in report:
            raise RuntimeError('Device checks completed but private input cleanup failed')
    elif report.get('phases_complete') and 'error' not in report:
        report['complete'] = True
        save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-name', default='two-device-ecs')
    label = parser.parse_args().run_name
    if not re.fullmatch(r'two-device-ecs(?:-[a-z0-9]+)?', label):
        raise ValueError('Use a distinct simple ECS run label')
    report_path = OUT / (label + '-result.json')
    if report_path.exists():
        raise RuntimeError('Existing ECS UI history must be inspected, not overwritten')
    accounts = json.loads((OUT / 'ecs-accounts.json').read_text('utf8'))
    smoke = json.loads((OUT / 'ecs-pair-smoke.json').read_text('utf8'))
    assert smoke.get('finished') and smoke['service_info']['sharing_invitations']
    for role in DEVICES:
        assert accounts[role]['username'] == 'paired_' + role + '_20261009'
    subject = accounts['owner']['subject_id']
    episode = smoke['episodes']['reply']['episode_id']
    apk = OUT / 'remember-me-0.7.0-internal-candidate.apk'
    manifest = json.loads((OUT / 'apk-manifest.json').read_text('utf8'))
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == manifest['sha256']
    report = {'server': URL, 'devices': DEVICES, 'physical_phone': False,
              'ecs': True, 'new_asr': False, 'new_model_calls': False,
              'adb_business_forwarding': False, 'apk_sha256': manifest['sha256'], 'phases': []}

    def save():
        temp = report_path.with_suffix('.tmp')
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        temp.replace(report_path)

    def adb(device, *args):
        return subprocess.run([ADB, '-s', device, *args], capture_output=True, check=True, timeout=180)

    # Fail closed if leftover forwarding could make the network result ambiguous.
    for device in DEVICES.values():
        assert not adb(device, 'reverse', '--list').stdout.strip()
        package_path = adb(device, 'shell', 'pm', 'path', 'me.remember.app.internal').stdout.decode().strip()
        assert package_path.startswith('package:/data/app/') and '\n' not in package_path
        installed_hash = adb(device, 'shell', 'sha256sum ' + shlex.quote(package_path[8:])).stdout.decode().split()[0]
        assert installed_hash == manifest['sha256'], 'Installed APK does not match the frozen candidate: ' + device
        report.setdefault('installed_apk_sha256', {})[device] = installed_hash
    context = ssl.create_default_context(cafile=str(ROOT / 'apps/android/app/src/internal/res/raw/remember_ecs_ip_demo.pem'))
    with httpx.Client(base_url=URL, verify=context, trust_env=False, timeout=60) as client:
        info = client.get('/api/v1/service-info'); info.raise_for_status()
        report['service_info'] = info.json()
        assert info.json()['release_id'] == smoke['service_info']['release_id']
        account = accounts['owner']
        login = client.post('/api/v1/accounts/login', json={k: account[k] for k in ['username', 'password']})
        login.raise_for_status(); client.headers['Authorization'] = 'Bearer ' + login.json()['actor_token']
        root = '/api/v1/workbench/subjects/' + subject
        try:
            grants = client.get(root + '/grants'); grants.raise_for_status()
            for grant in grants.json()['items']:
                if grant['episode_id'] == episode and grant['reader_actor_id'] == accounts['reader']['actor_id'] and not grant.get('revoked_at'):
                    client.delete(root + '/grants/' + grant['grant_id']).raise_for_status()
        finally:
            client.post('/api/v1/accounts/logout').raise_for_status()
    save()
    try:
        for cycle in range(1, 4):
            invitation = {}
            for role, phase in [('owner', 'create'), ('reader', 'claim'), ('owner', 'approve'),
                                ('reader', 'play'), ('owner', 'revoke'), ('reader', 'verify_revoked')]:
                device = DEVICES[role]
                config = {'url': URL, 'subject': subject, 'episode': episode,
                          'account': accounts[role], 'phase': phase, **invitation}
                temp = OUT / 'paired-ecs-device-input.json'
                temp.write_text(json.dumps(config, ensure_ascii=False), encoding='utf8')
                remote = '/sdcard/Android/data/me.remember.app.internal/files/'
                # Require new outputs even when a prior test was skipped or crashed.
                for output in ['paired-device-result.json', 'paired-device.png']:
                    adb(device, 'shell', 'rm', '-f', remote + output)
                    adb(device, 'shell', 'test', '!', '-e', remote + output)
                adb(device, 'push', str(temp), '/data/local/tmp/remember-paired-device.json')
                execution = adb(device, 'shell', 'am', 'instrument', '-w', '-r', '-e', 'class',
                                'me.remember.app.PairedDevicesLiveTest',
                                'me.remember.app.internal.test/androidx.test.runner.AndroidJUnitRunner')
                name = f'{label}-{cycle}-{phase}'
                log = (execution.stdout + execution.stderr).decode('utf8', 'replace')
                (OUT / (name + '.log')).write_text(log, encoding='utf8')
                verify_instrumentation(log)
                adb(device, 'pull', remote + 'paired-device-result.json', str(OUT / (name + '.json')))
                adb(device, 'pull', remote + 'paired-device.png', str(OUT / (name + '.png')))
                data = json.loads((OUT / (name + '.json')).read_text('utf8'))
                assert data['server'] == URL and data['phase'] == phase
                if phase == 'create':
                    invitation = {k: data[k] for k in ['code', 'invitation_id']}
                report['phases'].append({'cycle': cycle, 'device': device, 'phase': phase, 'passed': True})
                save(); print(name, 'passed', flush=True)
        report['phases_complete'] = True; save()
    except Exception as exc:
        report['error'] = str(exc); save(); raise
    finally:
        finish_report(report, adb, DEVICES.values(), OUT / 'paired-ecs-device-input.json', save)


if __name__ == '__main__':
    main()

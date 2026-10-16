"""Build with the EXISTING internal signing identity; never create another key.

Pass --signing-dir PRIVATE_DIRECTORY. Passwords use only the child environment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--signing-dir', type=Path, required=True)
    p.add_argument('--toolchain', type=Path, default=Path('D:/codex_work/remember-me-toolchain'))
    p.add_argument('--output', type=Path, default=ROOT/'services/backend/var/cloud-rollout-20261013')
    p.add_argument('--instrumentation', action='store_true')
    p.add_argument('--jdk', type=Path, default=Path(os.environ.get('JAVA_HOME', '')))
    p.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME', '')))
    p.add_argument('--gradle', type=Path, help='Installed Gradle launcher; otherwise use the project wrapper')
    p.add_argument('--soundcore-sdk', type=Path, help='Private Soundcore 1.3.02 AAR, never copied into Git')
    p.add_argument('--offline', action='store_true')
    args = p.parse_args()
    changes = subprocess.check_output(['git','diff','HEAD','--name-only','--','apps/android'],cwd=ROOT,text=True).strip()
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard','--','apps/android'],cwd=ROOT,text=True).splitlines()
    source_suffixes={'.kt','.java','.kts','.xml','.toml','.properties','.aar','.jar'}
    if changes or any(Path(path).suffix in source_suffixes for path in untracked):
        raise SystemExit('Commit the Android source before building a versioned delivery APK.')
    key = args.signing_dir/'remember-internal.p12'
    sign = args.signing_dir/'internal-signing.json'
    if not key.is_file() or not sign.is_file():
        raise SystemExit('Existing signing key and its private config required; nothing generated.')
    build = (ROOT/'apps/android/app/build.gradle.kts').read_text('utf8')
    version = re.search(r'versionName = "([0-9.]+(?:-[a-z]+)*-internal)"', build).group(1)
    version_code = int(re.search(r'versionCode = (\d+)', build).group(1))
    jdk = args.jdk if (args.jdk/'bin/java.exe').is_file() else args.toolchain/'jdk/jdk-17.0.20.1+1'
    sdk = args.sdk if (args.sdk/'build-tools/35.0.0').is_dir() else args.toolchain/'sdk'
    env = {**os.environ, 'JAVA_HOME':str(jdk), 'ANDROID_HOME':str(sdk),
           'GRADLE_USER_HOME':os.environ.get('GRADLE_USER_HOME', str(args.toolchain/'gradle')),
           'REMEMBER_INTERNAL_KEYSTORE':str(key.resolve()),
           'REMEMBER_INTERNAL_STORE_PASSWORD':json.loads(sign.read_text('utf8'))['password']}
    args.output.mkdir(parents=True, exist_ok=True)
    tasks = ['assembleInternal']
    if args.soundcore_sdk:
        if not args.soundcore_sdk.is_file():
            raise SystemExit('Private SDK archive does not exist.')
        tasks += [f'-PrememberSoundcoreSdk={args.soundcore_sdk.resolve().as_posix()}', '-PrememberRequireHardwareSdk=true']
    if '-device-' in version and not args.soundcore_sdk:
        raise SystemExit('Device delivery requires --soundcore-sdk; refusing a non-device APK.')
    if args.instrumentation:
        tasks += ['assembleInternalAndroidTest', '-PrememberTestBuildType=internal']
    with (args.output/'internal-build.log').open('w', encoding='utf8') as log:
        subprocess.run([str(args.gradle or ROOT/'apps/android/gradlew.bat'), '-p', str(ROOT/'apps/android'),
                        *tasks, *(['--offline'] if args.offline else []), '--console=plain'], env=env, stdout=log, stderr=log, check=True)
    apk = ROOT/'apps/android/app/build/outputs/apk/internal/app-internal.apk'
    dest = args.output/('remember-me-'+version+'.apk')
    if dest.exists():
        raise SystemExit('Output exists; choose a new output directory to preserve the prior candidate.')
    dest.write_bytes(apk.read_bytes())
    signer = sdk/'build-tools/35.0.0/apksigner.bat'
    result = subprocess.run([str(signer), 'verify', '--verbose', '--print-certs', str(dest)],
                            env=env, capture_output=True, text=True, check=True)
    (args.output/'signature.txt').write_text(result.stdout, encoding='utf8')
    certificate = re.search(r'Signer #1 certificate SHA-256 digest: ([a-f0-9]+)',result.stdout).group(1)
    expected = '9c99b41e65d934bd0dee3b111543266404b49fb7d799d43c23eb82f46d8e2f75'
    if certificate != expected:
        raise SystemExit('Signing certificate differs from the published internal APK; do not publish.')
    aapt = sdk/'build-tools/35.0.0/aapt.exe'
    badging = subprocess.check_output([str(aapt),'dump','badging',str(dest)],env=env,text=True)
    assert "name='me.remember.app.internal'" in badging
    assert f"versionCode='{version_code}'" in badging and f"versionName='{version}'" in badging
    assert 'application-debuggable' not in badging
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report = dict(apk=dest.name, sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), bytes=dest.stat().st_size,
                  version_name=version, version_code=version_code, source_commit=commit,
                  signing_certificate_sha256=certificate, server='https://39.108.183.47', debuggable=False,
                  soundcore_sdk_included=args.soundcore_sdk is not None,
                  soundcore_sdk_sha256=hashlib.sha256(args.soundcore_sdk.read_bytes()).hexdigest() if args.soundcore_sdk else None,
                  tls_verification='IP-specific test certificate; no cleartext',
                  delivery_status='candidate; cloud and emulator acceptance recorded separately')
    (args.output/'apk-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

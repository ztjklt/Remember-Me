"""Build the IP HTTPS internal APK with a persistent, ignored signing key.
No model credentials are read. Signing passwords never appear in argv or logs.
"""
import hashlib,json,os,secrets,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'services/backend/var/paired-delivery';OUT.mkdir(exist_ok=True)
TOOL=Path('D:/codex_work/remember-me-toolchain')
JDK=TOOL/'jdk/jdk-17.0.20.1+1'
sign=OUT/'internal-signing.json';key=OUT/'remember-internal.p12'
if not sign.exists():
    if key.exists():raise SystemExit('Signing key exists without its local config; do not replace it.')
    sign.write_text(json.dumps({'password':secrets.token_urlsafe(32)}),encoding='utf8')
env={**os.environ,'JAVA_HOME':str(JDK),'ANDROID_HOME':str(TOOL/'sdk'),'GRADLE_USER_HOME':str(TOOL/'gradle'),
    'REMEMBER_INTERNAL_KEYSTORE':str(key),'REMEMBER_INTERNAL_STORE_PASSWORD':json.loads(sign.read_text('utf8'))['password']}
with (OUT/'internal-build.log').open('w',encoding='utf8') as log:
    if not key.exists():
        subprocess.run([str(JDK/'bin/keytool.exe'),'-genkeypair','-keystore',str(key),'-storetype','PKCS12',
            '-storepass:env','REMEMBER_INTERNAL_STORE_PASSWORD','-keypass:env','REMEMBER_INTERNAL_STORE_PASSWORD',
            '-alias','remember-internal','-keyalg','RSA','-keysize','3072','-validity','3650','-dname','CN=Remember Me Internal Test'],
            env=env,stdout=log,stderr=log,check=True)
    subprocess.run([str(ROOT/'apps/android/gradlew.bat'),'-p',str(ROOT/'apps/android'),'testDebugUnitTest','assembleInternal',
        '--offline','--console=plain'],env=env,stdout=log,stderr=log,check=True)
src=ROOT/'apps/android/app/build/outputs/apk/internal/app-internal.apk'
dest=OUT/'remember-me-0.7.0-internal-candidate.apk';dest.write_bytes(src.read_bytes())
report={'apk':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bytes':dest.stat().st_size,
    'server':'https://39.108.183.47','debuggable':False,'tls_verification':'IP-specific test certificate, no cleartext',
    'delivery_status':'candidate; deployment and device acceptance are separate'}
(OUT/'apk-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))

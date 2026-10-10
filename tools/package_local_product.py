"""Assemble a local test delivery from an explicit source allowlist; no var/.env.

Provider credentials and all personal/test runtime identities are excluded.
This is source + APK, not an offline Python/model runtime or public deployment.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/remember-me'
APK=ROOT/'apps/android/app/build/outputs/apk/debug/app-debug.apk'


def main():
    from dotenv import dotenv_values
    if not APK.exists():raise SystemExit('Build the Android debug APK first.')
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    prefixes=('services/backend/','services/ai-core/','packages/contracts/','assets/brand/forget-me-not/',
              'docs/agent-loop/','docs/architecture/','tools/mobile_eval/')
    exact={'tools/start_product.py','tools/Start-RememberMe.ps1','tools/package_local_product.py','.gitignore','README.md'}
    files=[]
    for name in names:
        path=ROOT/name
        if not name or not path.is_file() or not (name.startswith(prefixes) or name in exact):continue
        if any(x in path.parts for x in ('var','.venv','__pycache__','node_modules')):raise RuntimeError('Runtime path in allowlist: '+name)
        if path.name.startswith('.env') and not path.name.endswith('.example'):raise RuntimeError('Private config in allowlist: '+name)
        files.append(path)
    credentials=[]
    for directory in (ROOT/'services/backend',ROOT/'services/ai-core'):
        for path in directory.glob('.env*'):
            if path.name.endswith('.example'):continue
            credentials.extend(v.encode() for k,v in dotenv_values(path).items() if v and len(v)>16 and any(s in k.upper() for s in ('API_KEY','TOKEN','PASSWORD')))
    for path in files:
        data=path.read_bytes()
        if any(key in data for key in credentials):raise RuntimeError('Credential scan failed: '+str(path.relative_to(ROOT)))
    # APK files are already compressed; inspect their uncompressed payloads too.
    with zipfile.ZipFile(APK) as package:
        for info in package.infolist():
            if any(key in package.read(info) for key in credentials):raise RuntimeError('Credential scan failed inside APK')
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'remember-me-local-debug.apk'
    shutil.copy2(APK,target)
    archive=OUT/'remember-me-local-kit.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files:z.write(path,path.relative_to(ROOT).as_posix())
        z.write(target,'output/remember-me/'+target.name,compress_type=zipfile.ZIP_STORED)
    manifest={'kind':'Local Android APK and server source; runtime dependencies configured separately',
              'provider_keys_included':False,'runtime_data_included':False,'source_files':len(files),
              'artifacts':[{'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (target,archive)]}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()

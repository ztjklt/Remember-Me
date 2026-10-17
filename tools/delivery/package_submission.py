"""Export an immutable Git commit, verify every file, and make a Python review bundle.

No workspace credentials, untracked files, databases or private runtime data are
implicitly included. A manifest reports omissions and exact file hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
TEXT_EXT = {'.py', '.kt', '.kts', '.js', '.mjs', '.json', '.md', '.yml', '.yaml',
            '.toml', '.lock', '.sh', '.ps1', '.html', '.css', '.txt', '.xml', '.patch'}


def local_secret_values():
    """Compare local credential values without disclosing them in logs or artifacts."""
    values = set()
    for service in ('backend', 'ai-core'):
        for file in (ROOT / 'services' / service).glob('.env*'):
            if file.name.endswith('.example') or not file.is_file():
                continue
            for line in file.read_text(encoding='utf-8-sig').splitlines():
                match = re.match(r'\s*(?:export\s+)?([\w]+)\s*=\s*(.+)', line)
                if not match or not re.search('KEY|TOKEN|PASSWORD|SECRET', match[1], re.I):
                    continue
                value = match[2].strip().strip('\"\'')
                if len(value) >= 12 and not value.startswith(('#', 'YOUR_', '<')):
                    values.add(value.encode())
    return values


def inspect(name, data, secrets):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name:
        raise ValueError('Unsafe archive path: ' + name)
    if p.name == '.env' or (p.name.startswith('.env.') and not p.name.endswith('.example')):
        raise ValueError('Private environment file: ' + name)
    if p.suffix.lower() in {'.jks', '.keystore', '.p12', '.dump', '.sqlite', '.sqlite3', '.db'}:
        raise ValueError('Private runtime or signing file: ' + name)
    if p.suffix.lower() in TEXT_EXT or p.name.endswith('.example'):
        if any(secret in data for secret in secrets):
            raise ValueError('Configured credential found in ' + name)
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', data):
            raise ValueError('Private key found in ' + name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--ref', default='HEAD')
    args = parser.parse_args()
    commit = subprocess.check_output(['git', 'rev-parse', args.ref + '^{commit}'], cwd=ROOT, text=True).strip()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    complete = out / 'remember-me-complete-source.zip'
    backend = out / 'remember-me-python-backend.zip'
    subprocess.run(['git', 'archive', '--format=zip', '-o', str(complete), commit], cwd=ROOT, check=True)
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '-z', commit], cwd=ROOT).decode().split('\0')
    expected = {n for n in names if n}
    manifest = {'source_commit': commit, 'scope': 'all tracked files in immutable commit',
                'excludes': ['untracked work in progress (separate patch)', 'credentials', 'runtime databases',
                             'private audio', 'build caches', 'external vendor SDK archive and model weights'],
                'files': [], 'archives': []}
    secrets = local_secret_values()
    with zipfile.ZipFile(complete) as src, zipfile.ZipFile(backend, 'w', zipfile.ZIP_DEFLATED) as dst:
        actual = {i.filename for i in src.infolist() if not i.is_dir()}
        if actual != expected:
            raise ValueError('Git/archive inventory mismatch')
        if src.testzip() is not None:
            raise ValueError('Full archive CRC check failed')
        for name in sorted(actual):
            data = src.read(name)
            inspect(name, data, secrets)
            manifest['files'].append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            if (name.startswith(('services/', 'packages/', 'infra/', 'tools/', 'docs/submission/'))
                    or name in {'SUBMISSION.md', 'AGENTS.md', 'CONTRIBUTING.md'}):
                dst.writestr(src.getinfo(name), data)
    with zipfile.ZipFile(backend) as z:
        if z.testzip() is not None:
            raise ValueError('Python archive CRC check failed')
    for path in (complete, backend):
        manifest['archives'].append({'file': path.name, 'bytes': path.stat().st_size,
                                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest['verification'] = 'all Git paths present; archive CRC and configured credential scan passed'
    (out / 'source-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'commit': commit, 'files': len(expected), 'archives': manifest['archives']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

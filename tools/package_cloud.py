"""Source-only Linux release, with no local database, identities or credentials."""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('services/backend/', 'services/ai-core/', 'packages/contracts/',
            'assets/brand/forget-me-not/', 'infra/aws/')
EXCLUDED = {'var', '.venv', '__pycache__', 'node_modules', 'tests'}
INFRA_FILES = {'pilot.yaml', 'Caddyfile', 'README.md', 'prepare-host.sh',
               'activate.sh', 'backup.sh', 'run-service.sh',
               'remember-me@.service', 'remember-me-proxy.service',
               'backend.env.example', 'ai.env.example', 'proxy.env.example'}


def source_allowed(path):
    """Only known runtime source trees, static assets and named templates."""
    name = path.as_posix()
    if name.startswith('infra/aws/'):
        return path.parent.as_posix() == 'infra/aws' and path.name in INFRA_FILES
    for service in ('services/backend', 'services/ai-core'):
        if path.parent.as_posix() == service:
            return path.name in {'pyproject.toml', 'uv.lock', 'alembic.ini',
                                 'README.md', '.env.example', '.env.workbench.example'}
        if name.startswith(service+'/app/'):
            return path.suffix in {'.py', '.json', '.js', '.css', '.html', '.svg', '.png'}
        if name.startswith(service+'/migrations/'):
            return path.suffix in {'.py', '.mako'}
    if name.startswith('packages/contracts/schemas/'):
        return path.suffix == '.json'
    if name.startswith('assets/brand/forget-me-not/'):
        return path.suffix in {'.png', '.jpg', '.svg', '.js', '.css', '.json', '.md'}
    return False


def build(root, names, output, *, secrets=()):
    root, output = Path(root).resolve(), Path(output)
    files = []
    for name in sorted(set(names)):
        if not name:
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            raise ValueError('Unsafe archive path')
        if not name.startswith(PREFIXES) or EXCLUDED.intersection(path.parts):
            continue
        if not source_allowed(path):
            continue
        file = root / name
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            raise ValueError('Unsafe source path')
        if not file.is_file():
            continue
        data = file.read_bytes()
        if any(secret and secret in data for secret in secrets):
            raise ValueError('Source contains a configured credential')
        files.append((name, data))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.tmp')
    with tarfile.open(temporary, 'w:gz') as archive:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith('.sh') else 0o644
            archive.addfile(info, io.BytesIO(data))
    temporary.replace(output)
    return {'files': len(files), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'bytes': output.stat().st_size,
            'selection_policy': 'runtime-source-static-assets-named-templates-v2',
            'configured_credential_scan': 'passed',
            'environment_and_database_files': 'excluded_by_allowlist'}


def main():
    from dotenv import dotenv_values
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others',
                                     '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    credentials = []
    for directory in (ROOT/'services/backend', ROOT/'services/ai-core'):
        for path in directory.glob('.env*'):
            if not path.name.endswith('.example'):
                credentials.extend(v.encode() for k, v in dotenv_values(path).items()
                    if v and len(v) > 12 and any(term in k.upper() for term in ('KEY', 'TOKEN', 'PASSWORD')))
    target = ROOT/'output/aws/remember-me-cloud.tar.gz'
    result = build(ROOT, names, target, secrets=credentials)
    result['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    result['includes_working_tree'] = True
    target.with_suffix('.manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

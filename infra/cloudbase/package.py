"""Make a minimal deployable source context; never include a whole checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FILES = ['services/backend/pyproject.toml','services/backend/uv.lock',
    'services/backend/alembic.ini','services/ai-core/pyproject.toml','services/ai-core/uv.lock']
DIRECTORIES = ['services/backend/app','services/backend/migrations','services/ai-core/app',
    'services/ai-core/fixtures','packages/contracts/schemas','infra/cloudbase/runtime']


def package(destination):
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT / 'build') or destination == ROOT / 'build':
        raise ValueError('Use a new dedicated directory below this checkout’s ignored build/.')
    destination.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / file for file in FILES]
    for directory in DIRECTORIES:
        sources.extend(path for path in (ROOT / directory).rglob('*') if path.is_file())
    hashes = {}
    config=json.loads((ROOT/'infra/cloudbase/voiceprint-model.json').read_text())
    cached=ROOT/config['cache_path']
    if not cached.is_file() or hashlib.sha256(cached.read_bytes()).hexdigest()!=config['sha256']:
        raise ValueError('Download and verify the pinned public voiceprint model in build/voiceprint-models before packaging.')
    target=destination/'models'/config['model'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(cached,target)
    hashes[str(target.relative_to(destination))]=config['sha256']
    for source in sorted(set(sources)):
        relative = source.relative_to(ROOT)
        if (source.is_symlink() or '__pycache__' in relative.parts or
            any(part.startswith('.env') or part in {'var','.venv'} for part in relative.parts) or
            source.suffix in {'.pyc','.pem','.key','.p12'}):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    for file, target in [('Dockerfile','Dockerfile'),('Dockerfile.dockerignore','.dockerignore')]:
        shutil.copyfile(ROOT / 'infra/cloudbase' / file, destination / target)
        hashes[target] = hashlib.sha256((destination / target).read_bytes()).hexdigest()
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    (destination / 'source-manifest.json').write_text(json.dumps(
        {'base_revision':revision, 'files':hashes},ensure_ascii=False,indent=2)+'\n')
    archive = destination.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz') as output:
        for source in sorted(destination.rglob('*')):
            if source.is_file(): output.add(source,arcname=str(source.relative_to(destination)))
    with zipfile.ZipFile(destination.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as output:
        for source in sorted(destination.rglob('*')):
            if source.is_file(): output.write(source,arcname=str(source.relative_to(destination)))
    print(f'Prepared {len(hashes)} source files: {destination.with_suffix(".zip")}')
    return destination


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    package(parser.parse_args().destination)

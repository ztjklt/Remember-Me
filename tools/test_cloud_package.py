import importlib.util
from pathlib import Path
import tarfile
import pytest


def module():
    path = Path(__file__).with_name('package_cloud.py')
    assert path.exists(), 'Cloud source packager has not been implemented'
    spec = importlib.util.spec_from_file_location('cloud_package', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_archive_contains_source_but_not_local_config_or_runtime(tmp_path):
    root = tmp_path / 'repo'
    names = ['services/backend/app/main.py', 'services/backend/.env',
             'services/backend/var/account.json', 'services/backend/.venv/key',
             'infra/aws/Caddyfile', 'services/backend/.env.example',
             'infra/aws/api.env', 'services/backend/backup.sqlite3',
             'services/backend/app/backup.sqlite', 'infra/aws/database.dump',
             'infra/aws/unknown.conf', 'services/ai-core/evaluations/private.json',
             'infra/aws/backend.env.example', 'services/backend/migrations/env.py']
    for name in names:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('placeholder', encoding='utf-8')
    destination = tmp_path / 'cloud.tar.gz'
    module().build(root, names, destination)
    with tarfile.open(destination) as archive:
        assert set(archive.getnames()) == {'services/backend/app/main.py',
            'infra/aws/Caddyfile', 'services/backend/.env.example',
            'infra/aws/backend.env.example', 'services/backend/migrations/env.py'}
        assert all(not member.issym() for member in archive.getmembers())


def test_credential_in_source_prevents_archive_creation(tmp_path):
    source = tmp_path / 'services/backend/app/main.py'
    source.parent.mkdir(parents=True)
    source.write_text('private-secret-for-test-only')
    output = tmp_path / 'result.tar.gz'
    with pytest.raises(ValueError, match='credential'):
        module().build(tmp_path, ['services/backend/app/main.py'], output,
                       secrets=[b'private-secret-for-test-only'])
    assert not output.exists()


def test_unsafe_archive_path_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='path'):
        module().build(tmp_path, ['../services/backend/app/main.py'], tmp_path/'result.tar.gz')


def test_source_symlink_is_rejected(tmp_path):
    source = tmp_path/'services/backend/app/main.py'
    source.parent.mkdir(parents=True)
    target = tmp_path/'outside.py'
    target.write_text('not release source')
    try:
        source.symlink_to(target)
    except OSError:
        pytest.skip('Host does not permit creating a symlink; Linux runs this check')
    with pytest.raises(ValueError, match='source path'):
        module().build(tmp_path, ['services/backend/app/main.py'], tmp_path/'result.tar.gz')

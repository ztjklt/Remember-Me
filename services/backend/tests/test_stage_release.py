import importlib.util
from pathlib import Path
import pytest
import tomllib


def module():
    path=Path(__file__).resolve().parents[3]/'tools/round_two/stage_ecs_paired.py'
    spec=importlib.util.spec_from_file_location('stage_release',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_staging_names_are_separate_from_production():
    plan=module().staging_names('fd9d539')
    assert plan['database']=='remember_stage_fd9d539_test'
    assert plan['root']=='/var/lib/remember-me/paired-stage-fd9d539'
    assert all('paired-stage-fd9d539-' in unit for unit in plan['units'])


@pytest.mark.parametrize('value',['../current','remember_me','fd9d539;echo',''])
def test_staging_rejects_arbitrary_paths_or_shell_fragments(value):
    with pytest.raises(ValueError):module().staging_names(value)


def test_ai_schema_validator_is_installed_in_production():
    # app.narrative imports this on API startup; dev-only installs hid ECS failure.
    path=Path(__file__).resolve().parents[3]/'services/ai-core/pyproject.toml'
    metadata=tomllib.loads(path.read_text(encoding='utf8'))
    assert any(item.startswith('jsonschema') for item in metadata['project']['dependencies'])


def test_all_runtime_units_must_be_active(monkeypatch):
    m=module();checked=[]
    def run(argv,**kwargs):
        checked.append(argv[-1])
        return type('Result',(),{'returncode':1 if argv[-1]=='ai' else 0})()
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='ai'):
        m.check_units(['ai','api','worker','profile'])
    assert checked==['ai','api','worker','profile']

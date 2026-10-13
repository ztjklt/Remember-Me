"""Smoke-test the built wheel outside the source checkout using installed deps.

Run `uv build --wheel` then `uv run python scripts/check_wheel.py [wheel-path]`.
No network or provider credentials are used. Extracted files live in a temporary
directory managed by Python and are removed on exit.
"""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile


SMOKE = """
import sys
import json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import app
assert Path(app.__file__).is_relative_to(Path(sys.argv[1]))
from app.contracts import load_fixture
from app.api import create_app
from app.config import Settings
from app.prompts import PROMPT_VERSION, SCHEMA_VERSION
from app.narrative import SCHEMA
import jsonschema
from fastapi.testclient import TestClient
schema_path = Path(app.__file__).parent / 'schemas' / 'narrative-draft-v1.schema.json'
assert schema_path.is_file(), 'Narrative contract missing from wheel'
assert SCHEMA == json.loads(schema_path.read_text(encoding='utf-8'))
jsonschema.validators.validator_for(SCHEMA).check_schema(SCHEMA)
try:
    jsonschema.validate({}, SCHEMA)
except jsonschema.ValidationError:
    pass
else:
    raise AssertionError('Packaged contract must reject an incomplete narrative')
settings = Settings(
    environment='test', provider='fixture', model='fixture-ai-v2',
    model_version='fixture-ai-v2', prompt_version=PROMPT_VERSION,
    schema_version=SCHEMA_VERSION, _env_file=None,
)
with TestClient(create_app(settings)) as client:
    assert client.get('/health').status_code == 200
    for name in ('phase1-happy', 'phase1-messy', 'phase1-adversarial', 'phase1-long-messy'):
        payload = load_fixture(name)
        response = client.post('/process', json=payload.model_dump(exclude_none=True))
        assert response.status_code == 200, response.status_code
capture_path = Path(app.__file__).parent / 'fixtures' / 'capture' / 'phase1-long-messy.json'
capture = json.loads(capture_path.read_text(encoding='utf-8'))
assert capture['subject_id'] == load_fixture('phase1-long-messy').subject_id
print('Wheel smoke passed: packaged contract, fixtures, extraction and HTTP boundary')
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", type=Path)
    args = parser.parse_args()
    wheel = args.wheel or max(Path("dist").glob("*.whl"), key=lambda path: path.stat().st_mtime)
    with tempfile.TemporaryDirectory(prefix="remember-me-wheel-") as directory:
        with ZipFile(wheel) as package:
            canonical = Path(__file__).resolve().parents[3] / 'packages/contracts/schemas/narrative-draft-v1.schema.json'
            if canonical.is_file():
                assert package.read('app/schemas/narrative-draft-v1.schema.json') == canonical.read_bytes(), 'Wheel contract differs from shared contract'
            package.extractall(directory)
        subprocess.run([sys.executable, "-I", "-c", SMOKE, directory], check=True)


if __name__ == "__main__":
    main()

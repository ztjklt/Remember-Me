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
from pathlib import Path
sys.path.insert(0, sys.argv[1])
if len(sys.argv) > 2:
    sys.path.insert(0, sys.argv[2])
    import remember_contracts
    assert Path(remember_contracts.__file__).is_relative_to(Path(sys.argv[2]))
import app
assert Path(app.__file__).is_relative_to(Path(sys.argv[1]))
from app.contracts import load_fixture
from app.api import create_app
from app.config import Settings
from app.prompts import PROMPT_VERSION, SCHEMA_VERSION
from fastapi.testclient import TestClient
settings = Settings(
    environment='test', provider='fixture', agent_enabled=True, model='fixture-ai-v2',
    model_version='fixture-ai-v2', prompt_version=PROMPT_VERSION,
    schema_version=SCHEMA_VERSION, _env_file=None,
)
with TestClient(create_app(settings)) as client:
    assert client.get('/health').status_code == 200
    from remember_contracts.agent import PersonaInput, Snapshot
    persona = PersonaInput(subject_id='wheel-subject', snapshot=Snapshot(subject_id='wheel-subject',
        revision=0, model_version='initial', prompt_version='initial'), materials=[], new_evidence_ids=[])
    result = client.post('/experimental/agent/v1/persona', json=persona.model_dump(mode='json'))
    assert result.status_code == 200, result.status_code
    for name in ('phase1-happy', 'phase1-messy', 'phase1-adversarial'):
        payload = load_fixture(name)
        response = client.post('/process', json=payload.model_dump(exclude_none=True))
        assert response.status_code == 200, response.status_code
print('Wheel smoke passed: packaged fixtures, extraction and HTTP boundary')
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", type=Path)
    parser.add_argument("--contracts-wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel or max(Path("dist").glob("*.whl"), key=lambda path: path.stat().st_mtime)
    with tempfile.TemporaryDirectory(prefix="remember-me-wheel-") as directory:
        with ZipFile(wheel) as package:
            package.extractall(directory)
        command = [sys.executable, "-I", "-c", SMOKE, directory]
        if args.contracts_wheel:
            contracts_dir = Path(directory) / "contracts"
            with ZipFile(args.contracts_wheel) as package:
                package.extractall(contracts_dir)
            command.append(str(contracts_dir))
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()

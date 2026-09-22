import json
from pathlib import Path

import pytest

from app.contracts import AICoreInput, load_fixture


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_NAMES = ("phase1-happy", "phase1-messy", "phase1-adversarial")


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_phase1_fixture_loads_as_the_frozen_input(name: str) -> None:
    payload = load_fixture(name)

    assert isinstance(payload, AICoreInput)
    assert payload.episode_id.startswith("fixture-")
    assert payload.subject_id
    assert payload.transcript.strip()
    assert payload.existing_model_version == "model-v0"


def test_fixtures_contain_only_contract_input_fields() -> None:
    expected = {
        "episode_id",
        "subject_id",
        "transcript",
        "existing_model_version",
    }

    for name in FIXTURE_NAMES:
        raw = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert set(raw) == expected


def test_fixture_loader_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="fixture name"):
        load_fixture("../phase1-happy")


def test_fixture_loader_is_deterministic() -> None:
    first = load_fixture("phase1-happy").model_dump(mode="json")
    second = load_fixture("phase1-happy").model_dump(mode="json")

    assert first == second

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.contracts import AICoreInput, load_fixture


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
CONTRACT_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "integration-contract-v0.1.schema.json"
)
FIXTURE_NAMES = (
    "phase1-happy", "phase1-messy", "phase1-adversarial", "phase1-long-messy",
)


@pytest.fixture(scope="module")
def contract_validator() -> Draft202012Validator:
    schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_phase1_fixture_loads_as_the_frozen_input(name: str) -> None:
    payload = load_fixture(name)

    assert isinstance(payload, AICoreInput)
    assert payload.episode_id.startswith("fixture-")
    assert payload.subject_id
    assert payload.transcript.strip()
    assert payload.existing_model_version == "model-v0"


def test_fixtures_contain_only_contract_input_fields(
    contract_validator: Draft202012Validator,
) -> None:
    expected = {
        "episode_id",
        "subject_id",
        "transcript",
        "existing_model_version",
    }

    for name in FIXTURE_NAMES:
        raw = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert set(raw) == expected
        contract_validator.validate(raw)


def test_capture_fixture_is_a_complete_contract_capture(
    contract_validator: Draft202012Validator,
) -> None:
    capture = json.loads(
        (FIXTURE_DIR / "capture" / "phase1-long-messy.json").read_text(encoding="utf-8")
    )
    transcript = load_fixture("phase1-long-messy")

    contract_validator.validate(capture)
    assert capture["subject_id"] == transcript.subject_id
    assert capture["actor_id"]
    assert capture["recording_consent_id"]
    assert capture["idempotency_key"]
    assert capture["source"] == "ANDROID_MIC"


def test_long_messy_transcript_has_substantial_ambiguous_content() -> None:
    transcript = load_fixture("phase1-long-messy").transcript

    assert len(transcript) >= 500
    assert "不对" in transcript
    assert "可能" in transcript
    assert "她说" in transcript


def test_fixture_loader_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="fixture name"):
        load_fixture("../phase1-happy")


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_loader_is_deterministic(name: str) -> None:
    first = load_fixture(name).model_dump(mode="json")
    second = load_fixture(name).model_dump(mode="json")

    assert first == second

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import AICoreInput, AICoreOutput, Evidence, MemoryItem


SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "integration-contract-v0.1.schema.json"
)


def _numeric_branch(property_schema: dict) -> dict:
    if "minimum" in property_schema:
        return property_schema
    return next(branch for branch in property_schema["anyOf"] if "minimum" in branch)


@pytest.fixture(scope="module")
def frozen_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_ai_core_input_mirrors_frozen_contract(frozen_schema: dict) -> None:
    generated = AICoreInput.model_json_schema()
    frozen = frozen_schema["$defs"]["aiCoreInput"]

    assert set(generated["properties"]) == set(frozen["properties"])
    assert set(generated["required"]) == set(frozen["required"])
    assert generated["additionalProperties"] is False
    assert generated["properties"]["episode_id"]["minLength"] == 1
    assert generated["properties"]["transcript"]["minLength"] == 1
    assert generated["properties"]["existing_model_version"]["minLength"] == 1


def test_evidence_mirrors_frozen_contract(frozen_schema: dict) -> None:
    generated = Evidence.model_json_schema()
    frozen = frozen_schema["$defs"]["evidence"]

    assert set(generated["properties"]) == set(frozen["properties"])
    assert set(generated["required"]) == set(frozen["required"])
    assert generated["additionalProperties"] is False
    assert generated["properties"]["source_type"]["enum"] == frozen["properties"]["source_type"]["enum"]
    confidence = _numeric_branch(generated["properties"]["confidence"])
    assert confidence["minimum"] == 0
    assert confidence["maximum"] == 1


def test_memory_item_mirrors_frozen_contract(frozen_schema: dict) -> None:
    generated = MemoryItem.model_json_schema()
    frozen = frozen_schema["$defs"]["memoryItem"]

    assert set(generated["properties"]) == set(frozen["properties"])
    assert set(generated["required"]) == set(frozen["required"])
    assert generated["additionalProperties"] is False
    assert generated["properties"]["memory_type"]["enum"] == frozen["properties"]["memory_type"]["enum"]
    assert generated["properties"]["source_type"]["enum"] == frozen["properties"]["source_type"]["enum"]
    assert generated["properties"]["evidence_ids"]["minItems"] == 1
    assert generated["properties"]["confidence"]["minimum"] == 0
    assert generated["properties"]["confidence"]["maximum"] == 1


def test_ai_core_output_mirrors_frozen_contract(frozen_schema: dict) -> None:
    generated = AICoreOutput.model_json_schema()
    frozen = frozen_schema["$defs"]["aiCoreOutput"]

    assert set(generated["properties"]) == set(frozen["properties"])
    assert set(generated["required"]) == set(frozen["required"])
    assert generated["additionalProperties"] is False


@pytest.mark.parametrize(
    "model, payload",
    [
        (
            AICoreInput,
            {
                "episode_id": "episode-1",
                "subject_id": "subject-1",
                "transcript": "hello",
                "existing_model_version": "model-0",
                "unexpected": True,
            },
        ),
        (
            Evidence,
            {
                "evidence_id": "evidence-1",
                "source_type": "SUBJECT",
                "source_ref": "episode:episode-1#span:0-5",
                "unexpected": True,
            },
        ),
    ],
)
def test_contract_models_reject_unknown_fields(model: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)

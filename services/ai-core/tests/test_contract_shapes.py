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


@pytest.mark.parametrize("confidence", [True, "0.9", float("nan"), float("inf")])
def test_confidence_cannot_be_coerced_from_non_json_numbers(confidence) -> None:
    with pytest.raises(ValidationError):
        Evidence(evidence_id="e", source_type="SUBJECT", source_ref="r", confidence=confidence)


@pytest.mark.parametrize("span", [True, "0", 0.5])
def test_span_cannot_be_coerced_from_boolean_or_string(span) -> None:
    with pytest.raises(ValidationError):
        Evidence(evidence_id="e", source_type="SUBJECT", source_ref="r", span_start=span)


@pytest.mark.parametrize("field", ["trace_id", "subject_context"])
def test_input_optional_fields_must_be_omitted_instead_of_null(field: str) -> None:
    with pytest.raises(ValidationError):
        AICoreInput.model_validate({
            "episode_id": "e", "subject_id": "s", "transcript": "hello",
            "existing_model_version": "v0", field: None,
        })


@pytest.mark.parametrize("timestamp", [1234567890, "1234567890", "2026-09-22T10:00:00", "2026-09-22"])
def test_effective_at_requires_a_timezone_aware_datetime(timestamp) -> None:
    with pytest.raises(ValidationError):
        MemoryItem(
            memory_type="EVENT", content="a memory", source_type="AI_INFERENCE",
            evidence_ids=["e"], confidence=0.9, model_version="m",
            prompt_version="p", schema_version="s", effective_at=timestamp,
        )


def test_effective_at_preserves_the_instant_as_utc():
    memory = MemoryItem(
        memory_type="EVENT", content="a memory", source_type="AI_INFERENCE",
        evidence_ids=["e"], confidence=1, model_version="m", prompt_version="p",
        schema_version="s", effective_at="2026-09-22T10:00:00+08:00",
    )
    assert memory.model_dump(mode="json")["effective_at"] == "2026-09-22T02:00:00Z"

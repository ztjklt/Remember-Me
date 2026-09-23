"""The Pydantic mirror against the frozen contract.

app/contracts.py is a hand-written mirror of packages/contracts, and a mirror
that can drift is worse than no mirror: it would accept a payload the contract
forbids and reject one it requires, silently, on both sides. This file reads the
frozen schema and fails when the two disagree, so a contract change breaks a test
here rather than a client later.

It compares shapes, not validation behaviour. The end-to-end cross-check — real
HTTP responses validated by the contract's own ajv suite — is run by hand and
recorded in the pull request, because it needs Node and this suite is Python.
"""

import json
from pathlib import Path
from typing import Literal, get_args, get_origin

import pytest
from annotated_types import Ge, Le, MaxLen, MinLen
from pydantic import BaseModel

from app import contracts

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "integration-contract-v0.1.schema.json"
)

# Every shape this service produces or consumes in Phase 1.
MIRRORED: dict[str, type[BaseModel]] = {
    "evidence": contracts.Evidence,
    "memoryItem": contracts.MemoryItem,
    "captureEpisode": contracts.CaptureEpisode,
    "episodeCreated": contracts.EpisodeCreated,
    "processingStatus": contracts.ProcessingStatus,
    "aiCoreInput": contracts.AICoreInput,
    "aiCoreOutput": contracts.AICoreOutput,
    "episodeResult": contracts.EpisodeResult,
}

# Deliberately not mirrored: Phase 2, 3, and 4 shapes.
NOT_MIRRORED = {
    "twinRequest",
    "twinResponse",
    "voiceRequest",
    "voiceResponse",
    "calibrationInput",
    "calibrationOutput",
}


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def definition(schema: dict, name: str) -> dict:
    return schema["$defs"][name]


def test_the_mirror_covers_exactly_the_phase_1_shapes(schema):
    assert set(MIRRORED) | NOT_MIRRORED == set(schema["$defs"])


@pytest.mark.parametrize("name", sorted(MIRRORED))
def test_field_names_and_required_fields_match(schema, name):
    model = MIRRORED[name]
    node = definition(schema, name)
    fields = model.model_fields

    assert set(fields) == set(node["properties"]), name
    assert {field for field, info in fields.items() if info.is_required()} == set(
        node.get("required", [])
    ), f"{name}: a field required by the contract must be required in the mirror"


@pytest.mark.parametrize("name", sorted(MIRRORED))
def test_unknown_fields_are_refused(schema, name):
    """additionalProperties: false in the schema becomes extra="forbid" here."""
    assert definition(schema, name)["additionalProperties"] is False
    assert MIRRORED[name].model_config["extra"] == "forbid", name


@pytest.mark.parametrize("name", sorted(MIRRORED))
def test_enum_values_match(schema, name):
    node = definition(schema, name)
    for field_name, info in MIRRORED[name].model_fields.items():
        expected = node["properties"][field_name].get("enum")
        if expected is None:
            continue
        annotation = info.annotation
        if get_origin(annotation) is Literal:
            actual = list(get_args(annotation))
        else:
            assert hasattr(annotation, "__members__"), (
                f"{name}.{field_name} mirrors an enum but is typed {annotation}"
            )
            actual = [member.value for member in annotation]
        assert actual == expected, f"{name}.{field_name}"


@pytest.mark.parametrize("name", sorted(MIRRORED))
def test_string_and_number_bounds_match(schema, name):
    node = definition(schema, name)
    for field_name, info in MIRRORED[name].model_fields.items():
        expected = node["properties"][field_name]

        if expected.get("type") == "string" and expected.get("minLength") == 1:
            assert _bound(info, MinLen) == 1, f"{name}.{field_name}: minLength 1"

        if "minimum" in expected:
            assert _bound(info, Ge) == expected["minimum"], f"{name}.{field_name}: minimum"
        if "maximum" in expected:
            assert _bound(info, Le) == expected["maximum"], f"{name}.{field_name}: maximum"


def _bound(field_info, kind: type):  # type: ignore[no-untyped-def]
    """The value of one constraint pydantic recorded in the field's metadata."""
    for item in field_info.metadata:
        if isinstance(item, kind):
            return item.ge if kind is Ge else item.le if kind is Le else item.min_length
    return None


def test_evidence_ids_are_a_non_empty_unique_list(schema):
    node = definition(schema, "memoryItem")["properties"]["evidence_ids"]
    assert node["minItems"] == 1
    assert node["uniqueItems"] is True

    field_info = contracts.MemoryItem.model_fields["evidence_ids"]
    assert _bound(field_info, MinLen) == 1

    with pytest.raises(Exception):
        contracts.MemoryItem(
            memory_type="EVENT",
            content="x",
            source_type="SUBJECT",
            evidence_ids=["ev_1", "ev_1"],
            confidence=0.5,
            model_version="m",
            prompt_version="p",
            schema_version="s",
        )


def test_a_result_is_ready_by_definition(schema):
    node = definition(schema, "episodeResult")["properties"]["status"]
    assert node["const"] == "ready"
    assert get_args(contracts.EpisodeResult.model_fields["status"].annotation) == ("ready",)


def test_optional_fields_are_optional_in_the_mirror(schema):
    """A field the contract does not require must not be required here either."""
    for name, model in MIRRORED.items():
        required = set(definition(schema, name).get("required", []))
        for field_name, info in model.model_fields.items():
            if field_name not in required:
                assert not info.is_required(), f"{name}.{field_name} is stricter than the contract"


def test_no_contract_shape_carries_a_job_id():
    """The contract asserts the job id is never exposed; the mirror must agree."""
    for model in MIRRORED.values():
        assert "job_id" not in model.model_fields


def test_the_schema_version_names_the_frozen_contract(schema):
    assert contracts.SCHEMA_VERSION in schema["$id"]
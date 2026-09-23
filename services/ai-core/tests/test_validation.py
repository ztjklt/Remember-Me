import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.contracts import AICoreOutput, Evidence, MemoryItem, load_fixture
from app.errors import AIOutputInvalid, EvidenceInvalid
from app.provenance import build_transcript_evidence
from app.validation import validate_output


SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "integration-contract-v0.1.schema.json"
)


def _valid_output() -> tuple[object, AICoreOutput]:
    payload = load_fixture("phase1-happy")
    evidence = build_transcript_evidence(
        payload,
        "evidence-1",
        0,
        len(payload.transcript),
        0.95,
    )
    memory = MemoryItem(
        memory_type="PREFERENCE",
        content="主体喜欢周末爬山。",
        source_type="AI_INFERENCE",
        evidence_ids=[evidence.evidence_id],
        confidence=0.9,
        model_version="fixture-ai-v1",
        prompt_version="memory-extractor-v1",
        schema_version="integration-contract-v0.1.2",
    )
    return payload, AICoreOutput(
        memory_items=[memory],
        graph_updates=[],
        persona_updates=[],
        evidence=[evidence],
        model_version="fixture-ai-v1",
    )


def test_validate_output_accepts_resolved_transcript_evidence() -> None:
    payload, output = _valid_output()

    assert validate_output(payload, output) == output


def test_valid_output_matches_the_frozen_json_schema() -> None:
    payload, output = _valid_output()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    validate_output(payload, output)
    Draft202012Validator(schema).validate(output.model_dump(mode="json", exclude_none=True))


def test_validate_output_rejects_duplicate_evidence_ids() -> None:
    payload, output = _valid_output()
    output = output.model_copy(update={"evidence": [output.evidence[0], output.evidence[0]]})

    with pytest.raises(EvidenceInvalid, match="unique"):
        validate_output(payload, output)


def test_validate_output_rejects_unknown_memory_evidence_id() -> None:
    payload, output = _valid_output()
    memory = output.memory_items[0].model_copy(update={"evidence_ids": ["missing-evidence"]})
    output = output.model_copy(update={"memory_items": [memory]})

    with pytest.raises(AIOutputInvalid, match="missing-evidence"):
        validate_output(payload, output)


def test_validate_output_rejects_duplicate_memory_evidence_ids() -> None:
    payload, output = _valid_output()
    memory = output.memory_items[0].model_copy(update={"evidence_ids": ["evidence-1", "evidence-1"]})
    output = output.model_copy(update={"memory_items": [memory]})

    with pytest.raises(AIOutputInvalid, match="unique"):
        validate_output(payload, output)


def test_contract_rejects_empty_evidence_ids() -> None:
    with pytest.raises(ValidationError):
        MemoryItem(
            memory_type="PREFERENCE",
            content="内容",
            source_type="AI_INFERENCE",
            evidence_ids=[],
            confidence=0.5,
            model_version="model-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
        )


def test_contract_rejects_invalid_confidence_and_source_type() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="evidence-1",
            source_type="SUBJECT",
            source_ref="episode:episode-1",
            confidence=1.1,
        )

    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="evidence-1",
            source_type="NOT_A_SOURCE",
            source_ref="episode:episode-1",
        )


def test_validate_output_rejects_span_outside_transcript() -> None:
    payload, output = _valid_output()
    evidence = output.evidence[0].model_copy(
        update={
            "span_start": 0,
            "span_end": len(payload.transcript) + 1,
            "excerpt": payload.transcript,
        }
    )
    output = output.model_copy(update={"evidence": [evidence]})

    with pytest.raises(EvidenceInvalid, match="outside transcript"):
        validate_output(payload, output)


def test_validate_output_rejects_excerpt_that_does_not_match_span() -> None:
    payload, output = _valid_output()
    evidence = output.evidence[0].model_copy(
        update={"span_start": 0, "span_end": 2, "excerpt": "不匹配"}
    )
    output = output.model_copy(update={"evidence": [evidence]})

    with pytest.raises(EvidenceInvalid, match="does not match"):
        validate_output(payload, output)


def test_validate_output_rejects_non_empty_phase1_future_updates() -> None:
    payload, output = _valid_output()
    output = output.model_copy(update={"graph_updates": [{"future": True}]})

    with pytest.raises(AIOutputInvalid, match="graph_updates"):
        validate_output(payload, output)


def test_validate_output_rejects_evidence_for_a_different_episode() -> None:
    payload, output = _valid_output()
    evidence = output.evidence[0].model_copy(
        update={"source_ref": "episode:another-episode#span:0-2"}
    )
    output = output.model_copy(update={"evidence": [evidence]})

    with pytest.raises(EvidenceInvalid, match="Episode"):
        validate_output(payload, output)


@pytest.mark.parametrize("source_ref", ["episode:someone-else", "https://invented.test/evidence"])
def test_evidence_cannot_skip_grounding_by_omitting_spans(source_ref: str) -> None:
    payload, output = _valid_output()
    output.evidence[0] = output.evidence[0].model_copy(
        update={"span_start": None, "span_end": None, "source_ref": source_ref}
    )
    with pytest.raises(EvidenceInvalid):
        validate_output(payload, output)


def test_inference_cannot_be_relabelled_as_a_subject_quote() -> None:
    payload, output = _valid_output()
    output.memory_items[0].source_type = "SUBJECT"
    output.memory_items[0].content = "我是一个完全不同的人。"
    with pytest.raises(EvidenceInvalid):
        validate_output(payload, output)


def test_third_party_evidence_cannot_be_relabelled_as_subject_evidence() -> None:
    payload, output = _valid_output()
    output.evidence[0].source_type = "THIRD_PARTY"
    output.memory_items[0].source_type = "SUBJECT"
    output.memory_items[0].content = payload.transcript
    with pytest.raises(EvidenceInvalid):
        validate_output(payload, output)


def test_whitespace_is_not_evidence_or_memory() -> None:
    payload, output = _valid_output()
    output.memory_items[0].content = " \n "
    with pytest.raises(AIOutputInvalid):
        validate_output(payload, output)


def test_exact_subject_quote_is_accepted() -> None:
    payload, output = _valid_output()
    output.memory_items[0].source_type = "SUBJECT"
    output.memory_items[0].content = payload.transcript
    assert validate_output(payload, output) == output

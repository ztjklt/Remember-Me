"""Semantic validation that cannot be expressed by Pydantic alone."""

from __future__ import annotations

from .contracts import AICoreInput, AICoreOutput, Evidence, GraphFact, PersonTrait
from .errors import AIOutputInvalid, EvidenceInvalid


def _validate_evidence(payload: AICoreInput, output: AICoreOutput) -> dict[str, Evidence]:
    evidence_by_id: dict[str, Evidence] = {}

    for evidence in output.evidence:
        if evidence.evidence_id in evidence_by_id:
            raise EvidenceInvalid(f"evidence IDs must be unique: {evidence.evidence_id}")
        evidence_by_id[evidence.evidence_id] = evidence

        has_start = evidence.span_start is not None
        has_end = evidence.span_end is not None
        if has_start != has_end:
            raise EvidenceInvalid(
                f"transcript span for {evidence.evidence_id} must include both start and end"
            )
        if not has_start:
            # Phase 1 has no resolver for external evidence. An opaque reference
            # alone cannot establish that an AI-generated claim is grounded.
            raise EvidenceInvalid("Phase 1 evidence must have a verified transcript span")

        assert evidence.span_start is not None
        assert evidence.span_end is not None
        if evidence.span_start >= evidence.span_end or evidence.span_end > len(payload.transcript):
            raise EvidenceInvalid(
                f"evidence {evidence.evidence_id} is outside transcript bounds"
            )

        expected_excerpt = payload.transcript[evidence.span_start : evidence.span_end]
        if evidence.excerpt != expected_excerpt or not expected_excerpt.strip():
            raise EvidenceInvalid(
                f"evidence {evidence.evidence_id} excerpt does not match its transcript span"
            )

        expected_ref = (
            f"episode:{payload.episode_id}#span:{evidence.span_start}-{evidence.span_end}"
        )
        if evidence.source_ref != expected_ref:
            raise EvidenceInvalid(
                f"evidence {evidence.evidence_id} must reference the current Episode"
            )

    return evidence_by_id


def validate_output(payload: AICoreInput, output: AICoreOutput) -> AICoreOutput:
    """Validate an already parsed output before it can leave AI Core."""

    evidence_by_id = _validate_evidence(payload, output)

    for trait in output.persona_updates:
        if not isinstance(trait, PersonTrait):
            raise AIOutputInvalid("persona_updates must be typed person traits")
        if not trait.evidence_ids or any(eid not in evidence_by_id for eid in trait.evidence_ids):
            raise EvidenceInvalid("person trait has unverified evidence")
        if any(eid not in evidence_by_id for eid in trait.counter_evidence_ids):
            raise EvidenceInvalid("person trait has unverified counter evidence")
    for fact in output.graph_updates:
        if not isinstance(fact, GraphFact):
            raise AIOutputInvalid("graph_updates must be typed graph facts")
        if fact.subject_id != payload.subject_id:
            raise AIOutputInvalid("graph fact belongs to another subject")
        if not fact.evidence_ids or any(eid not in evidence_by_id for eid in fact.evidence_ids):
            raise EvidenceInvalid("graph fact has unverified evidence")

    for memory in output.memory_items:
        if not memory.content.strip():
            raise AIOutputInvalid("memory content must not be whitespace")
        if not memory.evidence_ids:
            raise AIOutputInvalid(f"memory {memory.content!r} needs evidence")
        if len(memory.evidence_ids) != len(set(memory.evidence_ids)):
            raise AIOutputInvalid("memory evidence IDs must be unique")

        missing = [evidence_id for evidence_id in memory.evidence_ids if evidence_id not in evidence_by_id]
        if missing:
            raise AIOutputInvalid(
                f"memory {memory.content!r} references missing evidence: {', '.join(missing)}"
            )

        if memory.source_type != "AI_INFERENCE":
            sources = [evidence_by_id[item] for item in memory.evidence_ids]
            if any(item.source_type != memory.source_type for item in sources):
                raise EvidenceInvalid("memory attribution does not match its evidence")
            if memory.content not in {item.excerpt for item in sources}:
                raise EvidenceInvalid("a paraphrase must be labelled AI_INFERENCE, not a direct source")

        for field_name in ("model_version", "prompt_version", "schema_version"):
            if not getattr(memory, field_name).strip():
                raise AIOutputInvalid(
                    f"memory {memory.content!r} is missing {field_name}"
                )

    return output


__all__ = ["validate_output"]

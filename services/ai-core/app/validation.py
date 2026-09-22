"""Semantic validation that cannot be expressed by Pydantic alone."""

from __future__ import annotations

from .contracts import AICoreInput, AICoreOutput
from .errors import AIOutputInvalid, EvidenceInvalid


def _validate_evidence(payload: AICoreInput, output: AICoreOutput) -> dict[str, object]:
    evidence_by_id: dict[str, object] = {}

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
            continue

        assert evidence.span_start is not None
        assert evidence.span_end is not None
        if evidence.span_start >= evidence.span_end or evidence.span_end > len(payload.transcript):
            raise EvidenceInvalid(
                f"evidence {evidence.evidence_id} is outside transcript bounds"
            )

        expected_excerpt = payload.transcript[evidence.span_start : evidence.span_end]
        if evidence.excerpt != expected_excerpt:
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

    if output.graph_updates:
        raise AIOutputInvalid("graph_updates must be empty during Phase 1")
    if output.persona_updates:
        raise AIOutputInvalid("persona_updates must be empty during Phase 1")

    for memory in output.memory_items:
        if not memory.evidence_ids:
            raise AIOutputInvalid(f"memory {memory.content!r} needs evidence")
        if len(memory.evidence_ids) != len(set(memory.evidence_ids)):
            raise AIOutputInvalid("memory evidence IDs must be unique")

        missing = [evidence_id for evidence_id in memory.evidence_ids if evidence_id not in evidence_by_id]
        if missing:
            raise AIOutputInvalid(
                f"memory {memory.content!r} references missing evidence: {', '.join(missing)}"
            )

        for field_name in ("model_version", "prompt_version", "schema_version"):
            if not getattr(memory, field_name).strip():
                raise AIOutputInvalid(
                    f"memory {memory.content!r} is missing {field_name}"
                )

    return output


__all__ = ["validate_output"]

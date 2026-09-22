"""Build deterministic evidence references for the current Episode."""

from __future__ import annotations

from .contracts import AICoreInput, Evidence
from .errors import EvidenceInvalid


def build_transcript_evidence(
    payload: AICoreInput,
    evidence_id: str,
    start: int,
    end: int,
    confidence: float,
) -> Evidence:
    """Create subject evidence whose excerpt is taken from the input transcript."""

    if start < 0 or end <= start or end > len(payload.transcript):
        raise EvidenceInvalid(
            f"transcript span {start}-{end} is invalid for transcript length "
            f"{len(payload.transcript)}"
        )

    return Evidence(
        evidence_id=evidence_id,
        source_type="SUBJECT",
        source_ref=f"episode:{payload.episode_id}#span:{start}-{end}",
        excerpt=payload.transcript[start:end],
        span_start=start,
        span_end=end,
        confidence=confidence,
    )


__all__ = ["build_transcript_evidence"]

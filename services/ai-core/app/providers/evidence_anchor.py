"""Re-anchor model evidence only when a unique source span can be proven."""

from __future__ import annotations

from typing import Any

from opencc import OpenCC


def reanchor_unique_evidence(
    output: dict[str, Any], *, transcript: str, episode_id: str, converter: OpenCC,
) -> dict[str, Any]:
    """Copy the original text and offsets for unique exact or one-to-one CJK matches.

    Ambiguous excerpts and conversions that change character count stay untouched
    so the downstream provenance validator rejects them.
    """
    evidences = output.get("evidence")
    normalized_transcript: str | None = None
    for evidence in evidences if isinstance(evidences, list) else []:
        if not isinstance(evidence, dict):
            continue
        excerpt = evidence.get("excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            continue
        if transcript.count(excerpt) == 1:
            start = transcript.index(excerpt)
        else:
            if normalized_transcript is None:
                converted = converter.convert(transcript)
                normalized_transcript = converted if len(converted) == len(transcript) else ""
            normalized_excerpt = converter.convert(excerpt)
            if (
                not normalized_transcript
                or len(normalized_excerpt) != len(excerpt)
                or normalized_transcript.count(normalized_excerpt) != 1
            ):
                continue
            start = normalized_transcript.index(normalized_excerpt)
            if converter.convert(transcript[start : start + len(excerpt)]) != normalized_excerpt:
                continue
        end = start + len(excerpt)
        evidence["excerpt"] = transcript[start:end]
        evidence["span_start"] = start
        evidence["span_end"] = end
        evidence["source_ref"] = f"episode:{episode_id}#span:{start}-{end}"

    # A direct-source Memory must display the exact quote. A model may change
    # Traditional Chinese wording to an equivalent form while preserving every
    # character. Copy from one uniquely matching verified evidence only.
    by_id: dict[str, str] = {}
    for item in evidences if isinstance(evidences, list) else []:
        if not isinstance(item, dict):
            continue
        evidence_id, excerpt = item.get("evidence_id"), item.get("excerpt")
        start, end = item.get("span_start"), item.get("span_end")
        if (
            isinstance(evidence_id, str) and isinstance(excerpt, str)
            and isinstance(start, int) and isinstance(end, int)
            and 0 <= start < end <= len(transcript)
            and transcript[start:end] == excerpt
            and item.get("source_ref") == f"episode:{episode_id}#span:{start}-{end}"
        ):
            by_id[evidence_id] = excerpt
    memories = output.get("memory_items")
    for memory in memories if isinstance(memories, list) else []:
        if not isinstance(memory, dict) or memory.get("source_type") == "AI_INFERENCE":
            continue
        content = memory.get("content")
        ids = memory.get("evidence_ids")
        if not isinstance(content, str) or not isinstance(ids, list):
            continue
        excerpts = {by_id[item] for item in ids if isinstance(item, str) and item in by_id}
        if content in excerpts:
            continue
        normalized_content = converter.convert(content)
        if len(normalized_content) != len(content):
            continue
        matches = {
            excerpt for excerpt in excerpts
            if len(converter.convert(excerpt)) == len(excerpt)
            and converter.convert(excerpt) == normalized_content
        }
        if len(matches) == 1:
            memory["content"] = matches.pop()
    return output

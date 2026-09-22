"""Deterministic provider used only by local development and tests."""

from __future__ import annotations

from typing import Any

from ..contracts import AICoreInput
from ..provenance import build_transcript_evidence
from .base import ModelRequest


class FixtureProvider:
    """Produce a conservative, repeatable result without a network call."""

    provider_name = "fixture"
    default_model_version = "fixture-ai-v1"
    _uncertainty_markers = ("也许", "可能", "或许", "不确定", "说不准")

    def generate(self, request: ModelRequest) -> dict[str, Any]:
        payload = request.payload
        span = self._first_sentence_span(payload.transcript)
        if span is None:
            return self._empty_output(request)

        start, end = span
        excerpt = payload.transcript[start:end].strip()
        evidence = build_transcript_evidence(payload, f"{payload.episode_id}:evidence:0", start, end, 0.95)
        memory_type = "PREFERENCE" if any(word in excerpt for word in ("喜欢", "偏爱", "爱")) else "EVENT"
        memory = {
            "memory_type": memory_type,
            "content": excerpt,
            "source_type": "AI_INFERENCE",
            "evidence_ids": [evidence.evidence_id],
            "confidence": 0.85,
            "model_version": request.model_version,
            "prompt_version": request.prompt_version,
            "schema_version": request.schema_version,
        }
        return {
            "memory_items": [memory],
            "graph_updates": [],
            "persona_updates": [],
            "evidence": [evidence.model_dump(mode="json")],
            "model_version": request.model_version,
        }

    def _first_sentence_span(self, transcript: str) -> tuple[int, int] | None:
        if not transcript.strip() or any(marker in transcript for marker in self._uncertainty_markers):
            return None

        start = len(transcript) - len(transcript.lstrip())
        end = len(transcript)
        for index in range(start, len(transcript)):
            if transcript[index] in "。！？.!?\n":
                end = index + 1
                break

        if end <= start or len(transcript[start:end].strip()) < 4:
            return None
        return start, end

    @staticmethod
    def _empty_output(request: ModelRequest) -> dict[str, Any]:
        return {
            "memory_items": [],
            "graph_updates": [],
            "persona_updates": [],
            "evidence": [],
            "model_version": request.model_version,
        }


__all__ = ["FixtureProvider"]

"""Deterministic provider used only by local development and tests."""

from __future__ import annotations

import re
from typing import Any

from ..provenance import build_transcript_evidence
from .base import ModelRequest


class FixtureProvider:
    """Produce a conservative, repeatable result without a network call."""

    provider_name = "fixture"
    default_model_version = "fixture-ai-v2"
    _uncertainty_markers = ("也许", "可能", "或许", "不确定", "说不准", "maybe", "perhaps", "not sure")
    _instruction_markers = ("忽略", "系统提示", "改写记忆", "ignore", "system prompt", "invent a memory")

    def generate(self, request: ModelRequest) -> dict[str, Any]:
        if request.worker_input is not None:
            from ..agent.fixture import generate
            return generate(request)
        payload = request.payload
        output = self._empty_output(request)
        seen = set()
        # This is deliberately a small offline simulator, not a semantic model
        # or a production prompt-injection detector. Keep original offsets.
        for match in re.finditer(r"[^。！？.!?\n]+[。！？.!?]*", payload.transcript):
            sentence = match.group()
            excerpt = sentence.strip()
            lower = excerpt.casefold()
            if (len(excerpt) < 4 or excerpt in seen
                    or any(marker in lower for marker in self._uncertainty_markers + self._instruction_markers)):
                continue
            seen.add(excerpt)
            start = match.start() + len(sentence) - len(sentence.lstrip())
            end = match.end() - len(sentence) + len(sentence.rstrip())
            evidence = build_transcript_evidence(
                payload, f"{payload.episode_id}:evidence:{len(output['evidence'])}", start, end, 0.95,
            )
            memory_type = "PREFERENCE" if any(word in excerpt for word in ("喜欢", "偏爱")) else "EVENT"
            output["memory_items"].append({
                "memory_type": memory_type, "content": excerpt, "source_type": "AI_INFERENCE",
                "evidence_ids": [evidence.evidence_id], "confidence": 0.85,
                "model_version": request.model_version, "prompt_version": request.prompt_version,
                "schema_version": request.schema_version,
            })
            output["evidence"].append(evidence.model_dump(mode="json", exclude_none=True))
        return output

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

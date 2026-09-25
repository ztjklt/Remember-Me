"""Provider-neutral Episode/Transcript to Memory extraction pipeline."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from time import perf_counter

from pydantic import ValidationError

from .contracts import AICoreInput, AICoreOutput
from .errors import AICoreError, AIOutputInvalid, EvidenceInvalid
from .prompts import PROMPT_VERSION, SCHEMA_VERSION, build_system_prompt
from .providers.base import ModelRequest, StructuredModelProvider
from .validation import validate_output

logger = logging.getLogger("remember_me.ai_core")


class MemoryExtractor:
    def __init__(
        self,
        *,
        provider: StructuredModelProvider,
        model: str,
        model_version: str,
        prompt_version: str = PROMPT_VERSION,
        schema_version: str = SCHEMA_VERSION,
    ) -> None:
        self.provider = provider
        self.model = model
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.schema_version = schema_version

    def process(self, payload: AICoreInput) -> AICoreOutput:
        started = perf_counter()
        outcome = "internal_error"
        try:
            output = self._process(payload)
            outcome = "ok"
            return output
        except AICoreError as exc:
            outcome = exc.code
            raise
        finally:
            logger.info(json.dumps({
                "event": "extraction", "trace_id": payload.trace_id,
                "outcome": outcome, "duration_ms": round((perf_counter() - started) * 1000, 3),
            }, ensure_ascii=True))

    def _process(self, payload: AICoreInput) -> AICoreOutput:
        if not payload.transcript.strip():
            return AICoreOutput(
                memory_items=[], graph_updates=[], persona_updates=[], evidence=[],
                model_version=self.model_version,
            )

        request = ModelRequest(
            payload=payload,
            system_prompt=build_system_prompt(),
            response_schema=AICoreOutput.model_json_schema(),
            model=self.model,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
        )
        for attempt in range(2):
            try:
                raw_output = self.provider.generate(request)
                try:
                    output = AICoreOutput.model_validate(raw_output)
                except ValidationError as exc:
                    raise AIOutputInvalid("AI provider output failed the frozen schema") from exc

                # Provenance describes this deployment, not a string guessed by the LLM.
                output.model_version = self.model_version
                for memory in output.memory_items:
                    memory.model_version = self.model_version
                    memory.prompt_version = self.prompt_version
                    memory.schema_version = self.schema_version
                return validate_output(payload, output)
            except (AIOutputInvalid, EvidenceInvalid):
                if attempt:
                    raise
                # One bounded regeneration is valuable with JSON-object providers.
                # Never weaken validation or persist a partially valid response.
                request = replace(request, system_prompt=request.system_prompt + (
                    " The previous response was rejected. Generate a fresh complete JSON "
                    "object. Recalculate every evidence span from the original transcript, "
                    "copy its exact substring, keep only supported memory claims, and "
                    "omit any item you cannot cite exactly."
                ))
        raise AIOutputInvalid("AI provider did not produce a valid extraction")


__all__ = ["MemoryExtractor"]

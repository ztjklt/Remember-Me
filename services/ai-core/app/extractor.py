"""Provider-neutral Episode/Transcript to Memory extraction pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .contracts import AICoreInput, AICoreOutput
from .errors import AIOutputInvalid
from .prompts import PROMPT_VERSION, SCHEMA_VERSION, build_system_prompt
from .providers.base import ModelRequest, StructuredModelProvider
from .validation import validate_output


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
        request = ModelRequest(
            payload=payload,
            system_prompt=build_system_prompt(),
            response_schema=AICoreOutput.model_json_schema(),
            model=self.model,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
        )
        raw_output = self.provider.generate(request)
        try:
            output = AICoreOutput.model_validate(raw_output)
        except ValidationError as exc:
            raise AIOutputInvalid("AI provider output failed the frozen schema") from exc

        return validate_output(payload, output)


__all__ = ["MemoryExtractor"]

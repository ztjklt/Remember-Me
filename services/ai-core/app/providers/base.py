"""Provider-neutral request and adapter interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..contracts import AICoreInput


@dataclass(frozen=True)
class ModelRequest:
    payload: AICoreInput
    system_prompt: str
    response_schema: dict[str, Any]
    model: str
    model_version: str
    prompt_version: str
    schema_version: str


class StructuredModelProvider(Protocol):
    def generate(self, request: ModelRequest) -> dict[str, Any]:
        """Return raw structured data; the extractor validates it."""


__all__ = ["ModelRequest", "StructuredModelProvider"]

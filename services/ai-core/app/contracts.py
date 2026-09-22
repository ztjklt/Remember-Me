"""Pydantic mirrors of the frozen Phase 1 integration contract."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MemoryType = Literal[
    "EVENT",
    "PERSON",
    "RELATIONSHIP",
    "PREFERENCE",
    "VALUE",
    "EMOTION",
]
SourceType = Literal[
    "SUBJECT",
    "THIRD_PARTY",
    "AI_INFERENCE",
    "OBJECTIVE",
    "CALIBRATION",
]


class ContractModel(BaseModel):
    """Common strict configuration for cross-module payloads."""

    model_config = ConfigDict(extra="forbid")


class AICoreInput(ContractModel):
    episode_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    trace_id: str | None = Field(default=None, min_length=1)
    subject_context: dict[str, Any] | None = None
    existing_model_version: str = Field(min_length=1)


class Evidence(ContractModel):
    evidence_id: str = Field(min_length=1)
    source_type: SourceType
    source_ref: str = Field(min_length=1)
    excerpt: str | None = None
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class MemoryItem(ContractModel):
    memory_type: MemoryType
    content: str = Field(min_length=1)
    source_type: SourceType
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    effective_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class AICoreOutput(ContractModel):
    memory_items: list[MemoryItem]
    graph_updates: list[dict[str, Any]]
    persona_updates: list[dict[str, Any]]
    evidence: list[Evidence]
    model_version: str = Field(min_length=1)


_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name: str) -> AICoreInput:
    """Load one checked-in Phase 1 input fixture without network access."""

    if not name or Path(name).name != name or Path(name).suffix:
        raise ValueError("fixture name must be a plain fixture stem")

    path = _FIXTURE_DIR / f"{name}.json"
    if path.parent != _FIXTURE_DIR:
        raise ValueError("fixture name must stay inside the fixture directory")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"unknown fixture: {name}") from exc

    return AICoreInput.model_validate(raw)


__all__ = [
    "AICoreInput",
    "AICoreOutput",
    "Evidence",
    "MemoryItem",
    "MemoryType",
    "SourceType",
    "load_fixture",
]

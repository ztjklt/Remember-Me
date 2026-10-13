"""Pydantic mirrors of the frozen Phase 1 integration contract."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, field_validator


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

    @field_validator("trace_id", "subject_context", mode="before")
    @classmethod
    def optional_but_not_nullable(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("omit optional fields instead of sending null")
        return value


class Evidence(ContractModel):
    evidence_id: str = Field(min_length=1)
    source_type: SourceType
    source_ref: str = Field(min_length=1)
    excerpt: str | None = None
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    confidence: StrictFloat | None = Field(default=None, ge=0, le=1)

    @field_validator("span_start", "span_end", mode="before")
    @classmethod
    def json_integer(cls, value: Any) -> Any:
        # JSON Schema accepts 1.0 as an integer, but never true or "1".
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError("span offsets must be JSON integers")
        return value


class MemoryItem(ContractModel):
    memory_type: MemoryType
    content: str = Field(min_length=1)
    source_type: SourceType
    evidence_ids: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    confidence: StrictFloat = Field(ge=0, le=1)
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    effective_at: AwareDatetime | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("effective_at", mode="before")
    @classmethod
    def datetime_not_epoch(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("effective_at must be an RFC 3339 datetime")
        if isinstance(value, str) and not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value,
        ):
            raise ValueError("effective_at must be an RFC 3339 datetime")
        return value

    @field_validator("effective_at")
    @classmethod
    def utc_datetime(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class PersonTrait(ContractModel):
    trait_id: str = Field(min_length=1)
    domain: Literal["IDENTITY", "EPISODIC_MEMORY", "RELATIONSHIPS", "PREFERENCES", "VALUES_BELIEFS", "DECISION_PATTERNS", "EXPRESSION"]
    statement: str = Field(min_length=1)
    context: str | None = None
    confidence: StrictFloat = Field(ge=0, le=1)
    source_type: SourceType
    evidence_ids: list[str]
    counter_evidence_ids: list[str]
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    status: Literal["active", "unresolved", "superseded"]
    model_version: str = Field(min_length=1)
    memory_item_ids: list[str] | None = None


class GraphFact(ContractModel):
    fact_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    kind: Literal["EVENT", "PERSON", "RELATIONSHIP"]
    content: str = Field(min_length=1)
    evidence_ids: list[str]
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    model_version: str = Field(min_length=1)


class AICoreOutput(ContractModel):
    memory_items: list[MemoryItem]
    graph_updates: list[GraphFact]
    persona_updates: list[PersonTrait]
    evidence: list[Evidence]
    model_version: str = Field(min_length=1)


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
if not _FIXTURE_DIR.is_dir():
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

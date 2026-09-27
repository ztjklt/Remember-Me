"""The Phase 1 shapes of `packages/contracts`, as Pydantic models.

A hand-written mirror rather than a runtime read of the JSON Schema: the service
needs these shapes for validation and serialization on every request, and pulling
jsonschema in for that would be a dependency for a file of straightforward
constraints. The mirror is not allowed to drift — `tests/test_contract_shapes.py`
reads the frozen schema and asserts that every enum, required field, and bound
here still matches it, so a contract change fails a test rather than a client.

`additionalProperties: false` in the schema becomes `extra="forbid"` here, for
the same reason: a field the contract does not define must be rejected rather
than silently accepted.

Only the Phase 1 shapes live here. The twin, voice, and calibration shapes are
Phase 2/3 and are deliberately absent.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import CaptureSource, EpisodeStatus, MemoryType, SourceType

# The contract revision these shapes mirror. Written onto every memory item as
# `schema_version`, so a stored memory says which shape it was validated against
# rather than which one happens to be current when it is read back.
SCHEMA_VERSION = "integration-contract-v0.2"

# Annotated rather than a shared Field(...) instance: the same constraint applies
# to several fields, and a FieldInfo reused across models is state they would
# share.
Confidence = Annotated[float, Field(ge=0, le=1)]


class ContractModel(BaseModel):
    """Base for every shape: unknown fields are refused, as the schema requires."""

    model_config = ConfigDict(extra="forbid")


class Evidence(ContractModel):
    """One source a memory item rests on (contract `evidence`)."""

    evidence_id: str = Field(min_length=1)
    source_type: SourceType
    source_ref: str = Field(min_length=1)
    excerpt: str | None = None
    span_start: int | None = Field(None, ge=0)
    span_end: int | None = Field(None, ge=0)
    # Spelled out rather than reusing Confidence: pydantic keeps an Annotated
    # constraint nested inside an Optional rather than hoisting it into the
    # field's metadata, so `Confidence | None` would carry the bounds where
    # nothing reads them from.
    confidence: float | None = Field(None, ge=0, le=1)


class MemoryItem(ContractModel):
    """One extracted memory (contract `memoryItem`).

    Every field the contract requires is required here, so a result that cannot
    say which model, prompt, and schema produced it is a validation failure
    rather than a row with holes in it.
    """

    memory_type: MemoryType
    content: str = Field(min_length=1)
    source_type: SourceType
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    effective_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        for evidence_id in value:
            if not evidence_id:
                raise ValueError("evidence_ids must not contain an empty id")
        if len(set(value)) != len(value):
            raise ValueError("evidence_ids must be unique")
        return value


class PersonTrait(ContractModel):
    trait_id: str = Field(min_length=1)
    domain: Literal["IDENTITY", "EPISODIC_MEMORY", "RELATIONSHIPS", "PREFERENCES", "VALUES_BELIEFS", "DECISION_PATTERNS", "EXPRESSION"]
    statement: str = Field(min_length=1)
    context: str | None = None
    confidence: Confidence
    source_type: SourceType
    evidence_ids: list[str]
    counter_evidence_ids: list[str]
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: Literal["active", "unresolved", "superseded"]
    model_version: str = Field(min_length=1)
    memory_item_ids: list[str] | None = None


class GraphFact(ContractModel):
    fact_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    kind: Literal["EVENT", "PERSON", "RELATIONSHIP"]
    content: str = Field(min_length=1)
    evidence_ids: list[str]
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    model_version: str = Field(min_length=1)


class CaptureEpisode(ContractModel):
    """What a client sends when it captures a recording (contract `captureEpisode`).

    The audio bytes are not part of this shape — the contract carries an
    `audio_ref`, and the bytes arrive as the multipart file part of the same
    request. `actor_id`, `recording_consent_id`, and `idempotency_key` are
    optional *in the schema* and required at this boundary; the upload endpoint
    enforces that, and says so, rather than encoding the difference here.
    """

    subject_id: str = Field(min_length=1)
    actor_id: str | None = Field(None, min_length=1)
    recording_consent_id: str | None = Field(None, min_length=1)
    idempotency_key: str | None = Field(None, min_length=1)
    audio_ref: str = Field(min_length=1)
    source: CaptureSource
    recorded_at: datetime
    duration_ms: int | None = Field(None, ge=0)
    metadata: dict[str, Any] | None = None


class EpisodeCreated(ContractModel):
    """The upload response (contract `episodeCreated`)."""

    episode_id: str = Field(min_length=1)
    upload_status: Literal["pending", "uploading", "uploaded", "failed"]


class ProcessingStatus(ContractModel):
    """What a client polls (contract `processingStatus`)."""

    episode_id: str = Field(min_length=1)
    status: EpisodeStatus
    trace_id: str | None = Field(None, min_length=1)
    progress: float | None = Field(None, ge=0, le=1)
    error_code: str | None = None
    error_message: str | None = None


class AICoreInput(ContractModel):
    """What Backend sends to AI Core (contract `aiCoreInput`)."""

    episode_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    existing_model_version: str = Field(min_length=1)
    trace_id: str | None = Field(None, min_length=1)
    subject_context: dict[str, Any] | None = None


class AICoreOutput(ContractModel):
    """What AI Core returns (contract `aiCoreOutput`).

    Parsed with this model, so a response that is missing a required field, uses
    an unregistered enum value, or carries an unexpected one fails as
    AI_SCHEMA_INVALID instead of writing a half-shaped memory into the record.
    """

    memory_items: list[MemoryItem]
    graph_updates: list[GraphFact]
    persona_updates: list[PersonTrait]
    evidence: list[Evidence]
    model_version: str = Field(min_length=1)


class EpisodeResult(ContractModel):
    """What a client reads once processing is ready (contract `episodeResult`)."""

    episode_id: str = Field(min_length=1)
    status: Literal["ready"]
    memory_items: list[MemoryItem]
    model_version: str = Field(min_length=1)
    trace_id: str | None = Field(None, min_length=1)

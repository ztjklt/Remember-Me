"""Agent loop v0.2 experimental: shared API and schema-worker vocabulary."""

from typing import Literal
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "agent-loop-v0.2-experimental"
Domain = Literal[
    "IDENTITY",
    "EPISODIC_MEMORY",
    "RELATIONSHIPS",
    "PREFERENCES",
    "VALUES",
    "DECISION_PATTERNS",
    "EXPRESSION",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Material(Contract):
    evidence_id: str = Field(min_length=1, max_length=64)
    episode_id: str | None = None
    excerpt: str = Field(min_length=1, max_length=12000)
    source_type: Literal["SUBJECT", "THIRD_PARTY", "OBJECTIVE", "CALIBRATION"]
    source_ref: str = Field(min_length=1)
    memory_type: str = "EVENT"
    observed_at: AwareDatetime
    context: str = Field(default="", max_length=1000)
    speaker_authority: Literal["SELF_ATTESTED", "UNVERIFIED"] = "UNVERIFIED"


class Trait(Contract):
    trait_id: str = Field(min_length=1, max_length=64)
    domain: Domain
    statement: str = Field(min_length=1, max_length=2000)
    context: str = Field(default="", max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=40)
    counter_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    status: Literal["CANDIDATE", "SUPPORTED", "CONFLICTED", "SUPERSEDED"] = "CANDIDATE"
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None


class Snapshot(Contract):
    subject_id: str
    revision: int = Field(ge=0)
    traits: list[Trait] = Field(default_factory=list, max_length=160)
    model_version: str
    prompt_version: str
    schema_version: Literal["agent-loop-v0.2-experimental"] = SCHEMA_VERSION
    updated_at: AwareDatetime | None = None
    limitations: list[str] = Field(default_factory=list)


class Change(Contract):
    action: Literal["ADD", "SUPPORT", "CONFLICT", "CHANGE"]
    target_trait_id: str | None = None
    domain: Domain
    statement: str = Field(min_length=1, max_length=2000)
    context: str = Field(default="", max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=40)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=1000)


class PersonaProposal(Contract):
    changes: list[Change] = Field(default_factory=list, max_length=40)


class PersonaInput(Contract):
    subject_id: str
    snapshot: Snapshot
    materials: list[Material] = Field(max_length=160)
    new_evidence_ids: list[str] = Field(max_length=40)


class PersonaResult(Contract):
    subject_id: str
    base_revision: int
    traits: list[Trait] = Field(max_length=160)
    changes: list[Change] = Field(max_length=40)
    model_version: str
    prompt_version: str
    schema_version: Literal["agent-loop-v0.2-experimental"] = SCHEMA_VERSION


class TwinInput(Contract):
    subject_id: str
    question: str = Field(min_length=1, max_length=2000)
    snapshot: Snapshot
    materials: list[Material] = Field(max_length=160)


class TwinDecision(Contract):
    response_type: Literal["ORIGINAL", "SIMULATION", "INSUFFICIENT"]
    answer: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=12)


class TwinAnswer(TwinDecision):
    subject_id: str
    revision: int
    evidence: list[Material] = Field(default_factory=list, max_length=12)
    model_version: str
    prompt_version: str
    schema_version: Literal["agent-loop-v0.2-experimental"] = SCHEMA_VERSION


class DimensionDiff(Contract):
    dimension: Literal[
        "DECISION", "REASONING", "VALUE_PRIORITY", "EMOTIONAL_REACTION", "EXPRESSION"
    ]
    assessment: Literal["ALIGNED", "DIFFERENT", "UNCERTAIN"]
    reason: str = Field(min_length=1, max_length=1000)


class Comparison(Contract):
    dimension_diffs: list[DimensionDiff] = Field(min_length=5, max_length=5)
    cause: Literal[
        "INSUFFICIENT_MATERIAL",
        "MODEL_ERROR",
        "CONTEXT_DEPENDENT",
        "CHANGED_VIEW",
        "UNCERTAIN",
    ]
    followup_questions: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def distinct_dimensions(self):
        if len({d.dimension for d in self.dimension_diffs}) != 5:
            raise ValueError("Each calibration dimension must occur exactly once")
        return self


class CompareInput(Contract):
    subject_id: str
    question: str
    locked_answer: TwinAnswer
    human_answer: str = Field(min_length=1, max_length=12000)


class GrantRequest(Contract):
    recording_consent_id: str = Field(min_length=1)
    cloud_twin_consent: Literal[True]
    subject_single_speaker: Literal[True]


class QuestionRequest(Contract):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class CalibrationSubmit(Contract):
    human_answer: str = Field(min_length=1, max_length=12000)
    expected_revision: int = Field(ge=0)

    @field_validator("human_answer")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value.strip()


class CalibrationView(Contract):
    calibration_id: str
    question: str
    locked_answer: TwinAnswer
    locked_at: AwareDatetime
    lock_digest: str
    state: Literal["LOCKED", "COMPLETED", "INVALIDATED"]
    comparison: Comparison | None = None
    resulting_revision: int | None = None


class Plan(Contract):
    subject_id: str
    revision: int
    question: str
    reason: str
    target_domain: Domain
    related_trait_ids: list[str] = Field(default_factory=list)
    scoring_method: Literal["HEURISTIC"] = "HEURISTIC"

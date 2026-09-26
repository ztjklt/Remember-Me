from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Restore the UTC offset on a stored timestamp.

    SQLite has no timezone-aware datetime type, so a value written as UTC comes
    back naive while PostgreSQL returns it with the offset. Everything this
    application writes is UTC (see utcnow), so re-attaching UTC states what was
    stored rather than guessing; without it the same field would serialize with
    an offset from one backend and without one from the other (ADR-0001 D3).
    """
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


class ConsentScope(StrEnum):
    """Consent scopes. Each is a separate grant, never a label on another grant.

    RECORDING covers capturing the subject's audio and text. VOICE covers the
    separate permission to build and use a voice profile from that audio. They are
    distinct values in the same table so that the verification rule is one query
    against one shape, and so that a recording consent can never satisfy a voice
    operation (ADR-0001 D7, Issue #9).

    A new scope is a deliberate act: it needs a value here, a migration extending
    the database constraint, and — if it crosses a module boundary — the
    Issue/proposal route CONTRIBUTING.md requires.
    """

    RECORDING = "RECORDING"
    VOICE = "VOICE"
    CLOUD_TWIN = "CLOUD_TWIN"


# The database refuses a scope this codebase does not register, so a typo or a
# hand-written row cannot create a grant that no verification rule will ever
# match. Written as SQL rather than as a SQLAlchemy expression so the migration
# can state the same list.
CONSENT_SCOPE_CHECK = "scope IN ({})".format(
    ", ".join(f"'{scope.value}'" for scope in ConsentScope)
)


def _enum_check(column: str, values: type[StrEnum]) -> str:
    """A CHECK constraint restricting one column to a registered set of values."""
    return f"{column} IN ({', '.join(f'{member.value!r}' for member in values)})"


class ConsentStatus(StrEnum):
    GRANTED = "granted"
    REVOKED = "revoked"


class EpisodeStatus(StrEnum):
    """Processing status of one Episode.

    The values are the contract's processingStatus enum, in order: an Episode is
    persisted as `uploaded` before any processing runs, and every later value
    means the stage named is the one being worked on. `failed` is terminal and
    the Episode stays readable (Issue #1's definition of done).
    """

    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    EXTRACTING = "extracting"
    MODELING = "modeling"
    READY = "ready"
    FAILED = "failed"


EPISODE_STATUS_CHECK = _enum_check("status", EpisodeStatus)


class CaptureSource(StrEnum):
    """Where a recording came from (contract captureEpisode.source)."""

    ANDROID_MIC = "ANDROID_MIC"
    IOS_MIC = "IOS_MIC"
    WORK_3200 = "WORK_3200"
    RECORDING_DEVICE = "RECORDING_DEVICE"
    IMPORT = "IMPORT"


CAPTURE_SOURCE_CHECK = _enum_check("source", CaptureSource)


class MemoryType(StrEnum):
    """What kind of memory one item holds (contract memoryItem.memory_type)."""

    EVENT = "EVENT"
    PERSON = "PERSON"
    RELATIONSHIP = "RELATIONSHIP"
    PREFERENCE = "PREFERENCE"
    VALUE = "VALUE"
    EMOTION = "EMOTION"


class SourceType(StrEnum):
    """Where a memory item or evidence came from (contract source_type).

    THIRD_PARTY is a first-class value here: recording that a memory rests on
    someone else's words is a fact worth storing, not one worth losing.
    """

    SUBJECT = "SUBJECT"
    THIRD_PARTY = "THIRD_PARTY"
    AI_INFERENCE = "AI_INFERENCE"
    OBJECTIVE = "OBJECTIVE"
    CALIBRATION = "CALIBRATION"


MEMORY_TYPE_CHECK = _enum_check("memory_type", MemoryType)
SOURCE_TYPE_CHECK = _enum_check("source_type", SourceType)


class JobState(StrEnum):
    """Lifecycle of one unit of processing work.

    `queued` and `running` are worker-active states; `waiting` pauses iOS work
    until the capturing Actor reviews STT output. An expired lease returns a job
    to `queued` rather than leaving it stuck (ADR-0001 D8).
    """

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobStage(StrEnum):
    """The processing stage a job is working on. One stage per worker tick."""

    TRANSCRIBE = "transcribe"
    EXTRACT = "extract"
    MODEL = "model"


JOB_STATE_CHECK = _enum_check("state", JobState)
JOB_STAGE_CHECK = _enum_check("stage", JobStage)


class Subject(Base):
    """The modeled person. Durable across Actor changes."""

    __tablename__ = "subjects"

    subject_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Actor(Base):
    """Whoever currently operates the app.

    May be the Subject or another person. Kept distinct from Subject from the
    start so Creator Mode and Legacy Mode can move between actors around one
    subject (Issue #8 principle note).
    """

    __tablename__ = "actors"
    __table_args__ = (Index("ix_actors_token_hash", "token_hash", unique=True),)

    actor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Only the digest of an actor token is stored. See app/security.py.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Consent(Base):
    """A granted permission record tying a Subject to the Actor who granted it.

    A sensitive operation must verify an active consent for the subject and the
    required scope. Merely recording a consent reference is not enough
    (ADR-0001 D7).
    """

    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_subject_scope_status", "subject_id", "scope", "status"),
        CheckConstraint(CONSENT_SCOPE_CHECK, name="ck_consents_scope"),
    )

    consent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("subjects.subject_id", ondelete="RESTRICT"), nullable=False
    )
    granted_by_actor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("actors.actor_id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Episode(Base):
    """One captured recording, from the moment it is uploaded.

    The row is written **before** any speech-to-text or AI work runs, and it holds
    a reference to the audio plus that object's metadata — never the bytes
    (ADR-0001 D5). A downstream failure sets `status` to failed and leaves this
    row and the object it points at untouched: the original life record is not
    something a failing model gets to destroy (Issue #1's definition of done).

    `idempotency_key` is unique per (subject, actor), which is what makes a
    retried upload return the Episode that already exists rather than a second
    one (ADR-0001 D12).
    """

    __tablename__ = "episodes"
    __table_args__ = (
        Index(
            "ix_episodes_idempotency",
            "subject_id",
            "actor_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_episodes_subject_created", "subject_id", "created_at"),
        CheckConstraint(EPISODE_STATUS_CHECK, name="ck_episodes_status"),
        CheckConstraint(CAPTURE_SOURCE_CHECK, name="ck_episodes_source"),
    )

    episode_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("subjects.subject_id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("actors.actor_id", ondelete="RESTRICT"), nullable=False
    )
    recording_consent_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("consents.consent_id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capture_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # What the client called this audio (contract captureEpisode.audio_ref). Kept
    # beside the object key because they are different facts: the key is where
    # Backend put the bytes, this is what the recording was called before it
    # arrived, and that is worth not losing.
    audio_ref: Mapped[str] = mapped_column(String(1024), nullable=False)

    # The object reference and its metadata. The bytes live in object storage.
    audio_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    audio_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    audio_checksum: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # The trace id of the request that created this Episode, carried through
    # processing so one identifier spans upload, STT, AI Core, and the result.
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)

    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Preserve machine output when the Subject confirms or edits the transcript.
    stt_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript_reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stt_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stt_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_proposals: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Job(Base):
    """One unit of processing work for one Episode.

    A row in this table is the queue: there is no broker, and the worker claims
    work by taking a lease on a queued row (ADR-0001 D8). `stage` advances one
    step per tick, so the Episode's status is observable from outside the worker.

    `attempts` counts attempts at the *current* stage and resets when the stage
    advances, which is what bounds a poison pill without a transient failure in
    one stage spending the next stage's budget.

    The job id is internal and never appears in an API response: the contract's
    job-id assertion is a hard rule, and clients address work by `episode_id`.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        # Phase 1 has exactly one job per Episode, which holds the "exactly one
        # Episode" guarantee end to end: a duplicate upload cannot queue a
        # second run of the same recording.
        Index("ix_jobs_episode", "episode_id", unique=True),
        Index("ix_jobs_state_available", "state", "available_at"),
        CheckConstraint(JOB_STATE_CHECK, name="ck_jobs_state"),
        CheckConstraint(JOB_STAGE_CHECK, name="ck_jobs_stage"),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("episodes.episode_id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Evidence(Base):
    """One source an AI Core memory item rests on.

    Stored rather than discarded because a memory whose evidence is gone cannot
    be traced back to what the subject actually said, and re-deriving it later is
    impossible: the model that produced it may be gone too. `source_type` records
    whether the words were the subject's or a third party's.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_episode", "episode_id"),
        CheckConstraint(SOURCE_TYPE_CHECK, name="ck_evidence_source_type"),
    )

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("episodes.episode_id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class MemoryItem(Base):
    """One extracted memory, stored with the provenance and versions it carries.

    Every field the contract requires is required here too, including
    `model_version`, `prompt_version`, and `schema_version`: a memory whose origin
    is unrecorded cannot be re-evaluated when the model or the schema changes.

    `evidence_ids` is the set of `Evidence.evidence_id` values this item rests on.
    """

    __tablename__ = "memory_items"
    __table_args__ = (
        Index("ix_memory_items_episode", "episode_id", "ordinal"),
        CheckConstraint(MEMORY_TYPE_CHECK, name="ck_memory_items_memory_type"),
        CheckConstraint(SOURCE_TYPE_CHECK, name="ck_memory_items_source_type"),
    )

    memory_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("episodes.episode_id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)

    effective_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    item_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


PERSON_DOMAINS = (
    "IDENTITY", "EPISODIC_MEMORY", "RELATIONSHIPS", "PREFERENCES",
    "VALUES_BELIEFS", "DECISION_PATTERNS", "EXPRESSION",
)


class PersonTrait(Base):
    __tablename__ = "person_traits"
    __table_args__ = (Index("ix_person_traits_subject_domain", "subject_id", "domain"),)

    trait_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    counter_evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    memory_item_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class GraphFact(Base):
    __tablename__ = "graph_facts"
    fact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    memory_item_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaptureQuestion(Base):
    __tablename__ = "capture_questions"
    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    target_domain: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ModelRevision(Base):
    __tablename__ = "model_revisions"
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MemoryAudit(Base):
    __tablename__ = "memory_audit"
    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_item_id: Mapped[str] = mapped_column(String(64), ForeignKey("memory_items.memory_item_id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("actors.actor_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_content: Mapped[str] = mapped_column(Text, nullable=False)
    new_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PairingCode(Base):
    __tablename__ = "pairing_codes"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("actors.actor_id"), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceCredential(Base):
    __tablename__ = "device_credentials"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("actors.actor_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"
    __table_args__ = (Index("ix_memory_embeddings_subject", "subject_id"),)

    memory_item_id: Mapped[str] = mapped_column(String(64), ForeignKey("memory_items.memory_item_id"), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    vector: Mapped[list] = mapped_column(JSON, nullable=False)


class TwinAnswer(Base):
    __tablename__ = "twin_answers"
    __table_args__ = (Index("ix_twin_answers_subject", "subject_id", "created_at"),)

    answer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("actors.actor_id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    response_type: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    memory_item_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    person_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalibrationRun(Base):
    __tablename__ = "calibration_runs"
    __table_args__ = (Index("ix_calibration_runs_subject", "subject_id", "created_at"),)

    calibration_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("actors.actor_id"), nullable=False)
    twin_answer_id: Mapped[str] = mapped_column(String(64), ForeignKey("twin_answers.answer_id"), nullable=False, unique=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    locked_answer: Mapped[str] = mapped_column(Text, nullable=False)
    locked_response_type: Mapped[str] = mapped_column(String(16), nullable=False)
    locked_model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    locked_person_model_version: Mapped[int] = mapped_column(Integer(), nullable=False)
    locked_evidence_ids: Mapped[list] = mapped_column(JSON(), nullable=False)
    source_snapshot: Mapped[list] = mapped_column(JSON(), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    human_episode_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("episodes.episode_id"), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension_diffs: Mapped[list] = mapped_column(JSON(), nullable=False, default=list)
    suggested_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey("subjects.subject_id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("actors.actor_id"), nullable=False)
    voice_consent_id: Mapped[str] = mapped_column(String(64), ForeignKey("consents.consent_id"), nullable=False)
    sample_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    sample_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceAsset(Base):
    __tablename__ = "voice_assets"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    answer_id: Mapped[str] = mapped_column(String(64), ForeignKey("twin_answers.answer_id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), ForeignKey("voice_profiles.profile_id"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

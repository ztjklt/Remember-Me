"""episodes jobs memory items evidence

Adds the ingestion schema: the Episode, the processing job that advances it, and
the memory items and evidence an AI Core result produces.

Column sets, index names, and the CHECK constraints here must match
app/models.py — tests/test_migrations.py compares the migrated schema against the
models and fails on drift. The enum lists are written out literally rather than
imported, because a migration is a snapshot of the schema at one revision.

Revision ID: 0003_ingestion
Revises: 0002_consent_scopes
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ingestion"
down_revision: str | None = "0002_consent_scopes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EPISODE_STATUS = "status IN ('uploaded', 'transcribing', 'extracting', 'modeling', 'ready', 'failed')"
CAPTURE_SOURCE = "source IN ('ANDROID_MIC', 'WORK_3200', 'RECORDING_DEVICE', 'IMPORT')"
JOB_STATE = "state IN ('queued', 'running', 'succeeded', 'failed')"
JOB_STAGE = "stage IN ('transcribe', 'extract', 'model')"
SOURCE_TYPE = (
    "source_type IN ('SUBJECT', 'THIRD_PARTY', 'AI_INFERENCE', 'OBJECTIVE', 'CALIBRATION')"
)
MEMORY_TYPE = (
    "memory_type IN ('EVENT', 'PERSON', 'RELATIONSHIP', 'PREFERENCE', 'VALUE', 'EMOTION')"
)


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("episode_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "subject_id",
            sa.String(length=64),
            sa.ForeignKey("subjects.subject_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.String(length=64),
            sa.ForeignKey("actors.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "recording_consent_id",
            sa.String(length=64),
            sa.ForeignKey("consents.consent_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("capture_metadata", sa.JSON(), nullable=True),
        sa.Column("audio_ref", sa.String(length=1024), nullable=False),
        sa.Column("audio_object_key", sa.String(length=1024), nullable=False),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=False),
        sa.Column("audio_content_type", sa.String(length=128), nullable=False),
        sa.Column("audio_checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("stt_backend", sa.String(length=32), nullable=True),
        sa.Column("stt_model_version", sa.String(length=64), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(EPISODE_STATUS, name="ck_episodes_status"),
        sa.CheckConstraint(CAPTURE_SOURCE, name="ck_episodes_source"),
    )
    # Unique per (subject, actor): this is what makes a retried upload return the
    # Episode that already exists instead of creating a second one (ADR D12).
    op.create_index(
        "ix_episodes_idempotency",
        "episodes",
        ["subject_id", "actor_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_episodes_subject_created", "episodes", ["subject_id", "created_at"]
    )

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(length=64),
            sa.ForeignKey("episodes.episode_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(JOB_STATE, name="ck_jobs_state"),
        sa.CheckConstraint(JOB_STAGE, name="ck_jobs_stage"),
    )
    # One job per Episode in Phase 1.
    op.create_index("ix_jobs_episode", "jobs", ["episode_id"], unique=True)
    op.create_index("ix_jobs_state_available", "jobs", ["state", "available_at"])

    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(length=64),
            sa.ForeignKey("episodes.episode_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=1024), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(SOURCE_TYPE, name="ck_evidence_source_type"),
    )
    op.create_index("ix_evidence_episode", "evidence", ["episode_id"])

    op.create_table(
        "memory_items",
        sa.Column("memory_item_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(length=64),
            sa.ForeignKey("episodes.episode_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(MEMORY_TYPE, name="ck_memory_items_memory_type"),
        sa.CheckConstraint(SOURCE_TYPE, name="ck_memory_items_source_type"),
    )
    op.create_index("ix_memory_items_episode", "memory_items", ["episode_id", "ordinal"])


def downgrade() -> None:
    op.drop_index("ix_memory_items_episode", table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_index("ix_evidence_episode", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_jobs_state_available", table_name="jobs")
    op.drop_index("ix_jobs_episode", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_episodes_subject_created", table_name="episodes")
    op.drop_index("ix_episodes_idempotency", table_name="episodes")
    op.drop_table("episodes")
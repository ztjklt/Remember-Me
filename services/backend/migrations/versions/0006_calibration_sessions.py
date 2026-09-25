"""Lock Twin answers before collecting Actor calibration feedback.

Revision ID: 0006_calibration_sessions
Revises: 0005_memory_feedback
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_calibration_sessions"
down_revision: str | None = "0005_memory_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calibration_sessions",
        sa.Column("calibration_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("cloud_twin_consent_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("locked_answer", sa.Text(), nullable=False),
        sa.Column("response_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("human_answer", sa.Text(), nullable=True),
        sa.Column("dimension_gaps", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.subject_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.actor_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cloud_twin_consent_id"], ["consents.consent_id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_calibration_subject_actor", "calibration_sessions",
        ["subject_id", "actor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_calibration_subject_actor", table_name="calibration_sessions")
    op.drop_table("calibration_sessions")

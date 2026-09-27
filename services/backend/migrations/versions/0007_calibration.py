"""Locked Twin answer and linked human Episode for calibration.

Revision ID: 0007_calibration
Revises: 0006_twin_voice
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_calibration"
down_revision = "0006_twin_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_runs",
        sa.Column("calibration_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id"), nullable=False),
        sa.Column("twin_answer_id", sa.String(64), sa.ForeignKey("twin_answers.answer_id"), nullable=False, unique=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("locked_answer", sa.Text(), nullable=False),
        sa.Column("locked_response_type", sa.String(16), nullable=False),
        sa.Column("locked_model_version", sa.String(128), nullable=False),
        sa.Column("locked_person_model_version", sa.Integer(), nullable=False),
        sa.Column("locked_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("human_episode_id", sa.String(64), sa.ForeignKey("episodes.episode_id"), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("dimension_diffs", sa.JSON(), nullable=False),
        sa.Column("suggested_question", sa.Text(), nullable=True),
        sa.Column("comparison_model_version", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('awaiting_human', 'complete', 'stale')", name="ck_calibration_runs_status"),
    )
    op.create_index("ix_calibration_runs_subject", "calibration_runs", ["subject_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_calibration_runs_subject", table_name="calibration_runs")
    op.drop_table("calibration_runs")

"""Pause iOS extraction until the subject reviews the STT transcript.

Revision ID: 0005_transcript_review
Revises: 0004_person_model
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_transcript_review"
down_revision = "0004_person_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("episodes") as batch:
        batch.add_column(sa.Column("stt_transcript", sa.Text(), nullable=True))
        batch.add_column(sa.Column("transcript_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("transcript_reviewed_by", sa.String(64), nullable=True))
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("ck_jobs_state", type_="check")
        batch.create_check_constraint(
            "ck_jobs_state", "state IN ('queued', 'running', 'waiting', 'succeeded', 'failed')"
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("ck_jobs_state", type_="check")
        batch.create_check_constraint(
            "ck_jobs_state", "state IN ('queued', 'running', 'succeeded', 'failed')"
        )
    with op.batch_alter_table("episodes") as batch:
        batch.drop_column("transcript_reviewed_by")
        batch.drop_column("transcript_reviewed_at")
        batch.drop_column("stt_transcript")

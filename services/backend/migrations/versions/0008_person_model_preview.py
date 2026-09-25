"""Persist actor-partitioned, evidence-linked Person Model previews.

Revision ID: 0008_person_model_preview
Revises: 0007_legacy_preview
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_person_model_preview"
down_revision: str | None = "0007_legacy_preview"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "person_model_snapshots",
        sa.Column("subject_id", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(64), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_memory_ids", sa.JSON(), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.subject_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.actor_id"], ondelete="RESTRICT"),
    )


def downgrade() -> None:
    op.drop_table("person_model_snapshots")

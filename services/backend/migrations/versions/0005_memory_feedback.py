"""Track actor correction proposals without rewriting AI provenance.

Revision ID: 0005_memory_feedback
Revises: 0004_cloud_twin_consent
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_memory_feedback"
down_revision: str | None = "0004_cloud_twin_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_feedback",
        sa.Column("memory_item_id", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("proposed_content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["memory_item_id"], ["memory_items.memory_item_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.actor_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("status = 'CORRECT'", name="ck_memory_feedback_status"),
    )


def downgrade() -> None:
    op.drop_table("memory_feedback")

"""Persist optional, versioned AI assessment of calibration answers.

Revision ID: 0009_calibration_assessments
Revises: 0008_person_model_preview
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_calibration_assessments"
down_revision: str | None = "0008_person_model_preview"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("calibration_sessions") as batch:
        batch.add_column(sa.Column("ai_assessment", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("calibration_sessions") as batch:
        batch.drop_column("assessed_at")
        batch.drop_column("ai_assessment")

"""Persist semantic traits, entity graph, and synthesis provenance.

Revision ID: 0013_semantic_person_model
Revises: 0012_calibration_confirmation
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0013_semantic_person_model"
down_revision: str | None = "0012_calibration_confirmation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("person_model_snapshots") as batch:
        batch.add_column(sa.Column("semantic_graph", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("synthesis_model_version", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("person_model_snapshots") as batch:
        batch.drop_column("synthesis_model_version")
        batch.drop_column("semantic_graph")

"""Record explicit confirmation before calibration affects model planning.

Revision ID: 0012_calibration_confirmation
Revises: 0011_accounts
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0012_calibration_confirmation"
down_revision: str | None = "0011_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("calibration_sessions") as batch:
        batch.add_column(sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("person_model_snapshots") as batch:
        batch.add_column(sa.Column("calibration_updates", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("person_model_snapshots") as batch:
        batch.drop_column("calibration_updates")
    with op.batch_alter_table("calibration_sessions") as batch:
        batch.drop_column("confirmed_at")

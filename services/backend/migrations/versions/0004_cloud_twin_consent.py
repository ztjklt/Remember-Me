"""Add independent CLOUD_TWIN consent for iOS Twin queries.

Revision ID: 0004_cloud_twin_consent
Revises: 0003_ingestion
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_cloud_twin_consent"
down_revision: str | None = "0003_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite requires a table rebuild to change a CHECK constraint. PostgreSQL
    # uses ALTER TABLE. Existing RECORDING and VOICE grants keep their meaning.
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("ck_consents_scope", type_="check")
        batch.create_check_constraint(
            "ck_consents_scope", "scope IN ('RECORDING', 'VOICE', 'CLOUD_TWIN')"
        )


def downgrade() -> None:
    # Downgrade is safe only after CLOUD_TWIN grants have been removed.
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("ck_consents_scope", type_="check")
        batch.create_check_constraint(
            "ck_consents_scope", "scope IN ('RECORDING', 'VOICE')"
        )

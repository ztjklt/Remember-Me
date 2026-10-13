"""registered consent scopes

Adds the VOICE consent scope alongside RECORDING and constrains the column to the
registered scopes, so the database refuses a grant that no verification rule could
ever match. The scope list is written out literally rather than imported from
app.models: a migration is a snapshot of the schema at one revision and must not
change meaning when the application changes.

Revision ID: 0002_consent_scopes
Revises: 0001_initial
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_consent_scopes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE_CHECK = "scope IN ('RECORDING', 'VOICE')"


def upgrade() -> None:
    # Batch mode because SQLite cannot add a constraint in place; the dialect
    # rebuilds the table and carries the existing foreign keys and indexes over.
    # PostgreSQL takes the plain ALTER TABLE path.
    with op.batch_alter_table("consents") as batch:
        batch.create_check_constraint("ck_consents_scope", SCOPE_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("ck_consents_scope", type_="check")
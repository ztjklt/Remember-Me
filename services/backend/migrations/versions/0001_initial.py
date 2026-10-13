"""initial subjects actors consents

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("subject_id", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "actors",
        sa.Column("actor_id", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_actors_token_hash", "actors", ["token_hash"], unique=True)

    op.create_table(
        "consents",
        sa.Column("consent_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "subject_id",
            sa.String(length=64),
            sa.ForeignKey("subjects.subject_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_actor_id",
            sa.String(length=64),
            sa.ForeignKey("actors.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_consents_subject_scope_status",
        "consents",
        ["subject_id", "scope", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_consents_subject_scope_status", table_name="consents")
    op.drop_table("consents")
    op.drop_index("ix_actors_token_hash", table_name="actors")
    op.drop_table("actors")
    op.drop_table("subjects")
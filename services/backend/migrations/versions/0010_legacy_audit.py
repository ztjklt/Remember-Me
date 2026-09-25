"""Freeze preview model revision and audit recipient access.

Revision ID: 0010_legacy_audit
Revises: 0009_calibration_assessments
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_legacy_audit"
down_revision: str | None = "0009_calibration_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("legacy_grants") as batch:
        batch.add_column(sa.Column("baseline_model_revision", sa.Integer(), nullable=True))
    op.create_table(
        "legacy_audit_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("grant_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["grant_id"], ["legacy_grants.grant_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.actor_id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "action IN ('CREATED', 'ACTIVATED', 'READ', 'REVOKED')",
            name="ck_legacy_audit_action",
        ),
    )
    op.create_index(
        "ix_legacy_audit_grant_time", "legacy_audit_events", ["grant_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_legacy_audit_grant_time", table_name="legacy_audit_events")
    op.drop_table("legacy_audit_events")
    with op.batch_alter_table("legacy_grants") as batch:
        batch.drop_column("baseline_model_revision")

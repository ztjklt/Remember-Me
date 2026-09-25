"""Independent digital handover consent and revocable Legacy rehearsal grants.

Revision ID: 0007_legacy_preview
Revises: 0006_calibration_sessions
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_legacy_preview"
down_revision: str | None = "0006_calibration_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("ck_consents_scope", type_="check")
        batch.create_check_constraint(
            "ck_consents_scope",
            "scope IN ('RECORDING', 'VOICE', 'CLOUD_TWIN', 'DIGITAL_HANDOVER')",
        )
    op.create_table(
        "legacy_grants",
        sa.Column("grant_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("grantor_actor_id", sa.String(64), nullable=False),
        sa.Column("recipient_actor_id", sa.String(64), nullable=False),
        sa.Column("handover_consent_id", sa.String(64), nullable=False),
        sa.Column("allowed_domains", sa.JSON(), nullable=False),
        sa.Column("snapshot_memory_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.subject_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grantor_actor_id"], ["actors.actor_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_actor_id"], ["actors.actor_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["handover_consent_id"], ["consents.consent_id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PREVIEW_ACTIVE', 'REVOKED')",
            name="ck_legacy_grants_status",
        ),
    )
    op.create_index(
        "ix_legacy_recipient_subject_status", "legacy_grants",
        ["recipient_actor_id", "subject_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_legacy_recipient_subject_status", table_name="legacy_grants")
    op.drop_table("legacy_grants")
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("ck_consents_scope", type_="check")
        batch.create_check_constraint(
            "ck_consents_scope", "scope IN ('RECORDING', 'VOICE', 'CLOUD_TWIN')"
        )

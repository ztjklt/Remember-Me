"""Email accounts, one-time challenges, expiring sessions, and claim audit.

Revision ID: 0011_accounts
Revises: 0010_legacy_audit
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_accounts"
down_revision: str | None = "0010_legacy_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_challenges",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_table(
        "login_sessions",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("access_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "account_claims",
        sa.Column("claim_id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), sa.ForeignKey("accounts.email"), nullable=False),
        sa.Column("old_actor_id", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_claims")
    op.drop_table("login_sessions")
    op.drop_table("email_challenges")
    op.drop_table("accounts")

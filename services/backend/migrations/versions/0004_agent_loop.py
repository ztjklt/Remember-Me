"""Experimental Agent loop persistence; no change to frozen Phase 1 enums."""

from alembic import op
import sqlalchemy as sa

revision = "0004_agent_loop"
down_revision = "0003_ingestion"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_states",
        sa.Column("state_id", sa.String(64), primary_key=True),
        sa.Column(
            "subject_id",
            sa.String(64),
            sa.ForeignKey("subjects.subject_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.String(64),
            sa.ForeignKey("actors.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "recording_consent_id",
            sa.String(64),
            sa.ForeignKey("consents.consent_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("excluded_episode_ids", sa.JSON(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "agent_revisions",
        sa.Column("revision_id", sa.String(64), primary_key=True),
        sa.Column(
            "state_id",
            sa.String(64),
            sa.ForeignKey("agent_states.state_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("processed_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_revisions_state_id", "agent_revisions", ["state_id"])
    op.create_table(
        "agent_calibrations",
        sa.Column("calibration_id", sa.String(64), primary_key=True),
        sa.Column(
            "state_id",
            sa.String(64),
            sa.ForeignKey("agent_states.state_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("locked_answer", sa.JSON(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("human_answer", sa.Text(), nullable=True),
        sa.Column("comparison", sa.JSON(), nullable=True),
        sa.Column("resulting_revision", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_agent_calibrations_state_id", "agent_calibrations", ["state_id"]
    )
    op.create_table(
        "agent_materials",
        sa.Column("evidence_id", sa.String(64), primary_key=True),
        sa.Column(
            "state_id",
            sa.String(64),
            sa.ForeignKey("agent_states.state_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "calibration_id",
            sa.String(64),
            sa.ForeignKey("agent_calibrations.calibration_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_materials_state_id", "agent_materials", ["state_id"])


def downgrade():
    for name in (
        "agent_materials",
        "agent_calibrations",
        "agent_revisions",
        "agent_states",
    ):
        op.drop_table(name)

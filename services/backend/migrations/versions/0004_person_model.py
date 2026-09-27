"""iOS capture and evidence-backed person model.

Revision ID: 0004_person_model
Revises: 0003_ingestion
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_person_model"
down_revision = "0003_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("episodes") as batch:
        batch.drop_constraint("ck_episodes_source", type_="check")
        batch.create_check_constraint(
            "ck_episodes_source",
            "source IN ('ANDROID_MIC', 'IOS_MIC', 'WORK_3200', 'RECORDING_DEVICE', 'IMPORT')",
        )
        batch.add_column(sa.Column("model_proposals", sa.JSON(), nullable=True))
    op.add_column("memory_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "person_traits",
        sa.Column("trait_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("counter_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("memory_item_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_person_traits_subject_domain", "person_traits", ["subject_id", "domain"])
    op.create_table(
        "graph_facts",
        sa.Column("fact_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("memory_item_ids", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "capture_questions",
        sa.Column("question_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("target_domain", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "model_revisions",
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "memory_audit",
        sa.Column("audit_id", sa.String(64), primary_key=True),
        sa.Column("memory_item_id", sa.String(64), sa.ForeignKey("memory_items.memory_item_id"), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("previous_content", sa.Text(), nullable=False),
        sa.Column("new_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pairing_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id"), nullable=False),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "device_credentials",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("device_credentials")
    op.drop_table("pairing_codes")
    op.drop_table("memory_audit")
    op.drop_table("model_revisions")
    op.drop_table("capture_questions")
    op.drop_table("graph_facts")
    op.drop_index("ix_person_traits_subject_domain", table_name="person_traits")
    op.drop_table("person_traits")
    op.drop_column("memory_items", "deleted_at")
    with op.batch_alter_table("episodes") as batch:
        batch.drop_column("model_proposals")
        batch.drop_constraint("ck_episodes_source", type_="check")
        batch.create_check_constraint(
            "ck_episodes_source",
            "source IN ('ANDROID_MIC', 'WORK_3200', 'RECORDING_DEVICE', 'IMPORT')",
        )

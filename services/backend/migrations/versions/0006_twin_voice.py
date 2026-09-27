"""Subject-scoped retrieval, Twin answer provenance, and local Voice assets.

Revision ID: 0006_twin_voice
Revises: 0005_transcript_review
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_twin_voice"
down_revision = "0005_transcript_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("ck_consents_scope", type_="check")
        batch.create_check_constraint("ck_consents_scope", "scope IN ('RECORDING', 'VOICE', 'CLOUD_TWIN')")
    op.create_table(
        "memory_embeddings",
        sa.Column("memory_item_id", sa.String(64), sa.ForeignKey("memory_items.memory_item_id"), primary_key=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
    )
    op.create_index("ix_memory_embeddings_subject", "memory_embeddings", ["subject_id"])
    op.create_table(
        "twin_answers",
        sa.Column("answer_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("response_type", sa.String(16), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("memory_item_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("person_model_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("response_type IN ('ORIGINAL', 'SIMULATION', 'UNKNOWN')", name="ck_twin_answers_response_type"),
    )
    op.create_index("ix_twin_answers_subject", "twin_answers", ["subject_id", "created_at"])
    op.create_table(
        "voice_profiles",
        sa.Column("profile_id", sa.String(64), primary_key=True),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.subject_id"), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.actor_id"), nullable=False),
        sa.Column("voice_consent_id", sa.String(64), sa.ForeignKey("consents.consent_id"), nullable=False),
        sa.Column("sample_object_key", sa.String(1024), nullable=False),
        sa.Column("sample_transcript", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "voice_assets",
        sa.Column("asset_id", sa.String(64), primary_key=True),
        sa.Column("answer_id", sa.String(64), sa.ForeignKey("twin_answers.answer_id"), nullable=False),
        sa.Column("profile_id", sa.String(64), sa.ForeignKey("voice_profiles.profile_id"), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("voice_assets")
    op.drop_table("voice_profiles")
    op.drop_index("ix_twin_answers_subject", table_name="twin_answers")
    op.drop_table("twin_answers")
    op.drop_index("ix_memory_embeddings_subject", table_name="memory_embeddings")
    op.drop_table("memory_embeddings")
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("ck_consents_scope", type_="check")
        batch.create_check_constraint("ck_consents_scope", "scope IN ('RECORDING', 'VOICE')")

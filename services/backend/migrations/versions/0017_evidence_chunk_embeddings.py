"""Private original-evidence RAG cache; no mobile/API contract changes."""
from alembic import op
import sqlalchemy as sa
from app.vector_type import vector_type

revision = '0017_evidence_chunks'
down_revision = '0016_share_invitations'
branch_labels = depends_on = None


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public')
    op.create_table('evidence_chunk_embeddings',
        sa.Column('chunk_id', sa.String(64), primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False),
        sa.Column('evidence_id', sa.String(128), sa.ForeignKey('evidence.evidence_id', ondelete='CASCADE'), nullable=False),
        sa.Column('span_start', sa.Integer, nullable=False),
        sa.Column('span_end', sa.Integer, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('model_version', sa.String(128), nullable=False),
        sa.Column('vector', vector_type(), nullable=False))
    op.create_index('ix_evidence_chunks_subject_model', 'evidence_chunk_embeddings', ['subject_id', 'model_version'])


def downgrade():
    op.drop_table('evidence_chunk_embeddings')
    # The extension may be shared by other schemas. Never remove it here.

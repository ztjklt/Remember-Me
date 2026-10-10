"""Explicit approval and durable profile refresh, no colleague migration renumbering."""
from alembic import op
import sqlalchemy as sa
revision = '0009_profile_candidates'
down_revision = '0008_agent_loop'
branch_labels = depends_on = None

def upgrade():
    op.create_table('profile_candidates',
        sa.Column('candidate_id', sa.String(64), primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False),
        sa.Column('domain', sa.String(32), nullable=False), sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False), sa.Column('context', sa.Text(), nullable=False),
        sa.Column('evidence_ids', sa.JSON(), nullable=False), sa.Column('counter_evidence_ids', sa.JSON(), nullable=False),
        sa.Column('independent_episodes', sa.Integer(), nullable=False), sa.Column('source_basis', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False), sa.Column('model_version', sa.String(128), nullable=False),
        sa.Column('prompt_version', sa.String(128), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('profile_refreshes',
        sa.Column('job_id', sa.String(64), primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False),
        sa.Column('actor_id', sa.String(64), sa.ForeignKey('actors.actor_id'), nullable=False),
        sa.Column('consent_id', sa.String(64), nullable=False), sa.Column('status', sa.String(16), nullable=False),
        sa.Column('error', sa.Text(), nullable=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table('profile_refreshes')
    op.drop_table('profile_candidates')

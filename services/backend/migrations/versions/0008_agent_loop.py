"""Explicit ownership, story grants, revisions and question requests."""
from alembic import op
import sqlalchemy as sa

revision = "0008_agent_loop"
down_revision = "0007_calibration"
branch_labels = depends_on = None


def upgrade():
    # SQLite supports adding nullable REFERENCES without rebuilding the parent
    # table (which is already referenced by episodes and consents).
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('ALTER TABLE subjects ADD COLUMN owner_actor_id VARCHAR(64) REFERENCES actors(actor_id)')
    else:
        op.add_column('subjects', sa.Column('owner_actor_id', sa.String(64), sa.ForeignKey('actors.actor_id'), nullable=True))
    op.add_column('memory_items', sa.Column('review_state', sa.String(16), nullable=False, server_default='active'))
    op.create_table('story_grants',
        sa.Column('grant_id', sa.String(64), primary_key=True),
        sa.Column('episode_id', sa.String(64), sa.ForeignKey('episodes.episode_id'), nullable=False),
        sa.Column('reader_actor_id', sa.String(64), sa.ForeignKey('actors.actor_id'), nullable=False),
        sa.Column('cloud_processing_allowed', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('cloud_processing_allowed IN (0,1)', name='ck_grant_cloud'))
    op.create_index('ix_story_grants_episode_id', 'story_grants', ['episode_id'])
    op.create_index('ix_story_grants_reader_actor_id', 'story_grants', ['reader_actor_id'])
    op.create_table('memory_revisions',
        sa.Column('revision_id', sa.String(64), primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False),
        sa.Column('target_memory_id', sa.String(64), sa.ForeignKey('memory_items.memory_item_id'), nullable=False),
        sa.Column('episode_id', sa.String(64), sa.ForeignKey('episodes.episode_id'), nullable=False, unique=True),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('time_text', sa.String(200)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('supplement','correction','change')", name='ck_revision_kind'),
        sa.CheckConstraint("status IN ('pending','confirmed')", name='ck_revision_status'))
    op.create_table('question_requests',
        sa.Column('request_id', sa.String(64), primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False),
        sa.Column('actor_id', sa.String(64), sa.ForeignKey('actors.actor_id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('answer_episode_id', sa.String(64), sa.ForeignKey('episodes.episode_id')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','snoozed','declined','answered')", name='ck_question_request_status'))


def downgrade():
    op.drop_table('question_requests')
    op.drop_table('memory_revisions')
    op.drop_table('story_grants')
    op.drop_column('memory_items', 'review_state')
    op.drop_column('subjects', 'owner_actor_id')

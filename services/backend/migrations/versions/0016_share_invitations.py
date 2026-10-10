"""Invitations coordinate review; existing story_grants remain authoritative."""
from alembic import op
import sqlalchemy as sa
revision='0016_share_invitations'
down_revision='0015_narrative'
branch_labels=depends_on=None


def upgrade():
    op.create_table('share_invitations',
        sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False,index=True),
        sa.Column('creator_actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('recipient_actor_id',sa.String(64),sa.ForeignKey('actors.actor_id')),
        sa.Column('code_hash',sa.String(64),unique=True),sa.Column('status',sa.String(16),nullable=False),
        sa.Column('selection',sa.JSON,nullable=False),sa.Column('source_version',sa.String(64),nullable=False),
        sa.Column('cloud_processing_allowed',sa.Boolean,nullable=False),
        sa.Column('grant_ids',sa.JSON,nullable=False),sa.Column('created_grant_ids',sa.JSON,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('approved_at',sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table('share_invitations')

"""Explicit contribution grants, text letters and read-only selected snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '0017_companion'
down_revision = '0016_share_invitations'
branch_labels = depends_on = None


def common():
    return [sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
        sa.Column('author_actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('idempotency_key',sa.String(200),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('revision',sa.Integer,nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('last_action',sa.JSON),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False)]


def upgrade():
    op.create_table('contribution_grants',
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),primary_key=True),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),primary_key=True),
        sa.Column('author_actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('enabled',sa.Boolean,nullable=False),sa.Column('revision',sa.Integer,nullable=False),
        sa.Column('last_action',sa.JSON),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('companion_contributions',*common(),
        sa.Column('classification',sa.String(16),nullable=False),sa.Column('text',sa.Text,nullable=False),
        sa.Column('recipient_actor_ids',sa.JSON,nullable=False),
        sa.UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_contributions_idempotency'),
        sa.CheckConstraint("classification IN ('firsthand','reported','opinion')",name='ck_contributions_classification'),
        sa.CheckConstraint("status IN ('pending','accepted','rejected','disagreement','withdrawn')",name='ck_contributions_status'))
    op.create_table('companion_letters',*common(),
        sa.Column('recipient_actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('title',sa.String(120),nullable=False),sa.Column('text',sa.Text,nullable=False),
        sa.UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_letters_idempotency'),
        sa.CheckConstraint("status IN ('draft','published','revoked')",name='ck_letters_status'))
    op.create_table('sealed_snapshots',*common(),
        sa.Column('recipient_actor_ids',sa.JSON,nullable=False),sa.Column('source_version',sa.String(64),nullable=False),
        sa.Column('items',sa.JSON,nullable=False),
        sa.UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_snapshots_idempotency'),
        sa.CheckConstraint("status IN ('sealed','revoked')",name='ck_snapshots_status'))
    for table in ('companion_contributions','companion_letters','sealed_snapshots'):
        op.create_index('ix_'+table+'_subject_id',table,['subject_id'])


def downgrade():
    for table in ('sealed_snapshots','companion_letters','companion_contributions','contribution_grants'):
        op.drop_table(table)

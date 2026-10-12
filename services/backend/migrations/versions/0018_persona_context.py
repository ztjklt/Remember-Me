"""Additive dialogue provenance, dedicated audio and explicit contribution model use."""
from alembic import op
import sqlalchemy as sa
revision='0018_persona_context'
down_revision='0017_companion'
branch_labels=depends_on=None


def upgrade():
    op.create_table('persona_answer_contexts',
        sa.Column('answer_id',sa.String(64),sa.ForeignKey('twin_answers.answer_id'),primary_key=True),
        sa.Column('mode',sa.String(16),nullable=False),sa.Column('cloud_consent_id',sa.String(64),nullable=False),
        sa.Column('understanding_ids',sa.JSON,nullable=False),sa.Column('contribution_ids',sa.JSON,nullable=False),
        sa.Column('prompt_version',sa.String(128),nullable=False))
    op.create_table('companion_audio',
        sa.Column('audio_id',sa.String(64),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
        sa.Column('author_actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('idempotency_key',sa.String(200),nullable=False),sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('purpose',sa.String(16),nullable=False),sa.Column('object_key',sa.String(500),nullable=False),
        sa.Column('content_type',sa.String(100),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('revision',sa.Integer,nullable=False),sa.Column('transcript_text',sa.Text,nullable=False),
        sa.Column('reviewed_text',sa.Text,nullable=False),sa.Column('model_version',sa.String(128),nullable=False),
        sa.Column('error',sa.String(200),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_companion_audio_request'))
    op.create_index('ix_companion_audio_subject_id','companion_audio',['subject_id'])
    for table in ('companion_contributions','companion_letters'):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('audio_id',sa.String(64),nullable=True))
    with op.batch_alter_table('companion_contributions') as batch:
        batch.add_column(sa.Column('narrative_ids',sa.JSON,nullable=False,server_default='[]'))
        batch.add_column(sa.Column('model_use_author_allowed',sa.Boolean,nullable=False,server_default=sa.false()))
        batch.add_column(sa.Column('model_use_owner_allowed',sa.Boolean,nullable=False,server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('companion_contributions') as batch:
        for name in ('model_use_owner_allowed','model_use_author_allowed','narrative_ids'): batch.drop_column(name)
    for table in ('companion_letters','companion_contributions'):
        with op.batch_alter_table(table) as batch: batch.drop_column('audio_id')
    op.drop_table('companion_audio');op.drop_table('persona_answer_contexts')

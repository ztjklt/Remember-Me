"""Session speaker separation and spoken identity introductions."""
from alembic import op
import sqlalchemy as sa
revision='0022_speaker_recordings'
down_revision='0021_personal_learning'
branch_labels=depends_on=None

def upgrade():
    with op.batch_alter_table('consents') as b:
        b.drop_constraint('ck_consents_scope', type_='check')
        b.create_check_constraint('ck_consents_scope', "scope IN ('RECORDING','VOICE','CLOUD_TWIN','MODEL_TRAINING','SPEAKER_IDENTIFICATION')")
    op.create_table('speaker_recordings',
        sa.Column('recording_id',sa.String(64),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('consent_id',sa.String(64),sa.ForeignKey('consents.consent_id'),nullable=False),
        sa.Column('policy',sa.String(128),nullable=False),sa.Column('idempotency_key',sa.String(128),nullable=False),
        sa.Column('audio_key',sa.String(256),nullable=False),sa.Column('checksum',sa.String(64),nullable=False),
        sa.Column('content_type',sa.String(64),nullable=False),sa.Column('speaker_count',sa.Integer,nullable=True),sa.Column('duration_ms',sa.Integer,nullable=False),
        sa.Column('recorded_at',sa.DateTime(timezone=True),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('status',sa.String(24),nullable=False),sa.Column('attempts',sa.Integer,nullable=False),
        sa.Column('lease_token',sa.String(64),nullable=True),sa.Column('lease_expires_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('report',sa.JSON,nullable=True),sa.Column('error',sa.Text,nullable=True),
        sa.UniqueConstraint('subject_id','actor_id','idempotency_key',name='uq_speaker_recording_request'))
    op.create_index('ix_speaker_recording_owner','speaker_recordings',['subject_id','actor_id','created_at'])

def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM speaker_recordings")).scalar():
        raise RuntimeError('Export/delete group recordings before downgrading')
    if op.get_bind().execute(sa.text("SELECT count(*) FROM consents WHERE scope='SPEAKER_IDENTIFICATION'")).scalar():
        raise RuntimeError('Preserve speaker consent audit before downgrading')
    op.drop_table('speaker_recordings')
    with op.batch_alter_table('consents') as b:
        b.drop_constraint('ck_consents_scope',type_='check')
        b.create_check_constraint('ck_consents_scope',"scope IN ('RECORDING','VOICE','CLOUD_TWIN','MODEL_TRAINING')")

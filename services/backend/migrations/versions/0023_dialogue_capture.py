"""Reuse ordinary owner dialogue, with independent recording/identification grants."""
from alembic import op
import sqlalchemy as sa
revision='0023_dialogue_capture'
down_revision='0022_speaker_recordings'
branch_labels=depends_on=None
def upgrade():
    with op.batch_alter_table('voice_calls') as b:
        b.add_column(sa.Column('recording_consent_id',sa.String(64),sa.ForeignKey('consents.consent_id',name='fk_voice_calls_recording_capture'),nullable=True))
        b.add_column(sa.Column('speaker_consent_id',sa.String(64),sa.ForeignKey('consents.consent_id',name='fk_voice_calls_speaker_capture'),nullable=True))
    op.create_table('dialogue_samples',sa.Column('sample_id',sa.String(64),primary_key=True),
        sa.Column('call_id',sa.String(64),sa.ForeignKey('voice_calls.call_id'),nullable=False),sa.Column('turn_id',sa.String(64),nullable=False),
        sa.Column('audio_key',sa.String(256),nullable=False),sa.Column('checksum',sa.String(64),nullable=False),
        sa.Column('duration_ms',sa.Integer,nullable=False),sa.Column('status',sa.String(24),nullable=False),sa.Column('attempts',sa.Integer,nullable=False),
        sa.Column('lease_token',sa.String(64),nullable=True),sa.Column('lease_expires_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('error',sa.Text,nullable=True),sa.Column('profile_id',sa.String(64),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('call_id','turn_id',name='uq_dialogue_sample_turn'))
    op.create_index('ix_dialogue_samples_call_id','dialogue_samples',['call_id'])
def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM dialogue_samples')).scalar():raise RuntimeError('Preserve dialogue sample audit before downgrade')
    op.drop_table('dialogue_samples')
    with op.batch_alter_table('voice_calls') as b:
        b.drop_column('recording_consent_id');b.drop_column('speaker_consent_id')

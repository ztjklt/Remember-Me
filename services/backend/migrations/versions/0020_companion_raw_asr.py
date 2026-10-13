"""Preserve original ASR independently of simplified display and reviewed text."""
from alembic import op
import sqlalchemy as sa

revision='0020_companion_raw_asr'
down_revision='0019_synthetic_voice'
branch_labels=depends_on=None


def upgrade():
    with op.batch_alter_table('companion_audio') as batch:
        # Existing normalized transcripts cannot stand in for an unknown raw
        # provider result. Empty explicitly records that original is unavailable.
        batch.add_column(sa.Column('raw_transcript_text',sa.Text(),nullable=False,server_default=''))


def downgrade():
    with op.batch_alter_table('companion_audio') as batch:
        batch.drop_column('raw_transcript_text')

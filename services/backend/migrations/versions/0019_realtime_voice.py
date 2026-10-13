"""Separately consented realtime Voice profiles and call audits.

Revision ID: 0019_realtime_voice
Revises: 0018_twin_conversations
"""
from alembic import op
import sqlalchemy as sa
revision = '0019_realtime_voice'
down_revision = '0018_twin_conversations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('realtime_voice_profiles',
        sa.Column('profile_id', sa.String(64), primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False),
        sa.Column('actor_id', sa.String(64), sa.ForeignKey('actors.actor_id'), nullable=False),
        sa.Column('consent_id', sa.String(64), sa.ForeignKey('consents.consent_id'), nullable=False),
        sa.Column('sample_key', sa.String(1024), nullable=False),
        sa.Column('accepted_policy', sa.String(128), nullable=False),
        sa.Column('reference_text', sa.Text(), nullable=False),
        sa.Column('provider_voice_id', sa.String(256), nullable=False),
        sa.Column('model', sa.String(128), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('fetch_digest', sa.String(64), nullable=False),
        sa.Column('fetch_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)))
    op.create_table('voice_calls',
        sa.Column('call_id', sa.String(64), primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False),
        sa.Column('actor_id', sa.String(64), sa.ForeignKey('actors.actor_id'), nullable=False),
        sa.Column('profile_id', sa.String(64), sa.ForeignKey('realtime_voice_profiles.profile_id'), nullable=False),
        sa.Column('cloud_consent_id', sa.String(64), sa.ForeignKey('consents.consent_id'), nullable=False),
        sa.Column('voice_consent_id', sa.String(64), sa.ForeignKey('consents.consent_id'), nullable=False),
        sa.Column('credential_digest', sa.String(64), nullable=False),
        sa.Column('policy', sa.String(128), nullable=False),
        sa.Column('previous_answer_id', sa.String(64), nullable=False),
        sa.Column('active_turn', sa.String(64), nullable=False),
        sa.Column('active_answer_id', sa.String(64), nullable=False),
        sa.Column('room', sa.String(128), nullable=False, unique=True),
        sa.Column('participant', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table('voice_calls')
    op.drop_table('realtime_voice_profiles')

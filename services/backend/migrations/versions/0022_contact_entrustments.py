"""Scoped account-free contact receipts; preserves existing letters and grants."""
from alembic import op
import sqlalchemy as sa
revision = '0022_contact_entrustments'
down_revision = '0021_twin_review_summary'
branch_labels = depends_on = None


def upgrade():
    op.create_table('contact_entrustments',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), nullable=False, primary_key=False),
        sa.Column('author_actor_id', sa.String(64), sa.ForeignKey('actors.actor_id'), nullable=False, primary_key=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False, primary_key=False),
        sa.Column('request_hash', sa.String(64), nullable=False, primary_key=False),
        sa.Column('recipient_label', sa.String(80), nullable=False, primary_key=False),
        sa.Column('channel', sa.String(12), nullable=False, primary_key=False),
        sa.Column('contact_cipher', sa.Text(), nullable=False, primary_key=False),
        sa.Column('contact_hash', sa.String(64), nullable=False, primary_key=False),
        sa.Column('contact_mask', sa.String(254), nullable=False, primary_key=False),
        sa.Column('invite_cipher', sa.Text(), nullable=False, primary_key=False),
        sa.Column('invite_hash', sa.String(64), nullable=False, primary_key=False),
        sa.Column('title', sa.String(120), nullable=False, primary_key=False),
        sa.Column('message', sa.Text(), nullable=False, primary_key=False),
        sa.Column('sources', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('source_version', sa.String(64), nullable=False, primary_key=False),
        sa.Column('status', sa.String(16), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('notice_status', sa.String(16), nullable=False, primary_key=False),
        sa.Column('notice_attempt', sa.String(64), nullable=False, primary_key=False),
        sa.Column('notice_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('subject_id', 'author_actor_id', 'idempotency_key', name='uq_contact_entrustment_request'),
        sa.UniqueConstraint('invite_hash'),
    )
    op.create_index('ix_contact_entrustments_subject_id', 'contact_entrustments', ['subject_id'], unique=False)
    op.create_index('ix_contact_entrustments_contact_hash', 'contact_entrustments', ['contact_hash'], unique=False)
    op.create_table('receipt_challenges',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.String(64), sa.ForeignKey('contact_entrustments.id'), nullable=False, primary_key=False),
        sa.Column('code_hash', sa.String(64), nullable=False, primary_key=False),
        sa.Column('attempts', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(16), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index('ix_receipt_challenges_plan_id', 'receipt_challenges', ['plan_id'], unique=False)
    op.create_table('receipt_sessions',
        sa.Column('token_hash', sa.String(64), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.String(64), sa.ForeignKey('contact_entrustments.id'), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index('ix_receipt_sessions_plan_id', 'receipt_sessions', ['plan_id'], unique=False)
    op.create_table('receipt_rates',
        sa.Column('key', sa.String(64), nullable=False, primary_key=True),
        sa.Column('hits', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('reset_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )


def downgrade():
    op.drop_table('receipt_rates')
    op.drop_table('receipt_sessions')
    op.drop_table('receipt_challenges')
    op.drop_table('contact_entrustments')

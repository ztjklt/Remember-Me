"""Owner conversation chains and explicitly confirmed written chat capture."""
from alembic import op
import sqlalchemy as sa

revision = '0018_twin_conversations'
down_revision = '0017_evidence_chunks'
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table('twin_answers') as batch:
        batch.add_column(sa.Column('conversation_id', sa.String(64), nullable=True))
        batch.add_column(sa.Column('parent_answer_id', sa.String(64), nullable=True))
        batch.add_column(sa.Column('request_id', sa.String(64), nullable=True))
        batch.add_column(sa.Column('context_answer_ids', sa.JSON, nullable=True))
        batch.add_column(sa.Column('context_truncated', sa.Boolean, nullable=False, server_default=sa.false()))
        batch.drop_constraint('ck_twin_answers_response_type', type_='check')
        batch.create_check_constraint('ck_twin_answers_response_type', "response_type IN ('ORIGINAL','SIMULATION','UNKNOWN','CONVERSATION')")
        batch.create_index('ix_twin_answers_request', ['subject_id','actor_id','request_id'], unique=True)
    with op.batch_alter_table('episodes') as batch:
        batch.drop_constraint('ck_episodes_source', type_='check')
        batch.create_check_constraint('ck_episodes_source', "source IN ('ANDROID_MIC','IOS_MIC','IOS_TEXT','WORK_3200','RECORDING_DEVICE','IMPORT')")
        for name, size in [('audio_ref',1024), ('audio_object_key',1024), ('audio_checksum',64)]:
            batch.alter_column(name, existing_type=sa.String(size), nullable=True)


def downgrade():
    # There is no truthful downgrade of persisted text Episodes or chat replies.
    # Fail rather than delete data or relabel conversations as personality.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM episodes WHERE source='IOS_TEXT'")) or connection.scalar(sa.text("SELECT count(*) FROM twin_answers WHERE conversation_id IS NOT NULL")):
        raise RuntimeError('Conversation/text data must be preserved; downgrade refused')
    with op.batch_alter_table('episodes') as batch:
        batch.drop_constraint('ck_episodes_source', type_='check')
        batch.create_check_constraint('ck_episodes_source', "source IN ('ANDROID_MIC','IOS_MIC','WORK_3200','RECORDING_DEVICE','IMPORT')")
        for name, size in [('audio_ref',1024), ('audio_object_key',1024), ('audio_checksum',64)]:
            batch.alter_column(name, existing_type=sa.String(size), nullable=False)
    with op.batch_alter_table('twin_answers') as batch:
        batch.drop_index('ix_twin_answers_request')
        batch.drop_constraint('ck_twin_answers_response_type', type_='check')
        batch.create_check_constraint('ck_twin_answers_response_type', "response_type IN ('ORIGINAL','SIMULATION','UNKNOWN')")
        for name in ['conversation_id','parent_answer_id','request_id','context_answer_ids','context_truncated']:
            batch.drop_column(name)

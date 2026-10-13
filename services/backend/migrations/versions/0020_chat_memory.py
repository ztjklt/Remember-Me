"""Private historical chat indexes and source-linked summaries; preserve Voice."""
from alembic import op
import sqlalchemy as sa
revision = '0020_chat_memory'
down_revision = '0019_realtime_voice'
branch_labels = depends_on = None

def upgrade():
    op.add_column('twin_answers', sa.Column('recalled_answer_ids', sa.JSON, nullable=True))
    op.add_column('twin_answers', sa.Column('history_summary_status', sa.String(24), nullable=True))
    op.create_table('chat_memory_state',
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),primary_key=True),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),primary_key=True),
        sa.Column('enabled',sa.Boolean,nullable=False),
        sa.Column('forgotten_before',sa.DateTime(timezone=True),nullable=True),
        sa.Column('revision',sa.Integer,nullable=False))
    op.create_table('chat_turn_embeddings',
        sa.Column('answer_id',sa.String(64),sa.ForeignKey('twin_answers.answer_id',ondelete='CASCADE'),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('content_hash',sa.String(64),nullable=False),
        sa.Column('model_version',sa.String(128),nullable=False),sa.Column('vector',sa.JSON,nullable=False))
    op.create_index('ix_chat_turn_embeddings_subject_id','chat_turn_embeddings',['subject_id'])
    op.create_table('chat_digests',
        sa.Column('digest_id',sa.String(64),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('source_hash',sa.String(64),nullable=False),sa.Column('source_answer_ids',sa.JSON,nullable=False),
        sa.Column('summary',sa.Text,nullable=False),sa.Column('model_version',sa.String(128),nullable=False),
        sa.Column('prompt_version',sa.String(128),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_chat_digest_source','chat_digests',['subject_id','actor_id','source_hash'],unique=True)

def downgrade():
    op.drop_table('chat_digests');op.drop_table('chat_turn_embeddings');op.drop_table('chat_memory_state')
    op.drop_column('twin_answers','history_summary_status');op.drop_column('twin_answers','recalled_answer_ids')

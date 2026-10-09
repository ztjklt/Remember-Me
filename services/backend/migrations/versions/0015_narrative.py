"""Evidence-backed story organization; all original data is retained."""
from alembic import op
import sqlalchemy as sa
revision = '0015_narrative'
down_revision = '0014_profile_relations'
branch_labels = depends_on = None

def upgrade():
    op.add_column('twin_answers',sa.Column('expression',sa.JSON,nullable=True))
    op.add_column('profile_refreshes',sa.Column('request_payload',sa.JSON,nullable=True))
    op.create_table('narrative_records',
        sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False,index=True),
        sa.Column('kind',sa.String(20),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('payload',sa.JSON,nullable=False),sa.Column('evidence_snapshot',sa.JSON,nullable=False),
        sa.Column('revision',sa.Integer,nullable=False),sa.Column('model_version',sa.String(128),nullable=False),
        sa.Column('prompt_version',sa.String(128),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('narrative_history',sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('record_id',sa.String(64),sa.ForeignKey('narrative_records.id'),nullable=False,index=True),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('revision',sa.Integer,nullable=False),sa.Column('action',sa.String(20),nullable=False),
        sa.Column('payload',sa.JSON,nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('narrative_preferences',sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),primary_key=True),
        sa.Column('style_enabled',sa.Boolean,nullable=False),sa.Column('revision',sa.Integer,nullable=False))
    op.create_table('narrative_question_decisions',sa.Column('id',sa.String(192),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
        sa.Column('state',sa.String(16),nullable=False),sa.Column('until',sa.DateTime(timezone=True)))

def downgrade():
    op.drop_column('twin_answers','expression')
    op.drop_column('profile_refreshes','request_payload')
    for name in ('narrative_question_decisions','narrative_preferences','narrative_history','narrative_records'):
        op.drop_table(name)

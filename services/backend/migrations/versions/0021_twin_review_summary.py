"""Separate answer coverage from source validity without storing reviewer prose."""
from alembic import op
import sqlalchemy as sa

revision='0021_twin_review_summary'
down_revision='0020_companion_raw_asr'
branch_labels=depends_on=None


def upgrade():
    with op.batch_alter_table('persona_answer_contexts') as batch:
        # No historical answer is retrospectively declared complete.
        batch.add_column(sa.Column('review_summary',sa.JSON(),nullable=False,server_default='{}'))


def downgrade():
    with op.batch_alter_table('persona_answer_contexts') as batch:
        batch.drop_column('review_summary')

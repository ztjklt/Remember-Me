"""Persist actual source/permission basis used for an answer."""
from alembic import op
import sqlalchemy as sa
revision='0010_answer_source_version'
down_revision='0009_profile_candidates'
branch_labels=depends_on=None

def upgrade():
    op.add_column('twin_answers',sa.Column('source_basis',sa.String(64),nullable=True))

def downgrade():
    op.drop_column('twin_answers','source_basis')

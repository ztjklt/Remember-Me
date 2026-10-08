"""Private reusable language notes; never automatically treated as memory."""
from alembic import op
import sqlalchemy as sa

revision = '0012_subject_vocabulary'
down_revision = '0011_profile_updates'
branch_labels = depends_on = None


def upgrade():
    op.create_table('subject_vocabulary',
        sa.Column('subject_id', sa.String(64), sa.ForeignKey('subjects.subject_id'), primary_key=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('subject_vocabulary')

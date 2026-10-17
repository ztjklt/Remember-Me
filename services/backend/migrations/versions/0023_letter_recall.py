"""Explicit owner opt-in for evidence-linked private letter entry points."""
from alembic import op
import sqlalchemy as sa
revision = '0023_letter_recall'
down_revision = '0022_contact_entrustments'
branch_labels = depends_on = None


def upgrade():
    op.create_table('letter_recall_cues',
        sa.Column('letter_id',sa.String(64),sa.ForeignKey('companion_letters.id'),primary_key=True),
        sa.Column('letter_revision',sa.Integer(),nullable=False),
        sa.Column('source_version',sa.String(64),nullable=False),
        sa.Column('evidence_ids',sa.JSON(),nullable=False))


def downgrade():
    op.drop_table('letter_recall_cues')

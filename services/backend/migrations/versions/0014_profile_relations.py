"""Optional model suggestions reuse pending owner-reviewed profile updates."""
from alembic import op
import sqlalchemy as sa
revision='0014_profile_relations'
down_revision='0013_account_entry'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('profile_refreshes',sa.Column('kind',sa.String(16),nullable=False,server_default='candidates'))
    op.add_column('profile_updates',sa.Column('origin',sa.String(16),nullable=False,server_default='owner'))
    op.add_column('profile_updates',sa.Column('model_version',sa.String(128),nullable=True))
    op.add_column('profile_updates',sa.Column('prompt_version',sa.String(128),nullable=True))
    op.add_column('profile_updates',sa.Column('suggestion_evidence_ids',sa.JSON,nullable=True))

def downgrade():
    for column in ('suggestion_evidence_ids','prompt_version','model_version','origin'):
        op.drop_column('profile_updates',column)
    op.drop_column('profile_refreshes','kind')

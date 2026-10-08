"""Password accounts and expiring device sessions; existing tokens unchanged."""
from alembic import op
import sqlalchemy as sa
revision='0013_account_entry'
down_revision='0012_subject_vocabulary'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('device_credentials',sa.Column('expires_at',sa.DateTime(timezone=True),nullable=True))
    op.create_table('accounts',sa.Column('username',sa.String(64),primary_key=True),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False,unique=True),
        sa.Column('salt',sa.String(64),nullable=False),sa.Column('password_hash',sa.String(64),nullable=False))
    op.create_table('account_attempts',sa.Column('attempt_id',sa.String(64),primary_key=True),
        sa.Column('name_hash',sa.String(64),nullable=False),sa.Column('ip_hash',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_account_attempts_name_hash','account_attempts',['name_hash'])
    op.create_index('ix_account_attempts_ip_hash','account_attempts',['ip_hash'])

def downgrade():
    op.drop_table('account_attempts');op.drop_table('accounts')
    op.drop_column('device_credentials','expires_at')

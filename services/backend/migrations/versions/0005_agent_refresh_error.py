"""Isolate experimental refresh failures from the Episode lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = "0005_agent_refresh_error"
down_revision = "0004_agent_loop"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_states", sa.Column("refresh_error", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("agent_states", "refresh_error")

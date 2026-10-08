"""Private capture-policy diagnostics; public question shapes stay unchanged."""
from alembic import op
import sqlalchemy as sa

revision = "0008_capture_policy"
down_revision = "0007_calibration"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("capture_questions", sa.Column("policy_snapshot", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("capture_questions", "policy_snapshot")

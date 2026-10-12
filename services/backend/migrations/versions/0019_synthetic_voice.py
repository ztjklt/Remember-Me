"""Server-owned synthetic references and separately granted recipient voice."""
from alembic import op
import sqlalchemy as sa

revision = '0019_synthetic_voice'
down_revision = '0018_persona_context'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('synthetic_voice_profiles',
        sa.Column('profile_id',sa.String(64),sa.ForeignKey('voice_profiles.profile_id'),primary_key=True),
        sa.Column('preset',sa.String(32),nullable=False),
        sa.Column('provider',sa.String(32),nullable=False),
        sa.Column('reference_sha256',sa.String(64),nullable=False))
    op.create_table('voice_recipient_grants',
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),primary_key=True),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),primary_key=True),
        sa.Column('granted_by_actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    op.drop_table('voice_recipient_grants')
    op.drop_table('synthetic_voice_profiles')

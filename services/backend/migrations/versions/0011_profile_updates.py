"""Owner-confirmed profile updates and evidence fingerprints; preserve history."""
from alembic import op
import sqlalchemy as sa
revision='0011_profile_updates'
down_revision='0010_answer_source_version'
branch_labels=depends_on=None


def upgrade():
    op.add_column('profile_candidates',sa.Column('evidence_snapshot',sa.JSON(),nullable=True))
    op.create_table('profile_updates',
        sa.Column('update_id',sa.String(64),primary_key=True),
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False),
        sa.Column('candidate_id',sa.String(64),sa.ForeignKey('profile_candidates.candidate_id'),nullable=False),
        sa.Column('target_candidate_id',sa.String(64),sa.ForeignKey('profile_candidates.candidate_id'),nullable=True),
        sa.Column('result_candidate_id',sa.String(64),sa.ForeignKey('profile_candidates.candidate_id'),nullable=True),
        sa.Column('action',sa.String(16),nullable=False),
        sa.Column('reason',sa.Text(),nullable=False),
        sa.Column('time_text',sa.Text(),nullable=False),
        sa.Column('base_source_version',sa.String(64),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('decided_at',sa.DateTime(timezone=True),nullable=True))


def downgrade():
    op.drop_table('profile_updates')
    op.drop_column('profile_candidates','evidence_snapshot')

"""Separately consented training candidates and sealed human verification."""
from alembic import op
import sqlalchemy as sa
revision='0021_personal_learning'
down_revision='0020_chat_memory'
branch_labels=depends_on=None

def owner_columns():
    return [sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),nullable=False),
            sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),nullable=False)]

def upgrade():
    with op.batch_alter_table('consents') as b:
        b.drop_constraint('ck_consents_scope',type_='check')
        b.create_check_constraint('ck_consents_scope',"scope IN ('RECORDING','VOICE','CLOUD_TWIN','MODEL_TRAINING')")
    op.create_table('learning_preferences',
        sa.Column('subject_id',sa.String(64),sa.ForeignKey('subjects.subject_id'),primary_key=True),
        sa.Column('actor_id',sa.String(64),sa.ForeignKey('actors.actor_id'),primary_key=True),
        sa.Column('enabled',sa.Boolean,nullable=False),
        sa.Column('consent_id',sa.String(64),sa.ForeignKey('consents.consent_id'),nullable=True),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('personal_training_jobs',sa.Column('job_id',sa.String(64),primary_key=True),*owner_columns(),
        sa.Column('consent_id',sa.String(64),sa.ForeignKey('consents.consent_id'),nullable=False),
        sa.Column('source_basis',sa.String(64),nullable=False),sa.Column('person_model_version',sa.Integer,nullable=False),
        sa.Column('dataset_sha256',sa.String(64),nullable=False),sa.Column('base_model',sa.String(128),nullable=False),
        sa.Column('status',sa.String(32),nullable=False),sa.Column('counts',sa.JSON,nullable=False),
        sa.Column('result',sa.JSON,nullable=True),sa.Column('worker_id',sa.String(64),nullable=True),
        sa.Column('lease_token_hash',sa.String(64),nullable=True),sa.Column('lease_expires_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_personal_training_owner','personal_training_jobs',['subject_id','actor_id','created_at'])
    op.create_table('personal_trainer_heartbeats',sa.Column('worker_id',sa.String(64),primary_key=True),
        sa.Column('base_model',sa.String(128),nullable=False),sa.Column('available',sa.Boolean,nullable=False),
        sa.Column('seen_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('fidelity_cases',sa.Column('case_id',sa.String(64),primary_key=True),*owner_columns(),
        sa.Column('question',sa.Text,nullable=False),sa.Column('question_group_id',sa.String(64),nullable=False),
        sa.Column('locked_answer',sa.Text,nullable=False),sa.Column('answer_id',sa.String(64),nullable=False),
        sa.Column('response_type',sa.String(16),nullable=False),sa.Column('model_version',sa.String(128),nullable=False),
        sa.Column('person_model_version',sa.Integer,nullable=False),sa.Column('source_basis',sa.String(64),nullable=False),
        sa.Column('exposure_manifest',sa.JSON,nullable=False),sa.Column('human_answer',sa.Text,nullable=True),
        sa.Column('ratings',sa.JSON,nullable=True),sa.Column('human_confirmed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('rated_at',sa.DateTime(timezone=True),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_fidelity_owner','fidelity_cases',['subject_id','actor_id','created_at'])

def downgrade():
    # A rollback must not silently erase an explicit training permission.
    if op.get_bind().execute(sa.text("SELECT count(*) FROM consents WHERE scope='MODEL_TRAINING'")).scalar():
        raise RuntimeError('Revoke/export training grants before schema downgrade')
    for table in ['fidelity_cases','personal_trainer_heartbeats','personal_training_jobs','learning_preferences']:op.drop_table(table)
    with op.batch_alter_table('consents') as b:
        b.drop_constraint('ck_consents_scope',type_='check')
        b.create_check_constraint('ck_consents_scope',"scope IN ('RECORDING','VOICE','CLOUD_TWIN')")

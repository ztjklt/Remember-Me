"""Private voice references, per-turn provenance and scoped entrustment."""
from alembic import op
import sqlalchemy as sa
revision='0024_voiceprint_entrust'
down_revision='0023_dialogue_capture'
branch_labels=depends_on=None

def col(name,kind,nullable=False,primary=False):return sa.Column(name,kind,nullable=nullable,primary_key=primary)
def ref(name,target,nullable=False):return sa.Column(name,sa.String(64),sa.ForeignKey(target),nullable=nullable)
def stamp(name,nullable=False):return col(name,sa.DateTime(timezone=True),nullable)
def upgrade():
    with op.batch_alter_table('consents') as b:
        b.drop_constraint('ck_consents_scope',type_='check')
        b.create_check_constraint('ck_consents_scope',"scope IN ('RECORDING','VOICE','CLOUD_TWIN','MODEL_TRAINING','SPEAKER_IDENTIFICATION','DIGITAL_HANDOVER')")
    with op.batch_alter_table('voice_calls') as b:
        b.add_column(sa.Column('enroll_owner_voice',sa.Boolean,nullable=False,server_default=sa.false()))
        b.add_column(sa.Column('completed_turn_id',sa.String(64),nullable=False,server_default=''))
    with op.batch_alter_table('twin_answers') as b:
        b.add_column(sa.Column('voice_call_id',sa.String(64),nullable=True))
        b.add_column(sa.Column('voice_turn_id',sa.String(64),nullable=True))
    op.create_table('voice_identities',col('identity_id',sa.String(64),primary=True),ref('subject_id','subjects.subject_id'),ref('actor_id','actors.actor_id'),col('person_key',sa.String(128)),col('label',sa.String(80)),col('role',sa.String(24)),ref('consent_id','consents.consent_id'),col('encoder_version',sa.String(128)),col('vectors',sa.JSON),col('sources',sa.JSON),stamp('revoked_at',True),stamp('created_at'),sa.UniqueConstraint('subject_id','person_key',name='uq_voice_identity_person'))
    op.create_index('ix_voice_identities_subject_id','voice_identities',['subject_id'])
    op.create_table('voice_utterances',col('utterance_id',sa.String(64),primary=True),ref('call_id','voice_calls.call_id'),col('turn_id',sa.String(64)),col('audio_key',sa.String(256)),col('checksum',sa.String(64)),col('status',sa.String(24)),col('report',sa.JSON,True),col('lease_token',sa.String(64),True),stamp('lease_expires_at',True),stamp('created_at'),sa.UniqueConstraint('call_id','turn_id',name='uq_voice_utterance_turn'))
    op.create_index('ix_voice_utterances_call_id','voice_utterances',['call_id'])
    op.create_table('legacy_states',ref('subject_id','subjects.subject_id'),ref('steward_actor_id','actors.actor_id'),col('status',sa.String(32)),col('verification_history',sa.JSON),col('verification_ref',sa.String(256)),col('baseline',sa.JSON),stamp('updated_at'),sa.PrimaryKeyConstraint('subject_id'))
    op.create_table('entrustments',col('plan_id',sa.String(64),primary=True),ref('subject_id','subjects.subject_id'),ref('owner_actor_id','actors.actor_id'),ref('recipient_actor_id','actors.actor_id'),col('recipient_label',sa.String(80)),ref('consent_id','consents.consent_id'),col('episode_ids',sa.JSON),ref('voice_consent_id','consents.consent_id',True),col('secret_hash',sa.String(256)),col('condition',sa.String(32)),col('status',sa.String(24)),col('revision',sa.Integer),col('failures',sa.Integer),stamp('blocked_until',True),stamp('created_at'))
    op.create_index('ix_entrustments_subject_id','entrustments',['subject_id']);op.create_index('ix_entrustments_recipient_actor_id','entrustments',['recipient_actor_id'])
    op.create_table('entrust_unlocks',col('unlock_id',sa.String(64),primary=True),ref('plan_id','entrustments.plan_id'),ref('actor_id','actors.actor_id'),col('token_hash',sa.String(64)),col('visit_id',sa.String(64),True),col('plan_revision',sa.Integer),col('source_basis',sa.String(64)),stamp('expires_at'),stamp('revoked_at',True),col('answer_ids',sa.JSON))
    op.create_index('ix_entrust_unlocks_plan_id','entrust_unlocks',['plan_id'])
    op.create_table('entrust_visits',col('visit_id',sa.String(64),primary=True),ref('plan_id','entrustments.plan_id'),ref('actor_id','actors.actor_id'),col('consent_ids',sa.JSON),stamp('expires_at'),stamp('revoked_at',True))
    op.create_index('ix_entrust_visits_plan_id','entrust_visits',['plan_id'])

def downgrade():
    bind=op.get_bind();tables=('entrust_visits','entrust_unlocks','entrustments','legacy_states','voice_utterances','voice_identities')
    for table in tables:
        if bind.execute(sa.text('SELECT count(*) FROM '+table)).scalar():raise RuntimeError('Preserve voice identity, entrustment and activation audit before any downgrade')
    if bind.execute(sa.text("SELECT count(*) FROM consents WHERE scope='DIGITAL_HANDOVER'")).scalar():raise RuntimeError('Preserve handover grants before downgrade')
    for table in tables:op.drop_table(table)
    with op.batch_alter_table('twin_answers') as b:
        b.drop_column('voice_call_id');b.drop_column('voice_turn_id')
    with op.batch_alter_table('voice_calls') as b:
        b.drop_column('enroll_owner_voice');b.drop_column('completed_turn_id')
    with op.batch_alter_table('consents') as b:
        b.drop_constraint('ck_consents_scope',type_='check')
        b.create_check_constraint('ck_consents_scope',"scope IN ('RECORDING','VOICE','CLOUD_TWIN','MODEL_TRAINING','SPEAKER_IDENTIFICATION')")

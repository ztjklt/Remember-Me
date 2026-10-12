import sqlalchemy as sa
from alembic import command
from conftest import alembic_config, upgrade_to_head

from app.models import Base

EXPECTED_TABLES = {
    "alembic_version",
    "subjects",
    "actors",
    "consents",
    "episodes",
    "jobs",
    "evidence",
    "memory_items",
    "person_traits", "graph_facts", "capture_questions", "model_revisions",
    "memory_audit", "pairing_codes", "device_credentials",
    "memory_embeddings", "twin_answers", "voice_profiles", "voice_assets", "calibration_runs",
    "story_grants", "memory_revisions", "question_requests",
    "profile_candidates", "profile_refreshes", "profile_updates",
    "subject_vocabulary", "accounts", "account_attempts", "share_invitations",
    "narrative_records", "narrative_history", "narrative_preferences", "narrative_question_decisions",
    "contribution_grants", "companion_contributions", "companion_letters", "sealed_snapshots",
    "persona_answer_contexts", "companion_audio", "synthetic_voice_profiles", "voice_recipient_grants",
}


def table_names(database_url: str) -> set[str]:
    engine = sa.create_engine(database_url, future=True)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_review_summary_upgrade_preserves_old_answer_without_inventing_verdict(tmp_path):
    from sqlalchemy.orm import Session
    from app.seed import seed_development_data
    from app.models import TwinAnswer, utcnow
    url=f"sqlite:///{tmp_path / 'old-persona.db'}"
    config=alembic_config(url);command.upgrade(config,'0020_companion_raw_asr')
    engine=sa.create_engine(url,future=True)
    try:
        with Session(engine) as session:
            owner=seed_development_data(session,subject_name='旧人物',actor_name='旧账号')
            session.add(TwinAnswer(answer_id='old-answer',subject_id=owner.subject_id,actor_id=owner.actor_id,
                question='旧问题',answer='旧回答',response_type='UNKNOWN',evidence_ids=[],memory_item_ids=[],
                confidence=0,model_version='old-worker',person_model_version=0,source_basis='old-basis',created_at=utcnow()))
            session.commit()
        old=sa.Table('persona_answer_contexts',sa.MetaData(),autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(old.insert().values(answer_id='old-answer',mode='persona',cloud_consent_id='old-consent',
                understanding_ids=[],contribution_ids=[],prompt_version='old-prompt'))
        command.upgrade(config,'head')
        with engine.connect() as connection:
            row=connection.execute(sa.text('SELECT a.answer, c.review_summary FROM twin_answers a JOIN persona_answer_contexts c ON a.answer_id=c.answer_id')).mappings().one()
            import json
            assert row['answer']=='旧回答' and json.loads(row['review_summary'])=={}
    finally:
        engine.dispose()


def test_companion_raw_asr_column_preserves_old_rows_and_migration_roundtrip(tmp_path):
    from sqlalchemy.orm import Session
    from app.seed import seed_development_data
    from app.models import utcnow
    url=f"sqlite:///{tmp_path / 'companion-raw-asr.db'}"
    config=alembic_config(url)
    command.upgrade(config,'0019_synthetic_voice')
    engine=sa.create_engine(url,future=True)
    try:
        with Session(engine) as session:
            owner=seed_development_data(session,subject_name='旧录音人物',actor_name='旧录音作者')
        old=sa.Table('companion_audio',sa.MetaData(),autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(old.insert().values(audio_id='old-audio',subject_id=owner.subject_id,
                author_actor_id=owner.actor_id,idempotency_key='old-upload',request_hash='a'*64,
                purpose='letter',object_key='old/private/audio',content_type='audio/wav',status='confirmed',revision=3,
                transcript_text='旧展示稿',reviewed_text='旧核对稿',model_version='old-asr',error='',
                created_at=utcnow(),updated_at=utcnow()))
        command.upgrade(config,'head')
        columns={column['name']:column for column in sa.inspect(engine).get_columns('companion_audio')}
        assert 'raw_transcript_text' in columns
        assert columns['raw_transcript_text']['nullable'] is False
        assert columns['raw_transcript_text']['default'] is not None
        with engine.begin() as connection:
            row=connection.execute(sa.text('SELECT * FROM companion_audio')).mappings().one()
            # Old normalized text cannot be relabeled as an original ASR result.
            assert row['raw_transcript_text']==''
            assert row['transcript_text']=='旧展示稿' and row['reviewed_text']=='旧核对稿'
            connection.execute(sa.text("UPDATE companion_audio SET raw_transcript_text=:text"),{'text':'繁體原文'})
        command.downgrade(config,'0019_synthetic_voice')
        assert 'raw_transcript_text' not in {c['name'] for c in sa.inspect(engine).get_columns('companion_audio')}
        command.upgrade(config,'head')
        with engine.connect() as connection:
            row=connection.execute(sa.text('SELECT * FROM companion_audio')).mappings().one()
            assert row['audio_id']=='old-audio' and row['raw_transcript_text']==''
            assert row['transcript_text']=='旧展示稿' and row['reviewed_text']=='旧核对稿'
    finally:
        engine.dispose()


def test_migration_creates_the_foundation_tables_from_empty(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'empty.db'}"

    upgrade_to_head(database_url)

    assert table_names(database_url) == EXPECTED_TABLES


def test_upgrade_is_repeatable(database_url):
    # Already at head; applying head again must be a no-op rather than an error.
    upgrade_to_head(database_url)

    assert table_names(database_url) == EXPECTED_TABLES


def test_downgrade_removes_the_foundation_tables(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'rollback.db'}"
    upgrade_to_head(database_url)

    command.downgrade(alembic_config(database_url), "base")

    assert table_names(database_url) == {"alembic_version"}


def test_migrated_schema_matches_the_models(database_url):
    """Guard against model/migration drift, which would otherwise surface in Issue #1."""
    engine = sa.create_engine(database_url, future=True)
    try:
        inspector = sa.inspect(engine)
        migrated_tables = set(inspector.get_table_names()) - {"alembic_version"}

        assert migrated_tables == set(Base.metadata.tables)

        for table_name, table in Base.metadata.tables.items():
            columns = {
                column["name"]: column for column in inspector.get_columns(table_name)
            }
            assert set(columns) == {column.name for column in table.columns}, table_name

            for column in table.columns:
                assert columns[column.name]["nullable"] == column.nullable, (
                    f"{table_name}.{column.name} nullability differs between the "
                    "migration and the model"
                )

            migrated_indexes = {
                index["name"] for index in inspector.get_indexes(table_name)
            }
            assert {index.name for index in table.indexes} <= migrated_indexes, table_name

            migrated_checks = {
                check["name"] for check in inspector.get_check_constraints(table_name)
            }
            for constraint in table.constraints:
                if isinstance(constraint, sa.CheckConstraint):
                    # The database must refuse what the model refuses: the
                    # registered consent scopes are enforced in both places.
                    assert constraint.name in migrated_checks, (
                        f"{table_name} declares check constraint "
                        f"{constraint.name!r} that the migration does not create"
                    )
    finally:
        engine.dispose()

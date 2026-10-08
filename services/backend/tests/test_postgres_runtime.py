"""Real PostgreSQL transaction probes, enabled only on an isolated test DB."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select, text
from alembic import command
from fastapi.testclient import TestClient

from app.access import publication_lock, source_basis
from app.models import Subject
from app.seed import seed_development_data
from conftest import alembic_config, upgrade_to_head


def require_postgres(app):
    if app.state.database.engine.dialect.name != 'postgresql':
        pytest.skip('Set REMEMBER_TEST_POSTGRES_URL to run the real PostgreSQL probe')


def test_publication_blocks_ordinary_source_write_until_commit(app, session):
    require_postgres(app)
    seeded = seed_development_data(session, subject_name='原称呼', actor_name='记录者')
    publication_lock(session, seeded.subject_id)
    before = source_basis(session, seeded.subject_id)
    started, finished = Event(), Event()

    def ordinary_writer():
        with app.state.database.session() as writer:
            writer.execute(text("SET LOCAL lock_timeout = '5s'"))
            row = writer.get(Subject, seeded.subject_id)
            row.display_name = '经修改的称呼'
            started.set()
            writer.commit()
            finished.set()

    with ThreadPoolExecutor() as pool:
        future = pool.submit(ordinary_writer)
        assert started.wait(5)
        try:
            assert not finished.wait(0.5), 'Source write crossed the compare/publish transaction'
            assert source_basis(session, seeded.subject_id) == before
        finally:
            session.commit()
        future.result(timeout=10)
    publication_lock(session, seeded.subject_id)
    assert source_basis(session, seeded.subject_id) != before
    session.commit()


def test_postgres_roundtrip_migration(app, session, database_url):
    require_postgres(app)
    session.close()
    app.state.database.dispose()
    command.downgrade(alembic_config(database_url), 'base')
    upgrade_to_head(database_url)
    with app.state.database.session() as fresh:
        assert fresh.scalars(select(Subject)).all() == []


def test_postgres_lock_timeout_is_retryable_without_sql_or_secret_leak(app):
    require_postgres(app)
    @app.post('/test-lock-conflict')
    def conflicting_request():
        with app.state.database.session() as writer:
            writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
            writer.add(Subject(subject_id='private_test_id', display_name='do-not-echo-this-private-name'))
            writer.commit()
    with app.state.database.engine.connect() as holder:
        holder.execute(text('LOCK TABLE subjects IN SHARE ROW EXCLUSIVE MODE'))
        try:
            with TestClient(app, raise_server_exceptions=False) as http:
                response = http.post('/test-lock-conflict')
            assert response.status_code == 409, response.text
            assert response.json()['error_code'] == 'STATE_CONFLICT'
            assert 'private' not in response.text and 'INSERT' not in response.text
        finally:
            holder.rollback()

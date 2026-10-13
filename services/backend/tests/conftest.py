from collections.abc import Iterator
from pathlib import Path
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(BACKEND_ROOT))
    config.set_main_option("sqlalchemy.url", database_url.replace('%', '%%'))
    return config


def upgrade_to_head(database_url: str) -> None:
    """Apply every migration to a database that may be completely empty."""
    command.upgrade(alembic_config(database_url), "head")


@pytest.fixture
def settings(tmp_path: Path) -> Iterator[Settings]:
    # _env_file=None keeps the suite hermetic: a developer's local .env must not
    # change what the tests exercise.
    url = os.environ.get('REMEMBER_TEST_POSTGRES_URL')
    admin = None
    schema = 'rm_test_' + uuid4().hex
    if url:
        parsed = make_url(url)
        if parsed.get_backend_name() != 'postgresql' or not (parsed.database or '').endswith('_test'):
            raise ValueError('PostgreSQL tests require an explicitly named *_test database')
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
        url = parsed.update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    result = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url=url or f"sqlite:///{tmp_path / 'remember-me-test.db'}",
        object_store_backend="memory",
    )
    try:
        yield result
    finally:
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
            admin.dispose()


@pytest.fixture
def database_url(settings: Settings) -> str:
    upgrade_to_head(settings.database_url)
    return settings.database_url


@pytest.fixture
def app(settings: Settings, database_url: str):  # noqa: ANN201 - FastAPI app
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:  # noqa: ANN001 - FastAPI app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(app) -> Iterator[Session]:  # noqa: ANN001 - FastAPI app
    session = app.state.database.session()
    try:
        yield session
    finally:
        session.close()

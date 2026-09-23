from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Engine and session factory for one database URL.

    SQLite serves local development and tests; deployment supplies PostgreSQL
    (ADR-0001 D3). Migrations are the only schema authority — this class never
    creates tables.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            url, future=True, pool_pre_ping=True, connect_args=connect_args
        )
        if url.startswith("sqlite"):
            self._enable_sqlite_foreign_keys(self.engine)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    @staticmethod
    def _enable_sqlite_foreign_keys(engine: Engine) -> None:
        """SQLite ignores foreign keys unless asked; keep it close to PostgreSQL."""

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def session(self) -> Session:
        return self._session_factory()

    def dispose(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a session bound to the application engine."""
    database: Database = request.app.state.database
    session = database.session()
    try:
        yield session
    finally:
        session.close()
"""Alembic environment.

The database URL comes from the config override when one is supplied (tests do
this) and otherwise from REMEMBER_DATABASE_URL, so no connection string is
committed. One migration mechanism is the only schema authority (ADR-0001 D4).
"""

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.logging_config import configure_logging
from app.models import Base

config = context.config
target_metadata = Base.metadata

# Alembic reports each step through this logger, so migrations produce the same
# structured output as the service rather than failing silently.
configure_logging(get_settings().log_level)


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    connectable = create_engine(url, poolclass=pool.NullPool, future=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
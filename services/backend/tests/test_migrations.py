import sqlalchemy as sa
from alembic import command
from conftest import alembic_config, upgrade_to_head

from app.models import Base

FOUNDATION_TABLES = {"alembic_version", "subjects", "actors", "consents"}


def table_names(database_url: str) -> set[str]:
    engine = sa.create_engine(database_url, future=True)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migration_creates_the_foundation_tables_from_empty(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'empty.db'}"

    upgrade_to_head(database_url)

    assert table_names(database_url) == FOUNDATION_TABLES


def test_upgrade_is_repeatable(database_url):
    # Already at head; applying head again must be a no-op rather than an error.
    upgrade_to_head(database_url)

    assert table_names(database_url) == FOUNDATION_TABLES


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
    finally:
        engine.dispose()
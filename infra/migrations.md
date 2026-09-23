# Migrations

Alembic owns the schema (ADR-0001 D4). `services/backend/migrations/` is the only thing that creates or changes a table; the application never runs DDL, at startup or anywhere else. If a table is wrong, the migration is wrong, and the fix is a migration.

## Commands

All of them run from `services/backend`, against `REMEMBER_DATABASE_URL`:

| Command | Effect |
| --- | --- |
| `uv run alembic upgrade head` | Apply every pending migration. The step a deployment runs. |
| `uv run alembic current` | The revision this database is at, and whether it is head. |
| `uv run alembic history` | The chain, oldest first. |
| `uv run alembic downgrade -1` | Undo the most recent migration. Development and rollback rehearsal only. |
| `uv run alembic upgrade <from>:<to> --sql` | Print the SQL instead of running it. See [Reviewing the SQL](#reviewing-the-sql). |

```bash
$ uv run alembic history
0001_initial -> 0002_consent_scopes (head), registered consent scopes
<base> -> 0001_initial, initial subjects actors consents
```

## A fresh environment

```bash
cd services/backend
mkdir -p var                       # SQLite will not create the directory for you
uv run alembic upgrade head
uv run alembic current             # 0002_consent_scopes (head)
```

Migration logs are JSON, one line per step, so an upgrade leaves evidence of what it did rather than silence:

```json
{"timestamp": "2026-09-21T06:01:27.618625+00:00", "level": "INFO", "logger": "alembic.runtime.migration", "message": "Running upgrade  -> 0001_initial, initial subjects actors consents"}
{"timestamp": "2026-09-21T06:01:28.603342+00:00", "level": "INFO", "logger": "alembic.runtime.migration", "message": "Running upgrade 0001_initial -> 0002_consent_scopes, registered consent scopes"}
```

## Migrations in a deployment

- **One step, before the new code runs.** Migrations are not applied on startup, because several API instances starting together would race, and because a migration that fails should fail on its own rather than take the API down with it.
- **Backwards compatible within a release** where possible: add a column before the code requires it, stop using one before dropping it. Phase 1 has one deployer and no zero-downtime requirement, so this is a rule for later rather than a constraint now.
- **Reviewable before it runs.** See below.
- **A failed migration stops the rollout.** The database is at a known revision or it is not; there is no partial state to reason about, because each revision is applied in one transaction where the dialect supports transactional DDL (PostgreSQL does; SQLite does not, which is one more reason it is not a deployment target).

## Adding a migration

1. Change `app/models.py` first — the model is what the code reads.
2. Write the migration by hand under `migrations/versions/`, with a revision id, an accurate `down_revision`, and a docstring saying why the change exists.
3. Write the `downgrade()` as well as the `upgrade()`. A migration whose only way forward is forward is a migration nobody dares run.
4. **Do not edit a migration that has been applied to a shared database.** Add a new revision instead.
5. **Do not import application code into a migration.** A migration is a snapshot of the schema at one revision; importing `app.models` would let it silently change meaning when the application changes. The registered consent scopes, for example, are written out as literals in `0002_consent_scopes` rather than read from the enum.
6. Use batch mode for anything SQLite cannot do in place (constraint changes, column type changes). Alembic rebuilds the table on SQLite and takes the plain DDL path on PostgreSQL.

The test suite guards the agreement between the two: `tests/test_migrations.py` applies every migration to an empty database, downgrades back to base, and compares the migrated schema — tables, columns, nullability, indexes, and check constraints — against the models. A model change without a migration fails that test rather than surfacing later.

## The local/deployment split

| | Local development and CI | A real deployment |
| --- | --- | --- |
| Dialect | SQLite | PostgreSQL |
| Applied by | a developer, or the test fixture | a deployment step, before the code rolls out |
| Storage | a file under `var/` | a managed or self-hosted server |

SQLite is a development convenience, not a deployment target, and the difference is real: it has no timezone-aware datetime type (the API restores the offset on the way out — `as_utc` in `app/models.py`), it does not create missing directories, and it cannot add a constraint in place. Those three differences are handled in code rather than papered over. ADR-0001 D3 records this limitation honestly rather than claiming the two backends are interchangeable.

## Reviewing the SQL

A migration can be rendered as SQL for inspection, which is what a deployer should do before applying it to a shared database:

```bash
$ REMEMBER_DATABASE_URL="postgresql+psycopg://u:p@db-host:5432/remember_me" \
    uv run alembic upgrade 0001_initial:head --sql

BEGIN;

-- Running upgrade 0001_initial -> 0002_consent_scopes

ALTER TABLE consents ADD CONSTRAINT ck_consents_scope CHECK (scope IN ('RECORDING', 'VOICE'));

UPDATE alembic_version SET version_num='0002_consent_scopes' WHERE alembic_version.version_num = '0001_initial';

COMMIT;
```

**For SQLite this command does not work**, and that is expected rather than a defect: batch mode has to reflect the live table before it can write the rebuild, so it needs a connection. The error is explicit about it:

```text
FAILED: This operation cannot proceed in --sql mode; batch mode with dialect sqlite requires a
live database connection with which to reflect the table "consents".
```

The consequence is worth stating: a migration that is only ever rehearsed on SQLite is not fully reviewable before it runs. Reviewing the SQL therefore means rendering it for **PostgreSQL**, which is what a deployment actually applies, and using the SQLite run for development and CI.

## Rollback

`downgrade()` exists for every revision and is exercised by the suite, so a rollback is a known operation rather than an untested hope. In a deployment it is still an incident decision, not a routine one: rolling a migration back after new code has written data in the new shape can destroy that data, and no `downgrade()` can restore it. Take a backup first, or roll forward.
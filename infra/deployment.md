# Deployment and environments

Scope: how a Remember Me backend process is configured and started, what each environment is for, and what a deployer has to supply. Decisions behind this are in [ADR-0001](../docs/architecture/backend-adr.md); this document is the operator's view of them.

The deployment target is deliberately thin. No cloud provider is selected yet (Phase 1 non-goal), so nothing here names one, and everything here works on a single host.

## The environments

| Environment | Purpose | Database | Object store | Log level | Runs where |
| --- | --- | --- | --- | --- | --- |
| `development` | One developer's machine | SQLite under `services/backend/var/` | local filesystem under `services/backend/var/` | `INFO` (`DEBUG` while working) | the developer's host |
| `test` | The automated suite | SQLite in a temporary directory | in-memory | `WARNING` | CI, or the developer's host |
| `staging` | Integration before Product review; the environment the Android client is pointed at | SQLite locally, PostgreSQL in a real deployment | local filesystem locally, S3-compatible in a real deployment | `INFO` | a second process on a shared host, or a host of its own |
| production | Not yet defined | — | — | — | — |

Production is deliberately absent: it needs an identity provider, backups, and a provider decision, none of which Phase 1 authorizes. Staging is the furthest environment that exists.

`REMEMBER_ENVIRONMENT` names which of these a process believes it is in. It appears in every log line, so a log from the wrong environment is visible rather than silent.

## What an environment is

An environment is **one template plus the settings that differ**. The template is [`services/backend/.env.example`](../services/backend/.env.example); there is no per-environment copy of it, because copies drift and a drifted template is how a process ends up pointed at the wrong database.

Precedence, highest first: the process environment, then `.env`, then the defaults in `app/config.py`. A deployment therefore overrides the template by setting real environment variables, and never needs to edit it. `REMEMBER_` is the prefix on every key.

## Bringing up a second environment

This is the whole of it, and it is the sequence that was run to verify this document. It starts a `staging` process alongside a `development` one without touching development's data:

```bash
cd services/backend

# A staging environment gets its own state directory, so it cannot reach
# development's database or stored objects.
mkdir -p var/staging

export REMEMBER_ENVIRONMENT=staging
export REMEMBER_LOG_LEVEL=INFO
export REMEMBER_DATABASE_URL="sqlite:///./var/staging/remember-me.db"
export REMEMBER_OBJECT_STORE_ROOT="./var/staging/object-store"

uv sync                        # creates .venv from uv.lock
uv run alembic upgrade head    # migrations are the only schema authority
uv run python -m app.seed --subject-name "Staging Subject" --actor-name "Staging Actor"

# Port 8001 so it sits beside development's 8000.
uv run uvicorn app.main:app --port 8001
```

```bash
curl -s localhost:8001/health
# {"status":"ok"}
curl -s localhost:8001/ready
# {"status":"ready","components":{"database":"ok","object_store":"ok"}}
```

`var/` is git-ignored, so a staging environment created this way leaves nothing behind in the repository. To bring up a third environment, change the three paths and the port — nothing in the code knows the names `development` or `staging`.

The seed step is development and staging material only: it writes a Subject, an Actor, and one granted `RECORDING` consent. It prints the actor token once; the token is not stored in plaintext anywhere except as a digest. Production has no equivalent, because production subjects are not created by a command-line script.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `REMEMBER_ENVIRONMENT` | `development` | `development`, `staging`, or `test`. Appears in every log line. |
| `REMEMBER_LOG_LEVEL` | `INFO` | Root log level. `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `REMEMBER_DATABASE_URL` | `sqlite:///./var/remember-me.db` | A PostgreSQL deployment supplies `postgresql+psycopg://…`. Carries a credential — see [Secrets](#secrets). |
| `REMEMBER_OBJECT_STORE_BACKEND` | `local` | `local` or `memory`. The S3-compatible backend arrives with Issue #1, which owns the audio object path. |
| `REMEMBER_OBJECT_STORE_ROOT` | `./var/object-store` | Used by the `local` backend. Must be a directory this process may write. |

The directory a SQLite URL points at must exist before the first migration: SQLite does not create a missing parent directory, and the application does not create one silently, because a mistyped path should fail loudly rather than quietly produce an empty database.

## The process model

One codebase, two process roles (ADR-0001 D2):

| Process | Command | Port | State |
| --- | --- | --- | --- |
| API | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` | 8000 | Stateless. Several instances may run behind a load balancer. |
| Worker | arrives with Issue #1 | none | Owns the processing loop and the job lease. |

The API is stateless, so a request may land on any instance. Nothing that matters is kept in process memory: the trace id is per request, the database holds Episodes and jobs, and the object store holds audio.

Migrations are a **separate step**, not something a process does at startup. Several API instances starting at once must not race to migrate the same database, and a failed migration must not take the API down with it — see [migrations.md](migrations.md).

## Health and readiness

| Endpoint | Meaning | What a deployer should do with it |
| --- | --- | --- |
| `GET /health` | Liveness. Touches no dependency by design, so it answers even when the database is down. | Restart the process if it fails. Nothing else. |
| `GET /ready` | Readiness. Checks the database and the object store and returns `503` with per-component state when either is unreachable. | Remove the instance from rotation if it fails; do not restart on the strength of it alone. |

```bash
curl -s localhost:8000/ready
# {"status":"ready","components":{"database":"ok","object_store":"ok"}}
# {"status":"unavailable","components":{"database":"unreachable","object_store":"ok"}}
```

The split matters during an incident: a database outage makes instances unready but not unhealthy, and restarting them would not help.

## Observability baseline

What exists:

- **Structured logs.** Application, access, and migration logs are one JSON object per line with a timestamp, level, logger, and message. Nothing parses prose.
- **Request identification.** Every response carries `X-Request-ID`, generated at the request boundary. The same value is in the access log for that request and comes back in every error body as `request_id`, so a user-reported failure and a log line are the same identifier. It is also the value Issue #1 propagates to AI Core as the contract's `trace_id`.
- **One access line per request** with method, path, status code, and duration.
- **Environment and level as configuration**, so staging can be more verbose than development without a code change.
- **Errors with a stable code.** A failure is a code from a fixed list (`app/errors.py`), not a sentence to be pattern-matched.

What does not exist, and why: no metrics backend, no distributed tracing collector, no log shipping. Each needs a provider decision that Phase 1 does not authorize, and all three consume the baseline above rather than replacing it. The gaps are listed in ADR-0001's open items.

## Secrets

A secret reaches a process through its environment, and from nowhere else.

- `REMEMBER_DATABASE_URL` is the one setting that carries a credential today. In a deployment it is supplied by the platform's secret mechanism, never written into the repository, never into `.env` on a shared host, and never into a log line — the service logs the environment name, not the configuration.
- Provider credentials (speech-to-text, language model, voice provider) stay server-side and are read by the worker, not the API (ADR-0001 D10). None is committed and none is sent to Android.
- `.env` is git-ignored; `.env.example` holds defaults and comments only. If a real credential ever lands in a committed file it is an incident, not a cleanup: the credential must be rotated, because the history keeps it.

## PostgreSQL

A real staging or production deployment uses PostgreSQL. The code is written for it — the repositories, the migrations, and the timezone handling all target it (ADR-0001 D3) — and the local path uses SQLite only so that no developer needs a database server.

The driver is a deployment prerequisite, not a repository dependency, because a developer running only the local path does not need it:

```bash
cd services/backend
uv add "psycopg[binary]"
export REMEMBER_DATABASE_URL="postgresql+psycopg://user:password@db-host:5432/remember_me"
uv run alembic upgrade head
```

**Status, stated plainly:** this path has not been executed. No PostgreSQL server is reachable from the development machine, so the DSN above is documented rather than verified, and the driver is deliberately absent from `pyproject.toml` — a dependency that cannot be installed and exercised here would be a claim rather than a fact. Everything that can be checked without a server is checked: the migrations are written to run on both dialects, the SQLite path takes the table-rebuild route for constraint changes while PostgreSQL takes `ALTER TABLE`, and the test suite guards the model/migration agreement.

## Not covered here

- Production hardening: TLS termination, backups, restore drills, rate limits, an identity provider, secret rotation.
- Orchestration: whether the processes run in containers, on one host, or on a platform.
- Provider selection for speech-to-text, language model, or voice — all behind adapters and undecided.
- Any environment that handles real voice samples (Phase 3).
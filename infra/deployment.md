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

# Staging is not development, and the provider settings are where that shows.
# A fake provider is refused outside development and test, so an environment
# that leaves them at the default does not start — which is the intended
# outcome, not an obstacle to work around. Point these at the real services.
export REMEMBER_STT_BACKEND=http
export REMEMBER_STT_URL=http://127.0.0.1:8200
export REMEMBER_AI_BACKEND=http
export REMEMBER_AI_CORE_URL=http://127.0.0.1:8100

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

Readiness does not depend on the providers: they are reached per request, so a staging process starts and reports ready before the speech-to-text and AI Core services it points at are up. An upload made in the meantime fails with `STT_UNAVAILABLE` and is retried by the job's budget rather than being lost.

If staging genuinely has to come up before its providers exist, `REMEMBER_ALLOW_FAKE_PROVIDERS=true` builds the fakes instead and every process that does logs a WARNING naming the environment. That is the escape hatch for bringing an environment up, not a configuration to leave behind: the record it produces is placeholder text labelled as a placeholder, and no real acceptance run can be read off it.

The worker needs those provider settings too, because it is the process that calls them — start it with the same environment, in its own shell:

```bash
uv run python -m app.worker
```

`var/` is git-ignored, so a staging environment created this way leaves nothing behind in the repository. To bring up a third environment, change the three paths and the port — nothing in the code knows the names `development` or `staging`.

The seed step is development and staging material only: it writes a Subject, an Actor, and one granted `RECORDING` consent. It prints the actor token once; the token is not stored in plaintext anywhere except as a digest. Production has no equivalent, because production subjects are not created by a command-line script.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `REMEMBER_ENVIRONMENT` | `development` | `development`, `staging`, or `test`. Appears in every log line. |
| `REMEMBER_LOG_LEVEL` | `INFO` | Root log level. `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `REMEMBER_DATABASE_URL` | `sqlite:///./var/remember-me.db` | A PostgreSQL deployment supplies `postgresql+psycopg://…`. Carries a credential — see [Secrets](#secrets). |
| `REMEMBER_OBJECT_STORE_BACKEND` | `local` | `local`, `memory`, or `s3`. A real deployment uses `s3`; `local` and `memory` require no infrastructure and are what development, CI, and the test suite use. |
| `REMEMBER_OBJECT_STORE_ROOT` | `./var/object-store` | Used by the `local` backend. Must be a directory this process may write. |
| `REMEMBER_OBJECT_STORE_BUCKET` | `remember-me-audio` | Used by the `s3` backend. Must already exist: the service writes objects, it does not create buckets or set bucket policy. |
| `REMEMBER_OBJECT_STORE_ENDPOINT_URL` | unset | Set for MinIO or another S3-compatible service; unset means AWS resolves the endpoint for the region. Setting it also switches the client to path-style addressing, because a local MinIO has no `bucket.<host>` DNS record. |
| `REMEMBER_OBJECT_STORE_REGION` | `us-east-1` | Used by the `s3` backend. |
| `REMEMBER_MAX_UPLOAD_BYTES` | `26214400` (25 MiB) | The largest upload the boundary accepts. A reverse proxy in front of the API needs a limit at least this large, or the request is refused before it arrives. |
| `REMEMBER_STT_BACKEND` | `fake` | `fake` or `http`. The fake is refused outside `development` and `test`, so a deployment that has not configured a real provider fails at startup rather than recording placeholder transcripts. |
| `REMEMBER_STT_URL` | `http://127.0.0.1:8200` | Where the speech-to-text service is reachable from the **worker**, which is the process that calls it. |
| `REMEMBER_STT_PATH` | `/transcribe` | The provider's own path. It is configurable so that confirming the endpoint with whoever owns the provider needs no code change. |
| `REMEMBER_STT_TIMEOUT_SECONDS` | `60` | A timeout is `STT_TIMEOUT`, which the retry budget handles. |
| `REMEMBER_AI_BACKEND` | `fake` | `fake` or `http`. Same rule: the fake is refused outside `development` and `test`. |
| `REMEMBER_AI_CORE_URL` | `http://127.0.0.1:8100` | Where AI Core is reachable from the **worker**, which is the process that calls it. |
| `REMEMBER_AI_CORE_PATH` | `/process` | AI Core's own path. It is configurable so that confirming the endpoint with the AI Core owner needs no code change. |
| `REMEMBER_AI_TIMEOUT_SECONDS` | `30` | A timeout is a failure the retry budget handles. |
| `REMEMBER_ALLOW_FAKE_PROVIDERS` | `false` | The only way a fake provider runs outside `development` and `test`. Each process that builds one logs a WARNING naming the environment, so an environment running on placeholders states it rather than being inferred from the record. |
| `REMEMBER_JOB_MAX_ATTEMPTS` | `3` | Attempts **per stage**, so a transient failure in one stage does not spend the next stage's budget. |
| `REMEMBER_JOB_RETRY_BACKOFF_SECONDS` | `5` | How long a failed stage waits before it is retried. |
| `REMEMBER_JOB_LEASE_SECONDS` | `60` | How long a claim is good for. A worker renews it on a heartbeat while its stage runs, and a lease that expires returns the work to any worker, which is how a worker killed mid-stage is recovered. |

The directory a SQLite URL points at must exist before the first migration: SQLite does not create a missing parent directory, and the application does not create one silently, because a mistyped path should fail loudly rather than quietly produce an empty database.

## The object store

A real deployment sets `REMEMBER_OBJECT_STORE_BACKEND=s3`, which selects one adapter that serves AWS S3, MinIO, and anything else speaking the same API. What a deployer has to supply:

- **The bucket must already exist.** The service writes objects; it does not create buckets or set bucket policy. A missing bucket is an infrastructure failure, and it is reported as one rather than as a missing recording.
- **Credentials reach boto3 through boto3's own chain** — the process environment, a shared config file, or the instance role. No key is in `REMEMBER_*`, none is read by application code, and none belongs in `.env`. Provider credentials stay server-side (ADR-0001 D10).
- **Permissions: put, get, head, and delete.** Two things need the delete, and neither removes a recording that exists in the record. `/ready` proves the bucket accepts a write by writing, reading back, and removing `healthcheck/probe`. And a capture that stored its audio but could not commit its Episode — a concurrent retry with the same idempotency key won the row, or the commit itself failed — removes the object it wrote, because no Episode ever referenced it and nothing can observe it missing. A bucket that exists but is not writable should fail readiness, not the first upload.

Where an object lands is Backend's decision. The key is `audio/{subject_id}/{episode_id}/original`: the client's filename never reaches it, because a filename is client-controlled text and a key is a path. The database holds the object's size, content type, and a SHA-256 checksum the service computed itself — deliberately not the service's ETag, which is an MD5 for a simple upload but not for a multipart one and therefore cannot be compared across upload paths.

The adapter makes one attempt per call and does not retry underneath the job: a retry is the job's decision, made with the attempt count and the backoff in view, so a failure the worker sees is attributable rather than the end of an unknown number of hidden attempts. No audio that a durable Episode refers to is ever deleted: retention and deletion of recordings are not Phase 1 decisions.

## The process model

One codebase, two process roles (ADR-0001 D2):

| Process | Command | Port | State |
| --- | --- | --- | --- |
| API | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` | 8000 | Stateless. Several instances may run behind a load balancer. |
| Worker | `uv run python -m app.worker` | none | Owns the processing loop and the job lease. Reads the queue from the shared database and the audio from the shared object store. |

The API is stateless, so a request may land on any instance. Nothing that matters is kept in process memory: the trace id is per request, the database holds Episodes and jobs, and the object store holds audio.

The worker is **not** started by the API process: a stage that blocks for thirty seconds would otherwise occupy a web worker, and the two lifetimes have no reason to be coupled. It claims work by taking a lease on a queued job, so running more than one worker is safe. Two mechanisms carry that, and they are not redundant: a worker **renews** its lease on a heartbeat thread while its stage runs, which stops a stage that outlives its lease from being executed twice at all, and every transition out of a stage **writes the lease condition into its own `UPDATE`** and rolls the whole transaction back when it matches nothing, which is what makes a duplicate commit impossible even if a renewal does not land — and a best-effort thread on a process that can be descheduled can always fail to land. A worker that dies mid-stage therefore loses at most the stage in flight; the Episode, its audio, and everything committed before it stay where they are, and the work it held returns to whoever comes next when the lease runs out.

The worker's configuration is its own process's: it reads the same database and object store, and it is the process that actually calls the providers (`REMEMBER_STT_*`, `REMEMBER_AI_*`). The API builds the same providers at startup without calling them, so that an environment configured with a provider it is not allowed to use — a fake outside development and test — fails when it starts rather than in the worker long after the deployment looked healthy. Logs from the two processes interleave in the same JSON format, so a stage failure and the request that created the Episode are matchable by `trace_id`.

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
- **Request identification.** Every response carries `X-Request-ID`, generated at the request boundary. The same value is in the access log for that request and comes back in every error body as `request_id`, so a user-reported failure and a log line are the same identifier. It is also the value the capture boundary stores on the Episode and propagates to AI Core as the contract's `trace_id`, so one identifier spans the upload, the worker's stages, and the result a client reads back.
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
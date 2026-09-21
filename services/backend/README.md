# Backend Service

Owner: 王昊宇 (`qingtian-4`). Phase 1 — COMMITTED. See the [task brief](../../docs/team/03_WANGHAOYU_BACKEND_VOICE.md).

Platform decisions — language, data layer, object storage, auth boundary, job model, provider boundaries, client security, failure model, and the local verification path — are recorded in [ADR-0001](../../docs/architecture/backend-adr.md). Do not invent a platform decision outside it.

**Current status: the service foundation (Issue #8) and the environment and consent boundary (Issue #9).** Health and readiness, configuration, migrations, the Subject / Actor / Consent boundary, the consent API, object storage wiring, and structured logging exist and are tested. The upload, Episode, STT, job, and result APIs are Issue #1 and are not here yet.

Inputs and outputs must conform to [`packages/contracts`](../../packages/contracts/README.md).

## Layout

| Path | Contents |
| --- | --- |
| `app/config.py` | Environment configuration (`REMEMBER_*`) |
| `app/logging_config.py` | JSON log formatter and the trace-id context |
| `app/errors.py` | Backend-owned error codes |
| `app/db.py` | Engine and session factory |
| `app/models.py` | `Subject`, `Actor`, `Consent`, and the registered consent scopes |
| `app/repositories/` | All structured-data access |
| `app/security.py`, `app/tokens.py` | Token-to-Actor resolution |
| `app/storage/` | `ObjectStore` boundary, local filesystem and in-memory implementations |
| `app/api/` | HTTP surface |
| `app/seed.py` | Local development seed |
| `migrations/` | Alembic environment and the initial migration |
| `tests/` | The local verification suite |

## Requirements

Python 3.12+ and [uv](https://docs.astral.sh/uv/). No Docker, no PostgreSQL, and no network access are needed for local development or for the test suite (ADR-0001 D14).

## Run it locally

```bash
cd services/backend
uv sync                        # creates .venv from uv.lock
cp .env.example .env
mkdir -p var                   # SQLite and the local object store both live under ./var
uv run alembic upgrade head    # migrations are the only schema authority
uv run python -m app.seed --subject-name "Ada" --actor-name "Ada"
uv run uvicorn app.main:app --reload
```

`var/` is git-ignored. SQLite will not create a missing parent directory, so the directory is created explicitly rather than silently by the application — a mistyped database path should fail loudly rather than quietly produce an empty database.

`app.seed` prints a Subject, an Actor, a Consent, and a fresh actor token. The token is local development material and is never stored in plaintext — only its digest is. Check the running service with it:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/ready
curl -s localhost:8000/api/v1/session -H "Authorization: Bearer <the printed token>"
```

### The consent boundary, in one paste

`app.seed` prints a subject id and one granted `RECORDING` consent. Ask the boundary for a **voice** operation with that recording consent and it refuses; grant the separate voice consent and the same question succeeds:

```bash
TOKEN=<the printed actor token>
SUBJECT=<the printed subject_id>
RECORDING=<the printed consent_id>

ask() { curl -s -X POST localhost:8000/api/v1/consents/authorize \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"subject_id\":\"$SUBJECT\",\"scope\":\"$1\",\"consent_id\":\"$2\"}"; echo; }

ask VOICE "$RECORDING"
# {"error_code":"CONSENT_INVALID","error_message":"Consent … is not an active VOICE consent for subject …","request_id":"…"}

ask RECORDING "$RECORDING"
# {"authorized":true,"consent_id":"…","subject_id":"…","scope":"RECORDING","granted_at":"…"}

VOICE=$(curl -s -X POST localhost:8000/api/v1/consents \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"subject_id\":\"$SUBJECT\",\"scope\":\"VOICE\",\"evidence_ref\":\"local walkthrough\"}")
# {"consent_id":"consent_…","scope":"VOICE","status":"granted", …}

ask VOICE "$(echo "$VOICE" | sed 's/.*"consent_id":"\([^"]*\)".*/\1/')"
# {"authorized":true,"consent_id":"consent_…","scope":"VOICE","granted_at":"…"}
```

## Verification

The deterministic local command for this module, and the command CI runs:

```bash
cd services/backend && uv run pytest
```

It runs against SQLite, the in-memory object store, and migrations applied to an empty database. Record the command and its result in every Pull Request.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness. Touches no dependency, so it answers even when the database is down. |
| `GET /ready` | Readiness. Checks the database and the object store; returns `503` with per-component state when either is unreachable. |
| `GET /api/v1/session` | Resolves the bearer token to its Actor. |
| `POST /api/v1/consents` | Records a granted consent of one scope for one subject. The granting Actor comes from the credential, never from the body. |
| `POST /api/v1/consents/authorize` | **The consent boundary.** Verifies that an active consent authorizes this scope for this subject, or fails with `CONSENT_REQUIRED` / `CONSENT_INVALID`. Every sensitive operation asks here. |
| `GET /api/v1/consents?subject_id=&scope=` | Lists a subject's consents, optionally filtered by scope. |
| `GET /api/v1/consents/{consent_id}` | Reads one consent record. |
| `POST /api/v1/consents/{consent_id}/revoke` | Revokes a consent. The record stays; what was done under it was done. |

URL paths are Backend-owned. Payload shapes for Capture, Processing Status, AI Process, and Episode Result belong to the contract and arrive with Issue #1.

Every response carries an `X-Request-ID`. The value is generated at the request boundary and is the identifier Issue #1 propagates as the contract's `trace_id`.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `REMEMBER_ENVIRONMENT` | `development` | `development`, `staging`, or `test` |
| `REMEMBER_LOG_LEVEL` | `INFO` | Root log level; application, access, and migration logs are JSON |
| `REMEMBER_DATABASE_URL` | `sqlite:///./var/remember-me.db` | Deployment supplies PostgreSQL; the driver is a deployment prerequisite, not a repository dependency |
| `REMEMBER_OBJECT_STORE_BACKEND` | `local` | `local` or `memory` |
| `REMEMBER_OBJECT_STORE_ROOT` | `./var/object-store` | Used by the `local` backend |

`.env` is git-ignored and `.env.example` carries no secret. One template serves every environment: a deployment overrides these variables in its own process environment rather than editing a copy. [infra/deployment.md](../../infra/deployment.md) covers the environments and the process model; [infra/migrations.md](../../infra/migrations.md) covers the schema step. The S3-compatible object store backend arrives with Issue #1.

## Authentication (Phase 1 minimum)

A request presents `Authorization: Bearer <actor token>`. The token resolves to an `Actor`, which is what attributes recorded work to whoever operated the app.

This is **not** production authentication: there is no identity provider, no expiry, and no rotation. The `Actor` record is the seam a real identity provider plugs into later. Android holds no privileged backend credential (ADR-0001 D10).

There are also no roles. Any authenticated Actor may grant or revoke a consent for any Subject, and the record says which Actor did it — it does not restrict who may. In Phase 1 the Actor is the subject or the person operating the app on their behalf, and a role model would need the identity provider that Phase 1 does not have. The consent boundary is about *which scope* an operation holds, not about which actor may hold it.

## Error codes

Errors return `{"error_code", "error_message", "request_id"}`. The envelope is Backend-owned: the contract fixes `error_code` and `error_message` on Processing Status, and this reuses those names for request-level failures rather than inventing competing ones.

| Code | Status | Meaning |
| --- | --- | --- |
| `AUTH_REQUIRED` | 401 | No usable actor credential was presented |
| `AUTH_INVALID` | 401 | The credential was presented but is not recognized |
| `REQUEST_INVALID` | 422 | The request itself was malformed — an unknown field, a missing one, or a scope this codebase does not register |
| `ACTOR_NOT_FOUND` | 404 | No such Actor |
| `SUBJECT_NOT_FOUND` | 404 | No such Subject |
| `CONSENT_REQUIRED` | 403 | A sensitive operation arrived without a consent reference |
| `CONSENT_INVALID` | 403 | The consent reference is absent, revoked, another Subject's, or another scope |
| `CONSENT_NOT_FOUND` | 404 | No such consent record |

The ingest, STT, and AI Core codes listed in ADR-0001 D11 arrive with Issue #1.

## Data model

`Subject` is the modeled person; `Actor` is whoever currently operates the app. They are distinct records from the start so Creator Mode and Legacy Mode can move between actors around one subject.

`Consent` ties a Subject to the Actor who granted it and carries a `scope`. Two scopes are registered — `RECORDING` (capturing the subject's audio and text) and `VOICE` (building and using a voice profile from it) — and they are separate grants: a voice operation is never satisfiable by a recording consent. Three things enforce that rather than describing it: the database refuses a scope this codebase does not register (`ck_consents_scope`), verification matches scope exactly, and the API boundary takes the scope as an explicit parameter. A sensitive operation must **verify** an active consent for the subject and scope it needs; a missing, revoked, or subject-mismatched reference is a validation error rather than a warning. [`services/voice/README.md`](../voice/README.md) documents the boundary, including the rule that third-party speech never enters a subject's voice data.

Timestamps are stored in UTC and returned with the offset restored (`as_utc` in `app/models.py`), because SQLite has no timezone-aware type and would otherwise return the same field differently from PostgreSQL.

Migrations under `migrations/` are the only schema authority; the application never creates tables.

## Not in this module yet

- Upload, Episode persistence, STT, job, status, and result APIs, and the S3-compatible object store backend — Issue #1.
- The PostgreSQL driver, which a deployment adds as a prerequisite — see [infra/deployment.md](../../infra/deployment.md).
- Anything that processes voice — Phase 3. Phase 1 defines the consent boundary and the third-party exclusion rule only.
- Person Model, Twin, and Memory/Graph/Persona APIs — Phase 2.
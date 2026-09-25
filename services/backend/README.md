# Backend Service

> On the isolated `ios` branch, migration `0004_cloud_twin_consent` adds an
> independent `CLOUD_TWIN` scope. The provisional `/api/v1/subjects/{id}/memories`
> and `/api/v1/subjects/{id}/twin/query` routes are implemented in
> `app/api/core_twin.py`. The latter requires an active Cloud Twin consent from
> the calling Actor, never RECORDING or VOICE consent. It only quotes a matching
> Subject evidence excerpt as ORIGINAL; otherwise it returns explicit
> uncertainty. These Backend-owned shapes are not yet a frozen Phase 2 Contract.

Owner: 王昊宇 (`qingtian-4`). Phase 1 — COMMITTED. See the [task brief](../../docs/team/03_WANGHAOYU_BACKEND_VOICE.md).

Platform decisions — language, data layer, object storage, auth boundary, job model, provider boundaries, client security, failure model, and the local verification path — are recorded in [ADR-0001](../../docs/architecture/backend-adr.md). Do not invent a platform decision outside it.

**Current status: the service foundation (Issue #8), the environment and consent boundary (Issue #9), and audio ingestion (Issue #1).** Health and readiness, configuration, migrations, the Subject / Actor / Consent boundary, the consent API, object storage wiring, structured logging, the capture and Episode boundary, the STT and AI Core adapters, the processing worker, and the status and result APIs exist and are tested.

Inputs and outputs must conform to [`packages/contracts`](../../packages/contracts/README.md).

## Layout

| Path | Contents |
| --- | --- |
| `app/config.py` | Environment configuration (`REMEMBER_*`) |
| `app/logging_config.py` | JSON log formatter and the trace-id context |
| `app/errors.py` | Backend-owned error codes, and whether the work is worth retrying |
| `app/db.py` | Engine and session factory |
| `app/models.py` | `Subject`, `Actor`, `Consent`, `Episode`, `Job`, `Evidence`, `MemoryItem` |
| `app/contracts.py` | The Phase 1 contract shapes as Pydantic models |
| `app/repositories/` | All structured-data access |
| `app/security.py`, `app/tokens.py` | Token-to-Actor resolution |
| `app/storage/` | `ObjectStore` boundary: local filesystem, in-memory, and S3-compatible |
| `app/stt.py` | Speech-to-text boundary: the deterministic fake and the HTTP transport |
| `app/ai_core.py` | AI Core boundary: the fake and the HTTP transport |
| `app/providers.py` | The one rule both provider boundaries share: where a fake may run |
| `app/worker.py` | The processing worker: one stage per tick, under a renewable lease |
| `app/api/` | HTTP surface |
| `app/seed.py` | Local development seed |
| `migrations/` | Alembic environment and the migrations |
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

### The ingestion path, in one paste

The worker is a **separate process**. It runs one stage per tick — transcribe, then extract, then model — and commits each stage on its own, which is why the Episode's status is observable while the work is happening:

```bash
cd services/backend
uv run python -m app.worker
```

In another shell, capture a recording. Any bytes will do: the fake provider reads no speech, and says so in the transcript it returns.

```bash
TOKEN=<the printed actor token>
SUBJECT=<the printed subject_id>
CONSENT=<the printed consent_id>

printf 'RIFF\x00\x00\x00\x00WAVEfmt any bytes at all' > walk-in-the-park.m4a

curl -s -X POST localhost:8000/api/v1/episodes \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@walk-in-the-park.m4a;type=audio/mp4' -F subject_id="$SUBJECT" \
  -F recording_consent_id="$CONSENT" -F source=ANDROID_MIC \
  -F recorded_at=2026-09-21T09:30:00+00:00 -F audio_ref=walk-in-the-park.m4a \
  -F idempotency_key=capture-0001
# {"episode_id":"ep_…","upload_status":"uploaded"}

EPISODE=<the printed episode_id>

curl -s localhost:8000/api/v1/episodes/$EPISODE -H "Authorization: Bearer $TOKEN"
# {"episode_id":"ep_…","status":"uploaded","trace_id":"…"}
# The status names the stage the worker is on: transcribing, extracting,
# modeling, then ready. With the fake providers each stage finishes in
# milliseconds, so a poll usually sees the last one — the point is that each is
# committed on its own, so a client polling during a real (slow) provider call
# sees where the work is rather than waiting for the whole pipeline.

curl -s localhost:8000/api/v1/episodes/$EPISODE/result -H "Authorization: Bearer $TOKEN"
# {"episode_id":"ep_…","status":"ready","model_version":"fake-ai-v1","memory_items":[…],"trace_id":"…"}
```

The content type is stated explicitly because a client that sends a type which is not `audio/*` is refused: it is the one field the boundary uses to decide whether the bytes are audio at all. A `.m4a` file is not recognized by every `curl` build, and the guess would otherwise be `application/octet-stream`.

Repeat the capture with the same `idempotency_key` and the same bytes and you get `200` with **the same `episode_id`** rather than a second Episode. Same key, different bytes, is `409 IDEMPOTENCY_CONFLICT`: that is a client bug rather than a retry, and the stored recording is left alone.

The bytes reach the object store before the Episode row commits, because the row points at the object and a row pointing at nothing would claim to hold a recording it does not have. That order leaves one window, and it is closed on the spot: a request that stored the audio and then failed to commit its Episode — a concurrent retry with the same key won the row, or the commit itself failed — deletes the object it wrote. Nothing ever referenced that object, so nothing can observe it missing. This is not the cleanup-on-failure ADR-0001 D11 rejects, which is about deleting the audio of an Episode that was durably recorded.

To watch the failure path — the Episode stays readable, and the audio stays where it was:

```bash
curl -s -X POST localhost:8000/api/v1/episodes \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@walk-in-the-park.m4a;type=audio/mp4' -F subject_id="$SUBJECT" \
  -F recording_consent_id="$CONSENT" -F source=ANDROID_MIC \
  -F recorded_at=2026-09-21T09:30:00+00:00 -F audio_ref=walk-in-the-park.m4a \
  -F idempotency_key=capture-0002
# {"episode_id":"ep_…","upload_status":"uploaded"}

SECOND=<the printed episode_id>

# Nothing is listening on port 9, so every call to AI Core is refused. A zero
# backoff just makes the retries quick to watch.
REMEMBER_AI_BACKEND=http REMEMBER_AI_CORE_URL=http://127.0.0.1:9 \
  REMEMBER_JOB_RETRY_BACKOFF_SECONDS=0 uv run python -m app.worker

curl -s localhost:8000/api/v1/episodes/$SECOND -H "Authorization: Bearer $TOKEN"
# While the retries are in flight: {"status":"extracting","error_code":"AI_UNAVAILABLE", …}
# Once the attempts are gone:       {"status":"failed","error_code":"AI_UNAVAILABLE", …}
```

The transcript the transcribe stage produced is still on the Episode: a failing model does not get to destroy the recording, or the work already done on it. `AI_UNAVAILABLE` is retryable and has a bounded budget, so a provider that stays down ends the Episode rather than retrying it forever.

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
| `POST /api/v1/consents/authorize` | **The consent boundary.** Verifies that a consent **this Actor granted** authorizes this scope for this subject, or fails with `CONSENT_REQUIRED` / `CONSENT_NOT_FOUND` / `CONSENT_INVALID`. Every sensitive operation asks here. |
| `GET /api/v1/consents?subject_id=&scope=` | Lists the consents **this Actor** granted for a subject, optionally filtered by scope. Another Actor's grants for the same subject are filtered out, not reported. |
| `GET /api/v1/consents/{consent_id}` | Reads one consent record this Actor granted. Another Actor's is `CONSENT_NOT_FOUND`. |
| `POST /api/v1/consents/{consent_id}/revoke` | Revokes a consent this Actor granted. The record stays; what was done under it was done. |
| `POST /api/v1/episodes` | **Capture.** Takes the audio as multipart, verifies an active `RECORDING` consent this Actor granted, stores the bytes, and commits the Episode before any processing runs. `201` for a new Episode, `200` with the same body for a retried one. |
| `GET /api/v1/episodes/{episode_id}` | **Processing status.** The contract's `processingStatus`, polled by a client that wants to know where an Episode is. Readable only by the Actor that captured it. |
| `GET /api/v1/episodes/{episode_id}/result` | **Episode result.** The contract's `episodeResult`, once the Episode is `ready`. Before that it is `409 EPISODE_NOT_READY`, which a poller can tell apart from `404`. Readable only by the Actor that captured it. |
| `GET /api/v1/subjects/{subject_id}/memories` | Isolated iOS branch's provisional Phase 2 cross-Episode Memory list with evidence. Actor-owned Episodes only. |
| `PUT /api/v1/subjects/{subject_id}/memories/{memory_item_id}/correction` | Record an Actor's proposed correction; the disputed source claim is immediately excluded from Twin retrieval. |
| `DELETE /api/v1/subjects/{subject_id}/memories/{memory_item_id}/correction` | Withdraw that correction proposal. |
| `DELETE /api/v1/subjects/{subject_id}/memories/{memory_item_id}` | Remove one derived Memory from Episode results and Twin retrieval. Source Episode and raw Evidence remain. |
| `POST /api/v1/subjects/{subject_id}/twin/query` | Provisional evidence router requiring a separate active `CLOUD_TWIN` consent. |
| `POST /api/v1/subjects/{subject_id}/calibrations` | Lock a Twin answer and evidence before the Actor can submit a human answer. Requires active `CLOUD_TWIN` consent. |
| `GET /api/v1/subjects/{subject_id}/calibrations` | List this Actor's calibration records. |
| `POST /api/v1/subjects/{subject_id}/calibrations/{calibration_id}/answer` | Submit immutable Actor-provided human answer and five manual gap marks. |

URL paths are Backend-owned. Payload shapes belong to the contract: Capture, Processing Status, and Episode Result are the `captureEpisode`, `processingStatus`, and `episodeResult` shapes, and the AI Core request and answer are `aiCoreInput` and `aiCoreOutput`.

The provisional Phase 2 paths above are Backend-owned additions on `ios` and
do not change the frozen Contract. A correction is feedback, not a verified
replacement of the Subject's words. Deleting a derived Memory does not erase
the source recording or transcript.
Calibration records are Actor-submitted observations. The current account model
cannot prove the Actor is the Subject, so the Backend does not turn them into
verified Subject evidence or automatically update the Person Model.

A response carries only fields the contract defines, and omits the optional ones rather than sending `null` — the schema types them as strings and numbers, so an explicit null would not validate. `job_id` is internal and never appears in a response; clients address work by `episode_id`.

The HTTP AI Core adapter applies the same rule to outbound `aiCoreInput`: absent `trace_id` or `subject_context` is omitted, while a present value is sent unchanged. The provider tests validate both wire shapes against the frozen Contract v0.1 schema.

Every response carries an `X-Request-ID`. The value is generated at the request boundary and is the identifier Issue #1 propagates as the contract's `trace_id`.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `REMEMBER_ENVIRONMENT` | `development` | `development`, `staging`, or `test` |
| `REMEMBER_LOG_LEVEL` | `INFO` | Root log level; application, access, and migration logs are JSON |
| `REMEMBER_DATABASE_URL` | `sqlite:///./var/remember-me.db` | Deployment supplies PostgreSQL; the driver is a deployment prerequisite, not a repository dependency |
| `REMEMBER_OBJECT_STORE_BACKEND` | `local` | `local`, `memory`, or `s3`. Deployment uses `s3` |
| `REMEMBER_OBJECT_STORE_ROOT` | `./var/object-store` | Used by the `local` backend |
| `REMEMBER_OBJECT_STORE_BUCKET` | `remember-me-audio` | Used by the `s3` backend |
| `REMEMBER_OBJECT_STORE_ENDPOINT_URL` | unset | Set for MinIO or another S3-compatible service. Setting it also switches the client to path-style addressing |
| `REMEMBER_OBJECT_STORE_REGION` | `us-east-1` | Used by the `s3` backend |
| `REMEMBER_MAX_UPLOAD_BYTES` | `26214400` (25 MiB) | The largest upload the boundary accepts |
| `REMEMBER_STT_BACKEND` | `fake` | `fake` or `http`. `fake` is refused outside `development` and `test` |
| `REMEMBER_STT_URL` | `http://127.0.0.1:8200` | Used by the `http` backend: `POST <url><path>` with the audio as the body |
| `REMEMBER_STT_PATH` | `/transcribe` | The provider's path, which is its own surface rather than the contract's |
| `REMEMBER_STT_TIMEOUT_SECONDS` | `60` | A timeout is `STT_TIMEOUT`, which the budget retries |
| `REMEMBER_AI_BACKEND` | `fake` | `fake` or `http`. `fake` is refused outside `development` and `test` |
| `REMEMBER_AI_CORE_URL` | `http://127.0.0.1:8100` | Used by the `http` backend |
| `REMEMBER_AI_CORE_PATH` | `/process` | AI Core's path, which is its own surface rather than the contract's |
| `REMEMBER_AI_TIMEOUT_SECONDS` | `30` | A timeout is a failure the budget retries |
| `REMEMBER_ALLOW_FAKE_PROVIDERS` | `false` | The only way a fake runs outside `development` and `test`. Each process that builds one logs a WARNING naming the environment |
| `REMEMBER_JOB_MAX_ATTEMPTS` | `3` | Per stage, so a transient failure in one stage does not spend the next stage's budget |
| `REMEMBER_JOB_RETRY_BACKOFF_SECONDS` | `5` | How long a failed stage waits before it is retried |
| `REMEMBER_JOB_LEASE_SECONDS` | `60` | How long a claim is good for; a worker renews it while its stage runs, and a lease that expires returns the work to any worker |

`.env` is git-ignored and `.env.example` carries no secret. One template serves every environment: a deployment overrides these variables in its own process environment rather than editing a copy. [infra/deployment.md](../../infra/deployment.md) covers the environments and the process model; [infra/migrations.md](../../infra/migrations.md) covers the schema step.

## Authentication (Phase 1 minimum)

A request presents `Authorization: Bearer <actor token>`. The token resolves to an `Actor`, which is what attributes recorded work to whoever operated the app.

This is **not** production authentication: there is no identity provider, no expiry, and no rotation. The `Actor` record is the seam a real identity provider plugs into later. Android holds no privileged backend credential (ADR-0001 D10).

There are also no roles in the identity-provider sense, but a consent is not a free-floating record either. **Granting is open**: any authenticated Actor may grant a consent for an existing Subject, and the grant records which Actor made it. In Phase 1 that grant is the only way an Actor acquires authority over a Subject's records — the subject-to-actor relationship is not modeled yet — so narrowing who may grant would leave no way to obtain the authority the rest of the API enforces.

**Everything after the grant is scoped to it.** A consent can be read, used, or revoked **only by the Actor that granted it**. A request naming another Actor's consent is answered exactly as one naming a record that does not exist (`CONSENT_NOT_FOUND`), so no response discloses that another Actor's grant exists. This is why the refusal is a 404 rather than a 403: `CONSENT_INVALID` already means "yours, but it does not authorize this scope, this subject, or this moment", and a distinguishable "exists but is not yours" would let one Actor enumerate another's grants. The consent boundary is therefore about *which scope* an operation holds **and** which Actor holds it (ADR-0001 D7).

**An Episode is readable only by the Actor that captured it**, for the same reason and with the same answer: another Actor's Episode is `EPISODE_NOT_FOUND`, not a distinguishable refusal. The filter is on the query rather than applied to a row that was already fetched, so an Episode belonging to another Actor is never loaded at all. The worker is the one reader that is not an Actor: it addresses Episodes by `episode_id` alone, because the lease is what gives it the authority to touch them.

## Providers

Speech-to-text and AI Core are both behind a Protocol, and neither names a vendor (ADR-0001 D9). Each has two adapters: a deterministic **fake** that runs no real work and labels its output as its own, and an **`http`** transport that posts to a service over HTTP and maps every way the call can fail onto a code from the taxonomy.

The fake is refused at startup outside `development` and `test`, so a deployment that forgot to configure a real provider **fails to start** rather than filling the record with placeholder transcripts — the failure is loud and immediate instead of silent and historical. `REMEMBER_ALLOW_FAKE_PROVIDERS=true` is the one exception, for bringing an environment up end to end before its real provider is reachable; a process that builds a fake under that override logs a WARNING naming the environment, so an environment running on placeholders says so rather than being inferred from the record afterwards. Note that the fake is the **default** for both backends: a deployment sets `http` explicitly, and the startup refusal is what catches it if it does not.

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
| `CONSENT_INVALID` | 403 | The caller's own consent, but revoked, for another Subject, or for another scope |
| `CONSENT_NOT_FOUND` | 404 | No such consent for the calling Actor — an unknown id and another Actor's grant answer identically |
| `AUDIO_INVALID` | 400 | The upload is empty, or its content type is not audio |
| `AUDIO_TOO_LARGE` | 413 | The upload is over `REMEMBER_MAX_UPLOAD_BYTES` |
| `IDEMPOTENCY_CONFLICT` | 409 | An idempotency key was reused for different audio |
| `EPISODE_NOT_FOUND` | 404 | No such Episode for the calling Actor — an unknown id and another Actor's Episode answer identically |
| `EPISODE_NOT_READY` | 409 | The result was asked for before the Episode finished processing |
| `STORAGE_UNAVAILABLE` | 503 | Object storage refused the upload. No Episode is written: a record whose audio never arrived would claim to hold something it does not have |
| `AUDIO_UNAVAILABLE` | 503 | The audio an Episode points at could not be read from object storage |
| `STT_UNAVAILABLE` | 503 | No speech-to-text provider could be reached |
| `STT_FAILED` | 502 | The provider ran and could not produce a transcript for this audio |
| `STT_TIMEOUT` | 504 | The speech-to-text provider did not answer in time |
| `STT_EMPTY_TRANSCRIPT` | 422 | The provider returned no text, so there is nothing to extract |
| `AI_UNAVAILABLE` | 503 | AI Core could not be reached or answered HTTP 503 |
| `AI_FAILED` | 502 | AI Core refused the request, including HTTP 413, 422, and 502 |
| `AI_TIMEOUT` | 504 | AI Core did not answer in time or answered HTTP 504 |
| `AI_SCHEMA_INVALID` | 502 | AI Core answered with something that is not a valid `aiCoreOutput`, including a field v0.1 does not define |
| `INTERNAL` | 500 | A stage raised something outside this taxonomy. Recorded on the Episode like any other failure |

A processing failure is not a request failure: it is recorded **on the Episode** as `error_code` and `error_message`, and the Episode stays readable. The codes that a stage can fail with are also the ones the worker decides about, and `retryable` is part of the code rather than a decision each call site makes: `AUDIO_UNAVAILABLE`, `STORAGE_UNAVAILABLE`, `STT_UNAVAILABLE`, `STT_TIMEOUT`, `AI_UNAVAILABLE`, `AI_TIMEOUT`, and `INTERNAL` are worth asking again, while `STT_EMPTY_TRANSCRIPT`, `STT_FAILED`, `AI_FAILED`, and `AI_SCHEMA_INVALID` would fail the same way twice and end the Episode immediately.

The AI Core HTTP adapter makes one request per worker attempt. Its 503 and 504 responses use the worker's bounded retry and backoff; 413, 422, and 502 end the AI stage without retrying. The original audio and transcript remain on the Episode when extraction fails.

The codes are Backend-owned: the contract types `error_code` and `error_message` as free strings, so adding one is not a contract change, while renaming one a client branches on is a compatibility concern. ADR-0001 D11 is the decision record for this taxonomy.

## Data model

`Subject` is the modeled person; `Actor` is whoever currently operates the app. They are distinct records from the start so Creator Mode and Legacy Mode can move between actors around one subject.

`Consent` ties a Subject to the Actor who granted it and carries a `scope`. Two scopes are registered — `RECORDING` (capturing the subject's audio and text) and `VOICE` (building and using a voice profile from it) — and they are separate grants: a voice operation is never satisfiable by a recording consent. Three things enforce that rather than describing it: the database refuses a scope this codebase does not register (`ck_consents_scope`), verification matches scope exactly, and the API boundary takes the scope as an explicit parameter. A sensitive operation must **verify** an active consent for the subject and scope it needs, **granted by the calling Actor**; a missing reference, a revoked or subject-mismatched or scope-mismatched one, and a grant belonging to another Actor are all refusals rather than warnings. [`services/voice/README.md`](../voice/README.md) documents the boundary, including the rule that third-party speech never enters a subject's voice data.

`Episode` is one captured recording. Its row is written **before** any speech-to-text or AI work runs, and it holds a reference to the audio plus that object's metadata rather than the bytes. `idempotency_key` is unique per (subject, actor), which is what makes a retried upload return the Episode that already exists instead of a second one: the exactly-one-Episode guarantee is a database constraint rather than a convention in the handler.

`Job` is both the work record and the queue — there is no broker. One job per Episode, advanced one stage per tick, and a lease is what makes a worker the only process running that stage. A lease that expires returns the work to any worker, which is how a worker that dies mid-stage is recovered instead of stranding an Episode.

More than one worker can run, and the lease is what makes that safe. Two things are needed for it, and they answer different halves of one hazard. A worker **renews** its lease on a heartbeat thread while its stage runs, which stops a stage that outlives its lease — the normal case when a real provider is slower than the default lease — from being executed twice at all. And every transition out of a stage **writes the lease condition into its own `UPDATE`** (same owner, still running, not yet expired) and rolls the transaction back whole if it matches nothing, which is what makes a duplicate result impossible even when renewal fails, as a best-effort thread on a process that can be descheduled always can. A worker that lost its lease commits nothing: not the stage's advance, and not the transcript it produced.

`Evidence` and `MemoryItem` are the result. Evidence is stored rather than discarded because a memory whose evidence is gone cannot be traced back to what the subject actually said, and re-deriving it later is impossible once the model that produced it is gone. Every memory item carries the model, prompt, and schema versions that produced it, so a stored memory says what it was validated against rather than what happens to be current when it is read back.

Timestamps are stored in UTC and returned with the offset restored (`as_utc` in `app/models.py`), because SQLite has no timezone-aware type and would otherwise return the same field differently from PostgreSQL.

Migrations under `migrations/` are the only schema authority; the application never creates tables.

## Not in this module yet

- The graph and persona updates in AI Core's answer. They are Phase 2 shapes and are not committed, so the fake returns them empty and the model stage holds the boundary rather than filling them with something invented.
- A frozen speech-to-text vendor. Both adapters are in place — the fake, and an `http` one that speaks this module's own wire contract — but which service sits behind it is not decided (ADR-0001 D9).
- The PostgreSQL driver, which a deployment adds as a prerequisite — see [infra/deployment.md](../../infra/deployment.md).
- Anything that processes voice — Phase 3. Phase 1 defines the consent boundary and the third-party exclusion rule only.
- Person Model, Twin, and Memory/Graph/Persona APIs — Phase 2.

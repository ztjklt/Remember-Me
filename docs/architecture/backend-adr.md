# ADR-0001 — Backend Platform, Data, Storage, Auth, and Failure Model

- **Status:** Proposed — awaiting ratification by the Product / Integration Owner (Issue #13)
- **Date:** 2026-09-21
- **Decider:** 王昊宇 `@qingtian-4` (Backend / Voice / Infrastructure)
- **Ratifier:** 张天霁 `@ztjklt` (Product / Repo / Integration)
- **Phase:** Phase 1 — Golden Path
- **Related:** Issue #13 (this decision), Issue #8 (foundation), Issue #1 (ingestion), [Architecture baseline](README.md), [Contract v0.1](../../packages/contracts/README.md)
- **Path note:** Issue #13 names `docs/architecture/adr/ADR-0001-backend-platform.md` as the canonical location and permits an equivalent agreed path. This file is that decision record; if the ratifier prefers the named path, it moves without any content change.

**Delivery-policy update (2026-09-26):** Local checks remain useful diagnostics, but CI and a recorded test command are no longer mandatory PR merge gates. The current policy is in [team ownership](../team/00_TEAM_OWNERSHIP.md).

## Context

The engineering baseline proposes Supabase / PostgreSQL plus Object Storage, an independent Backend, and a Worker layer, but the reasoning and the boundaries were never written down. Without a decision record, Backend, Android, and AI Core each risk binding to a different assumed architecture.

This ADR fixes the platform decisions. It is deliberately narrow: it decides **how** the Phase 1 backend is built, not **what** the product does. Contract shapes are owned by `packages/contracts` and are not modified here.

Two constraints shape most decisions below:

1. **Backend needs a deterministic local verification command for quick diagnostics.** The available development machine has `python3.13` and `uv`, and has **no Docker and no PostgreSQL**. The default check should not need a container.
2. **No external provider is chosen.** STT, LLM, and Voice providers are all still open. Every one of them must sit behind an adapter so that Phase 1 can be built and verified end to end without selecting a vendor.

## Decision summary

| # | Decision | Choice | Rejected alternatives |
| --- | --- | --- | --- |
| D1 | Language / framework | Python 3.12+ with FastAPI | Node/TypeScript, Kotlin/Spring Boot, Go |
| D2 | Deployment shape | One Backend service + one Worker process, one codebase | Microservices per worker, serverless functions |
| D3 | Data layer | PostgreSQL as system of record, accessed through repositories | Supabase SDK as data access, document store, SQLite in production |
| D4 | Migrations | Alembic, one versioned mechanism | `create_all()` at import, hand-written SQL, dashboard-only changes |
| D5 | Object layer | S3-compatible object storage behind an `ObjectStore` adapter | Audio blobs in PostgreSQL, local filesystem in production, client-direct upload |
| D6 | Upload transport | One multipart request to Backend | Handle-then-confirm two-step, presigned direct-to-storage |
| D7 | Auth boundary | `subject` / `actor` / `consent` as distinct records, no external IdP | External IdP now, one shared `users` table |
| D8 | Job model | DB-backed job table with worker lease; no broker | Celery/Redis/RabbitMQ/Kafka, synchronous in-request processing |
| D9 | Provider boundary | `STTAdapter`, `AICoreClient`, `VoiceProviderAdapter` | Vendor SDK called directly from the API layer |
| D10 | Client security | Android holds no secret and no storage credential | Any cloud key in the app, presigned URLs as the Phase 1 upload path |
| D11 | Failure model | Episode and raw audio persist before any STT or AI work | Process-first, cleanup-on-failure |
| D12 | Idempotency | Unique on `(subject_id, actor_id, idempotency_key)` | Content-hash dedup, client-generated `episode_id` |
| D13 | Observability | Structured JSON logs plus `trace_id` propagation | Free-text logs, exposing `job_id` to clients |
| D14 | Local verification | `uv run pytest` with SQLite, local object store, fake adapters | Docker-only test path |

---

## D1 — Python 3.12+ with FastAPI

**Decision.** The Backend and Worker are Python services built on FastAPI, using Pydantic for request/response validation.

**Rationale.** Speech and language provider SDKs are Python-first, which lowers the cost of adding the STT adapter in Issue #1 without touching the service shape. FastAPI generates the OpenAPI document from the same models that enforce the contract, so the API surface Android codes against cannot silently drift from what the service validates. Async request handling fits a status endpoint that is polled while a worker runs. `uv` gives a reproducible, fast local install with a single lockfile, which is what the deterministic verification requirement needs.

**Rejected.** *Node/TypeScript* — sharing a language with `packages/contracts` is genuinely attractive, since AJV already validates the schema there, but the STT and speech ecosystem is weaker and the contract can still be enforced from Python by loading the same JSON schema file. *Kotlin/Spring Boot* — shares a language with Android, but it is the heaviest path from a standing start and no team member has an existing backend baseline in it. *Go* — good for the worker, poor for schema-driven API iteration at this team size.

## D2 — One Backend service plus one Worker process

**Decision.** A single deployable codebase with two entrypoints: the API process (HTTP, policy, orchestration, enqueue) and the Worker process (claims jobs, runs STT and AI Core calls, writes results). Both share the domain and repository layers.

**Rationale.** Job execution must not block HTTP request handling, but the two halves share every data structure. Splitting them into separate services would create a network boundary between code that is logically one module. The PRD explicitly prefers one main LLM with schema workers over a premature service split, and the same reasoning applies to the platform. Two entrypoints give the process isolation the worker needs without inventing an inter-service contract that has to be versioned.

**Rejected.** *Microservices per worker* (contract and operations cost with no Phase 1 benefit; each new boundary needs its own versioning and failure semantics). *Serverless functions* (cold starts and execution time limits are a poor fit for STT and model calls, and local verification becomes vendor-dependent).

## D3 — PostgreSQL as the system of record, behind repositories

**Decision.** PostgreSQL is the system of record for structured data: subjects, actors, consents, episodes, jobs, transcripts, and derived results. All access goes through a repository layer using SQLAlchemy 2.x. Supabase is acceptable as a **managed PostgreSQL host**, but no Supabase-specific client, RLS policy, or auto-generated API is used as the application's data access path. Local development and the test suite use SQLite through the same repository interfaces.

**Rationale.** Consent, provenance, evidence references, effective time, and model version are relational concerns; a document store would push integrity rules into application code. Postgres also keeps Phase 2 options open — `pgvector` and a temporal graph can live in the same store rather than adding a second database. Keeping Supabase at arm's length preserves the ability to move hosting without rewriting the data layer, which matters because hosting is not a product decision.

**Honest limitation.** SQLite is not PostgreSQL. Tests that pass on SQLite do not prove that a migration, a constraint, or a concurrency guarantee behaves identically in production. Mitigations: keep column types portable, avoid dialect-specific SQL in the repository layer, test repository *behavior* rather than SQL text, and document an opt-in PostgreSQL run in `services/backend/README.md` for pre-PR confidence. Any behavior that genuinely depends on Postgres (advisory locks, `pgvector`) must be behind an adapter with a documented local fallback, or excluded from the SQLite suite with a stated reason.

**Rejected.** *Supabase SDK as the data layer* — convenient, but it hides the SQL the team needs to reason about, locks the repository layer to one vendor, and cannot run in the offline test path. *Document store* — the integrity and provenance requirements are relational. *SQLite in production* — the API and Worker processes both write concurrently; SQLite's write model is not appropriate for that.

## D4 — Alembic migrations

**Decision.** One versioned migration mechanism: Alembic. Migrations must run cleanly from an empty database.

**Rationale.** Issue #8's definition of done requires a migration that runs from empty and a schema that can evolve without manual steps, and Issue #1 adds more tables on top. A versioned history is also the audit trail for a product whose core promise is traceability.

**Rejected.** *`create_all()` at import* (no version history, no safe production path, drifts silently). *Hand-written SQL scripts* (no autogenerate, ordering handled by convention). *Dashboard-only schema changes* (unreviewable, unreproducible from a clean checkout).

## D5 — Object storage behind an `ObjectStore` adapter

**Decision.** Raw audio and future media assets live in S3-compatible object storage. The database stores a reference plus object metadata (`content_type`, `size_bytes`, `checksum`, `storage_key`) and never stores audio bytes. Two implementations sit behind one adapter: local filesystem for development and tests, S3-compatible for deployment.

**Rationale.** Audio is large and append-only; it belongs in a store designed for it. Keeping the bytes out of the database keeps backups, migrations, and WAL volume proportional to structured data. The adapter is what lets the test suite run with no network and no cloud credentials.

**Rejected.** *Audio blobs in PostgreSQL* (bloats every backup and migration, wrong access pattern for large media, and it would make the Episode row heavy exactly where it must stay cheap and readable). *Local filesystem as the production store* (not durable or shareable across API and Worker hosts). *Client-direct upload* (see D6).

## D6 — Upload is one multipart request to the Backend

**Decision.** Phase 1: Android sends a single multipart request to the Backend containing the audio bytes and the Contract Capture fields. The Backend validates, writes audio to object storage, persists the Episode, enqueues the job, and returns `episodeCreated`. If the client also sends `audio_ref`, it is recorded as client-side provenance metadata describing the local recording handle and is never dereferenced server-side.

**Rationale.** The contract permits `audio_ref` to be either a local upload handle or an authorized object-storage reference; a multipart upload keeps the bytes flowing through the one component that already validates consent and idempotency, and it is the only option consistent with D10 (Android holds no storage credential). One request also means one failure surface for the client to handle rather than a two-phase handshake.

**Rejected.** *Handle-then-confirm* (two round trips and an extra orphaned-upload state for no Phase 1 benefit). *Presigned direct-to-storage* (the efficient choice at scale, but it requires the client to handle storage credentials or the Backend to operate a presigning service — revisit only if real upload sizes make multipart impractical, and only with a contract-aware proposal).

## D7 — Minimum Auth / Subject / Actor / Consent boundary

**Decision.** Three distinct records from the start:

| Record | Meaning | Notes |
| --- | --- | --- |
| `subject` | the modeled person | durable across Actor changes |
| `actor` | whoever currently operates the app | may be the subject, or later a recipient or steward |
| `consent` | a granted permission record | references the subject, the granting actor, a scope, and a status |

An Episode references `subject_id`, `actor_id`, and `recording_consent_id`. A consent record carries `consent_id`, `subject_id`, `granted_by_actor_id`, `scope`, `granted_at`, `revoked_at`, and an evidence reference. Phase 1 implements the **recording** scope and registers the **voice** scope as a value the model recognizes, so the Phase 3 boundary is closed structurally rather than by convention; the voice *pipeline* stays Phase 3. An upload boundary must **verify** that the referenced consent is granted for recording, belongs to the same subject, **and was granted by the calling actor**; a missing, revoked, or mismatched consent is an application-level validation error, not a warning.

**Phase 1 authorization.** Stated here because it is a boundary rule rather than an implementation detail: a consent may be read, used, or revoked by **only the actor that granted it**, and an Episode may be read by **only the actor that owns it**. An actor may grant a consent for an existing subject, and that grant is the only way authority over a record is acquired in Phase 1 — the subject↔actor relationship is deliberately not modeled yet. A request from any other actor is refused with the same code and status as a record that does not exist, so a response never discloses that another actor's consent or Episode exists. Phase 1 models no steward and no trusted person; those arrive with the Legacy work and will narrow this rule rather than widen it.

Phase 1 authentication is deliberately minimal: a bearer token resolved to an Actor, sufficient to attribute work correctly on the Golden Path. It is not production authentication, and it must not be presented as such.

**Rationale.** The PRD's "The User Changes, the Person Does not" is a data-model statement before it is a UI statement. Legacy handover, steward scope, and recipient access all assume this separation exists; retrofitting it later would touch every table and weaken the Legacy model. Recording consent must be *verified* rather than merely recorded, because the consent-first principle is only meaningful if an upload without consent fails.

**Rejected.** *External identity provider now* (out of Issue #8 scope and a blocker for the Golden Path; the Actor record is the seam an IdP plugs into later, so this is deferral, not debt). *A single `users` table* (conflates the operator with the modeled person). *Inventing `role`, `grant_scope`, or `legacy_state` semantics now* (Contract v0.1 explicitly keeps these as later-phase policy fields that must not be relied on in a payload).

**Deferred.** The voice pipeline (clone and TTS) that the voice scope gates, grant scope, trusted-people relations, and Legacy activation state. They reuse this structure in Phase 3/4; none are built now. The voice *scope* is registered in Phase 1 (above), so Phase 3 adds behavior rather than migrating a data model.

## D8 — Database-backed job model

**Decision.** A `jobs` table with worker leasing: `lease_owner`, `lease_expires_at`, `attempts`, `state`, `stage`, `last_error_code`. The Worker claims a job with a lease, renews it while a stage runs, and releases it when the stage ends. A stage's result is committed only if the worker still holds an **unexpired** lease for that job: the commit is an atomic compare-and-swap on `lease_owner` and `lease_expires_at`, so a lease that expires mid-stage cannot let two workers commit the same stage — the stale worker's transaction rolls back and its result is discarded rather than overwriting the new owner's. Renewing is what stops a slow stage from being executed twice at all; the compare-and-swap is what makes a duplicate commit impossible when renewal does not land. Job states map exactly to the contract's `processingStatus` enum: `uploaded → transcribing → extracting → modeling → ready | failed`. The `job_id` is internal and never appears in a contract payload.

**Rationale.** Phase 1 volume is tiny and Postgres is already present, so a durable job row is the cheapest correct queue: status, retry history, and audit are all one query away, and the status endpoint reads the same row the worker writes, so there is no second source of truth. A lease means a crashed worker does not strand an Episode — the job becomes reclaimable instead. Lease renewal and the commit-time compare-and-swap answer different halves of one hazard: renewal keeps a long stage from being executed twice, and the compare-and-swap makes a double commit impossible even when renewal fails. The second is the correctness guarantee; the first is economics, which is why both exist and why the tests cover the failure of each. It also keeps the local test path broker-free, which D14 requires.

`modeling` is a contract state that Phase 1 does not need to distinguish: when AI Core returns its result the pipeline moves through `modeling` to `ready` in one step. The state exists in the enum and the Worker passes through it rather than inventing a new sequence.

**Rejected.** *Celery / Redis / RabbitMQ / Kafka* (new infrastructure and operations for a workload that does not need them; the broker would also become the authority on job state, duplicating what the status API must expose, and it cannot run in the offline test path). *Synchronous processing inside the request* (violates the async requirement and the contract's progress model, and it makes an STT outage a failed upload). *Cron sweepers only* (no progress, no lease, no per-attempt history).

**Revisit when.** Sustained queue depth or job latency makes polling inefficient. That threshold should be recorded before a broker is introduced, not assumed.

## D9 — Named provider boundaries

Three adapters, named now, implemented on their own schedule:

**`STTAdapter` — Phase 1.** `transcribe(audio: bytes, content_type: str) -> Transcript{text, backend, model_version}`. Two implementations sit behind the boundary: a deterministic fake for development and tests, and a configurable HTTP adapter for a real provider, so selecting a provider is configuration rather than code. The boundary takes the audio bytes rather than a storage reference, because the Worker already holds the audio and a reference would let the adapter reach the object store on its own. Per-segment output and language selection are not Phase 1 needs; they arrive with the provider decision. Provider credentials stay server-side and must never appear in a contract payload.

**Where the fake may run.** The fake STT and AI providers are **refused at startup** outside `development` and `test`, so no deployment can silently record placeholder transcripts or placeholder memories — and because the fake is the *default* for both backends, a deployment that forgets to configure a provider fails to start rather than producing a record that looks real. An integration environment therefore **names its real transports** (`REMEMBER_STT_BACKEND=http`, `REMEMBER_AI_BACKEND=http`), which is what lets it be brought up and verified while no vendor is selected: attaching a provider is configuration, not code, so the environment does not wait on the provider decision to exist. The one remaining case is booting an environment *before* its provider is reachable: `REMEMBER_ALLOW_FAKE_PROVIDERS=true` builds the fakes instead and logs a warning naming the environment at startup, which is also visible in every subsequent log line. That is a deliberate escape hatch with a visible cost rather than a silent fallback — the record it produces contains placeholder text labelled as a placeholder, so it supports a startup check and cannot support an acceptance run.

**`AICoreClient` — Phase 1.** Sends `aiCoreInput` (episode id, subject id, transcript, `existing_model_version`, `trace_id`) and returns `aiCoreOutput`. The boundary **is** the contract message, not a private shape, so the transport can change without a semantic change: Phase 1 ships a deterministic fake and a configurable HTTP client, and an in-process callable remains a valid swap because the contract message is what crosses either transport. Backend does **not** decide extraction depth, prompt design, or person-model semantics — those belong to the AI Core owner.

**`VoiceProviderAdapter` — Phase 3, named only.** Clone and TTS behind one boundary, reachable only through the Backend, gated by independent voice consent. Not implemented in Phase 1; `provider_metadata` in `voiceResponse` stays non-normative as the contract states.

**Rejected.** *Calling a vendor SDK directly from the API or Worker layer* (a provider swap would become a rewrite, and vendor-specific errors would leak into client-visible status semantics). *Backend implementing Person Model logic* (out of module ownership, and it would fork the AI Core owner's schema).

## D10 — Client security rule

**Decision.** Android holds **no** provider secret, **no** database credential, **no** object-storage credential, and **no** privileged backend credential. It authenticates as an Actor with a scoped token, calls only the Backend HTTP contract, never resolves an `audio_ref` against storage directly, and receives only status, results, and playable audio. Every external provider is reached through the Backend.

**Rationale.** Anything shipped in an APK is extractable, so the only durable rule is that the client never needs the credential. It also keeps the adapter rule honest: if Android cannot reach a provider, providers cannot leak into the client contract.

**Rejected.** *Any cloud key in the app.* *Presigned storage URLs as the Phase 1 upload or playback path* (same exposure class; playback through the Backend is acceptable at Phase 1 scale).

## D11 — Failure model: the Episode is the evidence base

**Decision.** The order is fixed:

```
receive → validate Contract fields + verify consent → write audio to object storage
        → persist Episode → enqueue job → respond
```

STT and AI Core run **only after the Episode row exists**. Any downstream failure marks the job and Episode `failed` with a stable `error_code` and a human-readable `error_message`, and leaves the raw Episode **and** the raw audio readable. Failure never deletes derived or source data as a side effect.

Derived data — transcript, memory items, future persona and graph updates — is disposable and recomputable. The Episode is not. A `failed` Episode is retryable with the same idempotency key, and a retry must not create a second Episode or a second audio object.

**Ordering, and the one window it opens.** The audio object is written before the Episode transaction commits, because the Episode row must be able to reference an object that already exists — a durable row whose audio never landed would be the worse failure of the two. That leaves exactly one window: a request that has written its object and then fails to commit — a duplicate `idempotency_key` losing a race, or a database error — holds an object that no Episode will ever reference. The failing request removes that object as part of failing. The removal is best-effort: if it also fails, the result is an unreferenced object rather than a damaged record, because no Episode is left missing its audio and nothing points at the orphan. The distinction that matters: this removes a write belonging to **no record**, which is not the same act as deleting an Episode's audio to tidy up an error state. This decision forbids the second; the paragraph above specifies the first.

Contract states may not be extended: failure is `failed` plus an error code, never a new status. The `failed` state is reached atomically with the error fields so a client can never observe `failed` with no reason.

**Backend-owned error codes** (carried in the contract's free-string `error_code` field, so adding one is not a contract change; renaming one that Android branches on is a compatibility concern and must be disclosed):

| Area | Codes |
| --- | --- |
| Request / internal | `REQUEST_INVALID`, `INTERNAL` |
| Auth / identity | `AUTH_REQUIRED`, `AUTH_INVALID`, `ACTOR_NOT_FOUND`, `SUBJECT_NOT_FOUND` |
| Consent | `CONSENT_REQUIRED`, `CONSENT_INVALID`, `CONSENT_NOT_FOUND` |
| Audio | `AUDIO_INVALID`, `AUDIO_TOO_LARGE`, `AUDIO_UNAVAILABLE` |
| Object store | `STORAGE_UNAVAILABLE` |
| Episode lookup | `EPISODE_NOT_FOUND`, `EPISODE_NOT_READY` |
| Idempotency | `IDEMPOTENCY_CONFLICT` |
| STT | `STT_UNAVAILABLE`, `STT_FAILED`, `STT_TIMEOUT`, `STT_EMPTY_TRANSCRIPT` |
| AI Core | `AI_UNAVAILABLE`, `AI_FAILED`, `AI_TIMEOUT`, `AI_SCHEMA_INVALID` |

**Retryable, as part of the taxonomy rather than a per-call decision:** `STORAGE_UNAVAILABLE`, `AUDIO_UNAVAILABLE`, `STT_UNAVAILABLE`, `STT_TIMEOUT`, `AI_UNAVAILABLE`, `AI_TIMEOUT`. These describe something that was temporarily unavailable, so the stage's retry budget applies. `INTERNAL` is retryable too, and for a different reason: a stage that raised something outside this taxonomy is far more often a transient infrastructure fault than a deterministic refusal, and the budget bounds it, so a stage that dies on a real bug converges on `failed` rather than looping. Every other code is terminal for that stage: the same input would produce the same answer, and retrying it would spend the budget on a certainty. Whether a code is retryable is a property of the code, so the Worker reads it rather than deciding it.

**One disclosure for Android:** `CONSENT_NOT_FOUND` and `EPISODE_NOT_FOUND` also carry the Phase 1 cross-actor refusal (D7), so a client may see them for a record that exists but belongs to another actor. A client's handling does not change — the record is not available to this actor either way — but the codes must not be read as proof that no such record exists anywhere.

**Rationale.** This is the issue's stated principle and the PRD's: a downstream model outage is an inconvenience, a lost life record is not. Ordering the writes this way makes the guarantee structural rather than aspirational — there is no code path in which AI work begins before the Episode is committed.

**Rejected.** *Process-first* (a crash or an outage after STT would lose the recording). *Cleanup-on-failure* (deleting the Episode, or the audio a committed Episode references, to "tidy up" an error state is exactly the destructive behavior the principle forbids; removing a write that no Episode ever referenced is a different act, specified above).

## D12 — Idempotency

**Decision.** `idempotency_key` is required in practice at the real upload boundary even though the schema leaves it optional for fixture compatibility. Uniqueness is scoped to `(subject_id, actor_id, idempotency_key)`. A repeated upload returns the existing `episode_id` and upload status, and does not re-run STT or AI, create a second Episode, or store a second audio object. A reused key with a materially different body is rejected with a stable error rather than silently overwriting the original.

**Rationale.** Android must be able to retry an upload after a flaky network without doubting whether it created a duplicate. Scoping by subject and actor keeps one client's key from colliding with another's, and rejecting a mismatched body prevents the retry path from becoming a silent mutation path.

**Rejected.** *Content-hash dedup only* (two deliberate recordings of the same words are legitimately two Episodes — a real life record cannot dedupe on content). *Client-generated `episode_id`* (the contract gives Backend ownership of that identifier; letting a client mint domain identifiers invites collisions and makes idempotency harder to reason about, not easier).

## D13 — Observability

**Decision.** Structured JSON logs carrying `trace_id`, `episode_id`, internal job id, state transitions, durations, adapter provider and `model_version`, and `error_code`. `trace_id` is generated at the request boundary and propagated into `aiCoreInput`; AI Core preserves it in its own context and logs. `model_version` is persisted on results as the contract requires.

`episode_id` and the internal job id appear as **log fields only**, never as payload fields beyond what the contract defines. `trace_id` is an infrastructure correlation identifier; Android must not depend on it as a product identifier.

**Every process that handles an Episode logs under its trace id, not only the API.** The Worker adopts the Episode's own trace id for the duration of a stage, so a completed stage, a failed stage, and a crashed stage are written with the identifier the status endpoint returns to the client. That is what makes a client-reported `episode_id` sufficient to find the work in the Worker's log; without it, the person debugging has to resolve an `episode_id` to the internal job id in the database before they can read the Worker's output, which is a lookup rather than a log field. The Worker logs one line per stage with its duration and the version that produced it, so a healthy run is legible and not only a failing one.

**Rationale.** The Golden Path's failure modes are mostly asynchronous, so the only practical debugging path is correlating a client-visible status with a worker run. Generating `trace_id` at the boundary is what makes that correlation possible, and it is what Contract v0.1.1 assigns to Backend.

**Rejected.** *Free-text logs* (nothing is queryable, and the same failure would read differently in the API and the Worker). *Writing `job_id` into a contract payload so a client can correlate directly* (`job_id` is internal and its lifetime is the queue's, not the product's; `episode_id` is the client's identifier and the status endpoint already carries the trace). *Shipping logs to a collector or a tracing backend* (that is a provider decision Phase 1 does not authorize, and it consumes this baseline rather than replacing it — see the open items).

## D14 — Local verification and determinism

**Decision.** The module's deterministic command is:

```bash
cd services/backend && uv run pytest
```

It runs against SQLite, the local-filesystem object store, and fake STT / AI Core adapters. It must complete with no Docker, no PostgreSQL, and no network access. Real provider and PostgreSQL runs are opt-in through environment configuration. This command is added to `services/backend/README.md` by the first implementation Pull Request (#8), as the Phase 1 kickoff requires.

**Rationale.** The development machine has neither Docker nor PostgreSQL. Making the default check dependency-free helps distinguish product failures from environment failures without making a passing result a merge condition.

**Rejected.** *A Docker-only default check* (would be unavailable on this development machine). *Skipped or no-op checks presented as passing evidence* (they do not verify behavior).

**CI.** `.github/workflows/services-ci.placeholder.yml.disabled` stays disabled until there is real source code and this real command. It is renamed and enabled with the first implementation PR, and it must never contain a no-op job.

## Contract conformance (binding on the implementation)

These are obligations of the implementation, not contract changes:

- Use contract enums exactly. No new processing states, no new `upload_status` values, no new evidence or memory types.
- Every shape is `additionalProperties: false`. Extensions use the `metadata` / `context` extension points already in the contract; new top-level fields require a Contract Change Proposal.
- `job_id` is never serialized outward. `processingStatus` exposes `episode_id`, `status`, optional `progress`, optional `error_code` / `error_message`, and optional `trace_id`.
- `episodeResult` is only ever served in its `ready` shape (the contract fixes `status` to the constant `ready`). Before that, the status endpoint is the answer.
- `memoryItem` requires `memory_type`, `content`, `source_type`, `evidence_ids`, `confidence`, `model_version`, `prompt_version`, and `schema_version`. Nothing is persisted before validation; an AI payload that fails it is a job failure (`AI_SCHEMA_INVALID`), never a partial write.
- Backend generates `episode_id` and `trace_id` and never mutates an AI Core value. AI Core must not generate or mutate `episode_id`.
- Confidence values are in the inclusive range 0–1.

## Consequences

**Positive.** Phase 1 can be built and verified with zero external providers and zero containers. The Episode-first ordering makes the product's central safety promise structural. The provider boundaries mean selecting STT, LLM, or Voice later is configuration plus one adapter, not a redesign. Subject/Actor separation exists before any Legacy work needs it.

**Negative and accepted.** A database-backed queue is not a long-term high-volume answer; it is the right Phase 1 answer and there is a named revisit trigger. SQLite-based tests do not prove PostgreSQL behavior, which is mitigated but not eliminated and is stated rather than hidden. Minimal Phase 1 authentication must never be mistaken for production auth — it is a seam, not a solution. Using Supabase only as managed PostgreSQL forfeits the vendor's convenience features by choice.

## Non-goals

Selecting the STT, LLM, or Voice provider. Implementing any Phase 2–4 endpoint (Twin, Memory, Graph, Persona, voice). Microservice decomposition. Changing the Integration Contract — contract changes go through a Contract Change Proposal and Product/Integration approval. Production identity-provider integration, RLS hardening, HA, or multi-region. Defining retention, export, and cascade-deletion semantics (Phase 2 owns derived-data correctness; the Episode-first rule here is the constraint those semantics must respect).

## Open items carried forward

- STT provider selection. The adapter boundary and a configurable HTTP adapter exist, so the decision is a URL, a credential, and a response mapping — not code.
- LLM provider and where AI Core runs: in-process callable versus HTTP service (the contract message is the boundary either way).
- Voice pipeline design (Phase 3, requires its own decision). The voice consent scope it is gated by is registered in Phase 1.
- Trusted people, grant scope, and Legacy activation policy (Phase 4). Phase 1 authorization is narrow by construction, so this work widens access rather than repairing it.

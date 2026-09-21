# Backend Service

Owner: 王昊宇 (`qingtian-4`). Phase 1 — COMMITTED. See the [task brief](../../docs/team/03_WANGHAOYU_BACKEND_VOICE.md).

This directory will contain the API, PostgreSQL or equivalent persistence, object storage, auth, consent, asynchronous jobs, audit, and subject isolation. No backend implementation has been selected or claimed complete.

Platform decisions — language and framework, data layer, migrations, object storage, upload transport, auth boundary, job model, provider adapters, client security, failure model, idempotency, observability, and the local verification command — are recorded in [ADR-0001](../../docs/architecture/backend-adr.md). Issue #8 implements the foundation it describes; no further platform decision should be invented outside it.

Phase 1 scope: audio upload, Episode persistence, object storage, STT plumbing, processing job and status, the minimum Auth/Subject/Actor/Consent structure, and a status and result API Android can consume. An Episode must be persisted before AI runs, so a downstream failure cannot lose the original record.

Inputs and outputs must conform to `packages/contracts`.

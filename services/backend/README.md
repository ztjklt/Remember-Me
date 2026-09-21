# Backend Service

Owner: 王昊宇 (`qingtian-4`). Phase 1 — COMMITTED. See the [task brief](../../docs/team/03_WANGHAOYU_BACKEND_VOICE.md).

This directory will contain the API, PostgreSQL or equivalent persistence, object storage, auth, consent, asynchronous jobs, audit, and subject isolation. No backend implementation has been selected or claimed complete.

Phase 1 scope: audio upload, Episode persistence, object storage, STT plumbing, processing job and status, the minimum Auth/Subject/Actor/Consent structure, and a status and result API Android can consume. An Episode must be persisted before AI runs, so a downstream failure cannot lose the original record.

Inputs and outputs must conform to `packages/contracts`.

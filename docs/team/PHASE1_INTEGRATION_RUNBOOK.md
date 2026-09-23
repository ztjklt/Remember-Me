# Phase 1 fixture integration runbook

Owner: Product / Integration (`@ztjklt`). Tracks Issue #14. This checks wiring
on `develop`; it does not satisfy the real-device Phase 1 exit gate.

## Run the cross-service check

Install `uv` and use Python 3.12 or newer. From a checkout containing the
Backend and AI Core services:

```bash
cd services/backend
uv run --locked python ../../scripts/verify_phase1_fixture.py
```

The script starts AI Core's HTTP fixture provider and the Backend API/worker,
applies migrations to a temporary SQLite database, seeds a local Actor, Subject,
and RECORDING consent, and uploads a deterministic audio sample. It asserts
that repeating the upload returns the same `episode_id`, then polls for a ready
Episode and reads the persisted fixture Memory. All data and local credentials
are discarded at exit. The script prints status codes and the fixture model
version, never the Actor token or transcript.

Expected after Backend Issue #48 is fixed:

```text
upload=201 duplicate=200 episode=ready result=200 error=none
model=fixture-ai-v2 memories=1 (fixture wiring only)
```

## Current result (2026-09-23)

On merged Backend PR #42 and AI Core PR #45, the check currently reports:

```text
upload=201 duplicate=200 episode=failed result=409 error=AI_FAILED
RuntimeError: Fixture Golden Path did not reach a readable Memory
```

AI Core refuses the request with HTTP 422: Backend sends an absent optional
`subject_context` as JSON `null`, while Contract v0.1 permits that field to be
omitted but does not permit null. The module fix is [Issue #48](https://github.com/ztjklt/Remember-Me/issues/48).
AI Core HTTP 503/504 currently becomes a terminal `AI_FAILED` in Backend;
transient error mapping and retry coverage are [Issue #47](https://github.com/ztjklt/Remember-Me/issues/47).

As a diagnostic only, a temporary local forwarding proxy omitted null fields
without changing either module. The same upload then reached `ready` and the
result API returned HTTP 200 with one `fixture-ai-v2` Memory. This isolates the
first integration blocker; the repository check intentionally does not hide it.

## Phase 1 gate still to verify

- Android Issue #6: real-device recording, consent, persistent audio and local
  owner verification; draft integration PR #46 only proves CI build and tests.
- Android Issue #7: upload, status/error handling, and a real Memory rendered on
  the device from the Backend result for the same `episode_id`.
- AI Core Issues #4/#2/#5: representative long/messy transcript fixtures and
  evidence-backed extraction with an actual provider and provenance checks.
- Backend Issues #47/#48: actual AI Core HTTP happy path and bounded transient
  failure handling. A real STT provider must also replace fake STT for gate
  acceptance; provider choice remains open behind its adapter.
- Product / Integration Issue #21: record the real-device path and then make
  the Phase 1 gate decision. Phase 2 remains planned until that decision.

The check here covers only the fixture-backed cross-service subset of Issue
#14. Issue #14 additionally needs Android to render the Backend result on
`develop`; a green script alone does not close that Issue.

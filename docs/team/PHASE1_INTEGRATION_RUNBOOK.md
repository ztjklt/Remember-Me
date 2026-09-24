# Phase 1 integration runbook

Owner: Product / Integration (`@ztjklt`). Tracks Issues #14 and #21. The
fixture check verifies wiring on `develop`; the live check verifies the service
path. Neither alone satisfies the real-device Phase 1 exit gate.

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

Expected after Backend Issues #48 and #47 are integrated:

```text
upload=201 duplicate=200 episode=ready result=200 error=none
model=fixture-ai-v2 memories=1 (fixture wiring only)
```

## Latest candidate verification (2026-09-25)

On `develop` commit `03720d8`, temporarily cherry-pick the exact Backend PR
commits [#53](https://github.com/ztjklt/Remember-Me/pull/53) (`01f94de`)
and [#54](https://github.com/ztjklt/Remember-Me/pull/54) (`2eb9848`) in that
order, then copy this script unchanged into the disposable checkout and run
the command above. The result was:

```text
upload=201 duplicate=200 episode=ready result=200 error=none
model=fixture-ai-v2 memories=1 (fixture wiring only)
```

This verifies the candidate integration, including the same Episode ID on
replay and a persisted fixture Memory. The fixes are still open PRs, so this
is not a passing result on merged `develop`. Rerun the unchanged script after
#53 and #54 merge before treating Issue #14's fixture path as integrated.

## Full PR-stack candidate verification (2026-09-25)

In a disposable worktree starting at `develop` `03720d8`, merge these exact
heads in order: #53 `01f94de`, #54 `2eb9848`, #46 `46d777e`, #59 `04ac595`,
#61 `c35ede0`, #49 `c85a6bf`, and the documentation PR #52 `04380bb`.
All seven merged locally without conflicts. This is a composition test, not a
merge into the protected `develop` branch.

| Check on the combined tree | Result |
| --- | --- |
| Backend `uv run --locked pytest -q` | Passed |
| AI Core `uv run --locked pytest -q` | 119 passed |
| Contract `npm ci && npm test` | 7 passed |
| `verify_phase1_fixture.py` | `upload=201 duplicate=200 episode=ready result=200 error=none`; one fixture Memory |
| `test_verify_phase1_live.py` | 5 passed |
| Android `./gradlew --no-daemon test assembleDebug compileDebugAndroidTestKotlin` | Build successful |

The Android build used JDK 17 and Android SDK 35. Instrumentation tests were
compiled but not executed in this worktree because no emulator or physical
device was connected. Real STT, real AI extraction, and real-device capture
were not exercised. After the individual PRs pass their required reviews and
merge, repeat these checks on the actual `develop` head; the candidate cannot
stand in for that result or the Phase 1 gate.

## Original failure (2026-09-23)

On merged Backend PR #42 and AI Core PR #45, the check reported:

```text
upload=201 duplicate=200 episode=failed result=409 error=AI_FAILED
RuntimeError: Fixture Golden Path did not reach a readable Memory
```

AI Core refuses the request with HTTP 422: Backend sends an absent optional
`subject_context` as JSON `null`, while Contract v0.1 permits that field to be
omitted but does not permit null. The module fix is [Issue #48](https://github.com/ztjklt/Remember-Me/issues/48).
At that point AI Core HTTP 503/504 also became a terminal `AI_FAILED` in
Backend; [Issue #47](https://github.com/ztjklt/Remember-Me/issues/47) tracks
the transient error mapping and retry coverage now proposed in PR #54.

As a diagnostic only, a temporary local forwarding proxy omitted null fields
without changing either module. The same upload then reached `ready` and the
result API returned HTTP 200 with one `fixture-ai-v2` Memory. This isolates the
first integration blocker; the repository check intentionally does not hide it.

## Verify the real service path

When Backend #53/#54 are integrated and the module owners have configured a
real HTTP STT service and AI Core's non-fixture provider, use a consented,
representative audio recording. Start the Backend API, worker, STT service, and
AI Core; apply the Backend migrations and create an Actor, Subject, and active
RECORDING consent for that Actor. Use the same Backend database URL as the
running worker. Set these environment variables in the local shell or a secret
manager, without committing their values:

| Variable | Value |
| --- | --- |
| `PHASE1_BACKEND_URL` | Reachable Backend API base URL |
| `PHASE1_ACTOR_TOKEN` | Token of the Actor who granted RECORDING consent |
| `PHASE1_SUBJECT_ID` | Subject being recorded |
| `PHASE1_RECORDING_CONSENT_ID` | That Actor's active RECORDING consent ID |
| `PHASE1_AUDIO_PATH` | Path to the real `.m4a`, `.wav`, or other recognized audio file |
| `PHASE1_RECORDED_AT` | Actual capture time in RFC 3339 form with UTC offset |
| `PHASE1_DATABASE_URL` | Backend database URL for readback verification |
| `PHASE1_TIMEOUT_SECONDS` | Optional processing deadline; default 180 |

From the repository checkout:

```bash
cd services/backend
uv run --locked python ../../scripts/verify_phase1_live.py
uv run --locked python ../../scripts/test_verify_phase1_live.py
```

This creates a new Episode with a unique idempotency key, polls until ready,
validates the typed result, and reads the persisted Episode, Memory, and
Evidence. It checks the uploaded file's checksum and size, recording consent,
Subject isolation, STT transcript and model version, and exact Memory row
contents. Fake STT and fixture AI results fail the check. The output contains
only the Episode ID, status, row count, and provider model versions; it does
not print the token, transcript, Memory contents, or database URL. A failed
run may leave an Episode for diagnosis. Record the command, its safe output,
the tested provider configuration and service revisions in Issue #21.

This verifies the service path from real audio to persisted Memory. Complete
the separate real Android device check with the same `episode_id`: record,
pause/resume, save, re-enter, play the full audio, upload, and show the real
Memory returned by Backend. Capture the device and API evidence in Issue #21
before declaring the Phase 1 gate complete.

## Phase 1 gate still to verify

- Android Issue #6: real-device recording, consent, persistent audio and local
  verification. Draft PR #46 now includes lifecycle fix #60 and a passing
  emulator suite; physical capture and full playback remain unverified.
- Android Issue #7: upload, status/error handling, and a real Memory rendered on
  the device from the Backend result for the same `episode_id`. Draft stacked
  PR #59 has passing local and CI tests, but not physical-device acceptance.
- AI Core Issues #4/#2/#5: representative long/messy transcript fixtures and
  evidence-backed extraction with an actual provider and provenance checks.
- Backend Issues #47/#48: actual AI Core HTTP happy path and bounded transient
  failure handling. A real STT provider must also replace fake STT for gate
  acceptance; provider choice remains open behind its adapter.
- Product / Integration Issue #21: record the real-device path and then make
  the Phase 1 gate decision. Phase 2 remains planned until that decision.

The fixture check covers only the cross-service subset of Issue #14. Issue #14
additionally needs Android to render the Backend result on `develop`; passing
either script alone does not close that Issue.

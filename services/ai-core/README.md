# AI Core Service

Owner: 康欣 (`centraler`). Phase 1 — COMMITTED. See the [task brief](../../docs/team/02_KANGXIN_AI_CORE.md).

This directory contains the Phase 1 boundary for schema-validated memory extraction. Temporal graph and person model updates, evidence-backed Twin responses, calibration, and capture planning remain future work. The domain layer stays provider-neutral; the real HTTP adapter is OpenAI-compatible but does not select a vendor.

Phase 1 scope: the Episode/Transcript → Memory Extractor schema, structured output that is validated before persistence, preserved provenance fields, and a minimum AI processing interface callable by Backend with deterministic fixtures.

Inputs and outputs must conform to `packages/contracts`.

## Local verification

From this directory:

```powershell
uv run pytest -q
```

The checked-in fixtures under `fixtures/` are input-only, deterministic, and
contain no provider credentials or expected provider output.

## HTTP boundary

Run the service locally with the deterministic provider:

```powershell
$env:REMEMBER_ENVIRONMENT = "development"
$env:AI_PROVIDER = "fixture"
uv run uvicorn app.main:app --port 8100
```

The service exposes:

- `GET /health` for provider-neutral liveness;
- `POST /process` accepting the frozen `AICoreInput` and returning only
  `AICoreOutput`.

For a real OpenAI-compatible endpoint, set `AI_PROVIDER=openai_compatible`,
`AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`, and the version settings. Provider
secrets stay in the AI Core process environment and are never returned in an
error body. The fixture provider is refused in `staging` and `production`.

Invalid input returns `422`; provider unavailability returns `503`; provider
timeouts return `504`; invalid structured output or provenance returns `502`.
The response contains stable `error_code` values and safe messages only.

## Backend handoff

Backend owns Episode persistence, retries, processing status, and user-facing
failure state. It should call `POST /process` with `episode_id`, `subject_id`,
`transcript`, `existing_model_version`, and optional `trace_id`. AI Core never
creates or mutates `episode_id` and never writes a database. See
`docs/team/02_KANGXIN_AI_CORE_HANDOFF.md` for the complete handoff checklist.

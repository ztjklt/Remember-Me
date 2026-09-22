# AI Core Service

Owner: 康欣 (`centraler`). Phase 1 — COMMITTED. See the [task brief](../../docs/team/02_KANGXIN_AI_CORE.md).

This directory contains the Phase 1 boundary for schema-validated memory extraction. Temporal graph and person model updates, evidence-backed Twin responses, calibration, and capture planning remain future work. No AI provider or business logic is selected by the contract mirror.

Phase 1 scope: the Episode/Transcript → Memory Extractor schema, structured output that is validated before persistence, preserved provenance fields, and a minimum AI processing interface callable by Backend with deterministic fixtures.

Inputs and outputs must conform to `packages/contracts`.

## Local verification

From this directory:

```powershell
uv run pytest -q
```

The checked-in fixtures under `fixtures/` are input-only, deterministic, and
contain no provider credentials or expected provider output.

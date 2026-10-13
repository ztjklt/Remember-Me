# Contract v0.1 Field Guide

This guide explains the minimum Phase 1 boundaries. The normative types and enums are in `packages/contracts/schemas/integration-contract-v0.1.schema.json`. Phase status per contract is tracked in [`packages/contracts/README.md`](../../packages/contracts/README.md).

| Flow | Phase | Input | Output | Required behavior |
| --- | --- | --- | --- | --- |
| Capture and Episode | P1 COMMITTED | audio reference, `subject_id`, `actor_id`, recording consent, idempotency, source, timestamp, metadata | `episode_id`, upload status | Android stores locally until upload succeeds; backend creation is idempotent. |
| Processing | P1 COMMITTED | `episode_id` | state, progress, structured error | Heavy work is asynchronous. `failed` includes a stable error code where possible. |
| AI Core | P1/P2 | Episode, transcript, subject context, existing model version, optional trace | typed memory, planned graph/persona updates, evidence, new model version | Validate before persistence and preserve provenance. |
| Episode Result | P1 COMMITTED | `episode_id` | ready state, typed memories, model version, optional trace | Android reads this resource after Processing reaches `ready`. |
| Twin | P2 PLANNED | `subject_id`, query, context | answer, ORIGINAL or SIMULATION, evidence, confidence | Prefer direct original evidence; simulated answers remain explicit. |
| Voice | P3 PLANNED | subject, authorized text, voice profile, voice consent | audio reference, provider metadata, state | Reject missing or invalid independent voice consent. |
| Calibration | P3 PLANNED | question, locked Twin answer, human answer | dimension diffs, model updates, follow-up questions | The Twin answer is immutable before the human answer is accepted. |

`audio_ref` may be a local upload handle or authorized object-storage reference; it must not embed provider credentials. `metadata` and `context` are extension points, not permission to duplicate required fields under private names. Confidence values use the inclusive range 0 to 1.

`actor_id` and `recording_consent_id` are available on Capture in v0.1.2 and are mandatory by Phase 1 implementation policy. `role`, `grant_scope`, and `legacy_state` remain later-phase policy fields; see the open contract gaps in [`packages/contracts/README.md`](../../packages/contracts/README.md) before relying on them in a payload.

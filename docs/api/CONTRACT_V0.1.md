# Contract v0.1 Field Guide

This guide explains the minimum Phase 1 boundaries. The normative types and enums are in `packages/contracts/schemas/integration-contract-v0.1.schema.json`.

| Flow | Input | Output | Required behavior |
| --- | --- | --- | --- |
| Capture and Episode | audio reference, `subject_id`, source, timestamp, metadata | `episode_id`, upload status | Android stores locally until upload succeeds; backend creation is idempotent. |
| Processing | `episode_id` | state, progress, structured error | Heavy work is asynchronous. `failed` includes a stable error code where possible. |
| AI Core | Episode, transcript, subject context, existing model version | memory, graph, persona, evidence, new model version | Validate before persistence and preserve provenance. |
| Twin | `subject_id`, query, context | answer, ORIGINAL or SIMULATION, evidence, confidence | Prefer direct original evidence; simulated answers remain explicit. |
| Voice | subject, authorized text, voice profile, voice consent | audio reference, provider metadata, state | Reject missing or invalid independent voice consent. |
| Calibration | question, locked Twin answer, human answer | dimension diffs, model updates, follow-up questions | The Twin answer is immutable before the human answer is accepted. |

`audio_ref` may be a local upload handle or authorized object-storage reference; it must not embed provider credentials. `metadata` and `context` are extension points, not permission to duplicate required fields under private names. Confidence values use the inclusive range 0 to 1.


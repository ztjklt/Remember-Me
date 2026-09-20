# Integration Contract v0.1

This package is the source of truth for cross-module payloads. Version `0.1.2` freezes the minimum Phase 1 vocabulary without selecting providers or implementing unapproved business logic.

The machine-readable schema is `schemas/integration-contract-v0.1.schema.json`. Validate payloads at module boundaries. Additive optional fields may be proposed in a Pull Request; removals, renames, type changes, required-field changes, enum changes, or semantic changes are breaking and require an Issue plus Product and Integration Owner approval.

## Contract status by phase

Phase status describes when a contract is expected to be implemented. It does not change any field definition — the schema is unchanged by this table. Contracts marked Planned are **not** frozen, and their details must not be invented by a single member.

| Contract | Phase status | Input | Output |
| --- | --- | --- | --- |
| Capture / Create Episode | P1 COMMITTED | audio + subject/actor + recording consent + idempotency + source + time + metadata | `episode_id` + `upload_status` |
| Processing Status | P1 COMMITTED | `episode_id` | status + progress + error |
| AI Process | P1/P2 | `episode_id` + transcript + `existing_model_version` + optional trace | typed `memory_items[]` + planned graph/persona arrays + `evidence[]` + `model_version` |
| Episode Result | P1 COMMITTED | `episode_id` | ready state + typed `memory_items[]` + `model_version` |
| Twin Query | P2 PLANNED | `subject_id` + query + actor/policy context | answer + `response_type` + `evidence[]` + `confidence` |
| Calibration | P3 PLANNED | question + `locked_twin_answer` + `human_answer` | `dimension_diffs` + `model_updates` + `followup_questions` |
| Voice Synthesis | P3 PLANNED | `subject_id` + `authorized_text` + `voice_profile_id` + `voice_consent_id` | `audio_ref` + status + `provider_metadata` |

## Shared rules

- IDs are opaque non-empty strings. Timestamps are RFC 3339 UTC date-time strings.
- `subject_id` identifies the modeled person and is required at sensitive boundaries.
- Real Phase 1 Capture implementations must send `actor_id`, `recording_consent_id`, and `idempotency_key`. They remain optional in the v0.1 envelope only so existing fixtures and prototypes stay readable; absence at a real upload boundary is an application-level validation error.
- Processing states are `uploaded`, `transcribing`, `extracting`, `modeling`, `ready`, or `failed`.
- `trace_id` is an optional infrastructure correlation identifier on Processing Status. Backend generates and propagates it, AI Core preserves it in execution context and logs, and Android must not depend on it as a product identifier.
- `episode_id` remains the durable product-domain identifier. `job_id` is deliberately not exposed in Contract v0.1.1.
- Evidence includes a source reference, source type, and optional excerpt and confidence.
- Evidence source types distinguish `SUBJECT`, `THIRD_PARTY`, `AI_INFERENCE`, `OBJECTIVE`, and future `CALIBRATION` material. Optional span offsets locate evidence in a transcript.
- Each Memory item carries its kind, content, source type, one or more evidence identifiers, confidence, and model/prompt/schema versions. Graph and persona update depth remains Phase 2 work.
- Twin `response_type` is `ORIGINAL` only when direct source content answers the query; otherwise it is `SIMULATION`.
- Voice requests require an explicit granted voice-consent reference. Recording consent alone is insufficient.

## Approved v0.1.1 clarification

Issue #16 approved one minimum additive change: Processing Status may include an optional non-empty `trace_id`. Existing payloads remain valid, no data migration is required, and `trace_id` must not be overloaded as an Episode or Job identifier. Backend owns generation at the request boundary and propagation across workers; AI Core must not generate or mutate `episode_id`; Android may ignore `trace_id`.

## Approved v0.1.2 Phase 1 boundary correction

Issue #36 corrected the boundary before module implementations existed. It adds the missing objective evidence type, typed Memory items, optional Capture actor/consent/idempotency fields, AI trace propagation, and an Android-readable Episode Result. The new envelope fields are additive; the Memory item definition deliberately becomes strict so Backend and AI Core cannot freeze incompatible private shapes.

## Known open contract gaps

These are recorded rather than silently resolved. None may be changed without an Issue and Product and Integration Owner approval, because the schema sets `additionalProperties: false` and every one of these is a breaking change.

- **`job_id` visibility.** A Processing Job is distinct from an Episode and from an execution trace, but Phase 1 does not require Android to inspect job identity or retry history. Keep it internal to Backend until a concrete cross-module consumer requires a versioned proposal.
- **Graph, persona, Twin, and Calibration shapes are shallow.** `graph_updates`, `persona_updates`, `dimension_diffs`, `model_updates`, and `followup_questions` remain generic. Deepening them is Phase 2/3 work and requires a versioned proposal.
- **Voice Synthesis provider metadata is open-ended.** `provider_metadata` intentionally allows any properties so no provider is presumed; treat its contents as non-normative.

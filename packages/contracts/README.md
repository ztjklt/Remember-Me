# Integration Contract v0.3

Version `0.3.0` adds the approved iOS-first Twin query/answer, evidence provenance, `UNKNOWN` routing, and local Voice profile/speech status in `schemas/integration-contract-v0.3.schema.json`. It is additive: v0.1 and v0.2 schemas remain available for Android and earlier iOS consumers. The [cross-module proposal](../../docs/architecture/twin-voice-contract-proposal.md) records Product Owner authorization and the sensitive-data boundary.

Version `0.2.0` adds the iOS voice-to-Person-Model closure authorized in [Issue #75](https://github.com/ztjklt/Remember-Me/issues/75). The prior v0.1 schema is retained for existing Android fixtures. The v0.2 schema adds `IOS_MIC`, typed graph facts and person traits, a seven-domain model snapshot, and a capture question. Existing Android capture fields and values remain valid.

The Backend and AI Core use v0.2 for newly extracted memories; a memory keeps the schema version that produced it. Only evidence that resolves to an original transcript span enters AI Core output. Backend correction evidence is separately attributed to a calibration audit record.

This package is the source of truth for cross-module payloads. Version `0.1.2` remains frozen for Phase 1 consumers; versions `0.2.0` and `0.3.0` add the approved iOS capabilities without changing that older file.

The current machine-readable schema is `schemas/integration-contract-v0.3.schema.json`; v0.1 and v0.2 remain for existing consumers. Validate payloads at module boundaries. Additive optional fields may be proposed in a Pull Request; removals, renames, type changes, required-field changes, enum changes, or semantic changes require an Issue plus Product and Integration Owner approval.

## Contract status by phase

Phase status describes when a contract is expected to be implemented. It does not change any field definition — the schema is unchanged by this table. Contracts marked Planned are **not** frozen, and their details must not be invented by a single member.

| Contract | Phase status | Input | Output |
| --- | --- | --- | --- |
| Capture / Create Episode | P1 COMMITTED | audio + subject/actor + recording consent + idempotency + source + time + metadata | `episode_id` + `upload_status` |
| Processing Status | P1 COMMITTED | `episode_id` | status + progress + error |
| AI Process | P1/P2 approved slice | `episode_id` + transcript + `existing_model_version` + optional trace | typed `memory_items[]`, `graph_updates[]`, `persona_updates[]`, `evidence[]`, and `model_version` |
| Person Model Snapshot | P2 approved slice | `subject_id` | seven domains with evidence-linked traits and optional graph facts |
| Capture Question | P2 approved slice | current model gaps or contradictions | target domain, reason, evidence, and status |
| Episode Result | P1 COMMITTED | `episode_id` | ready state + typed `memory_items[]` + `model_version` |
| Twin Query | iOS-first approved slice, v0.3 | `subject_id` + reviewed query + `CLOUD_TWIN` consent | answer ID + Original/Simulation/Unknown + evidence + model/revision |
| Calibration | P3 PLANNED | question + `locked_twin_answer` + `human_answer` | `dimension_diffs` + `model_updates` + `followup_questions` |
| Voice Synthesis | local iOS-first approved slice, v0.3 | saved Twin answer ID + active `VOICE` profile/consent | private audio asset ID + status + model version |

## Shared rules

- IDs are opaque non-empty strings. Timestamps are RFC 3339 UTC date-time strings.
- `subject_id` identifies the modeled person and is required at sensitive boundaries.
- Real Phase 1 Capture implementations must send `actor_id`, `recording_consent_id`, and `idempotency_key`. They remain optional in the v0.1 envelope only so existing fixtures and prototypes stay readable; absence at a real upload boundary is an application-level validation error.
- Processing states are `uploaded`, `transcribing`, `extracting`, `modeling`, `ready`, or `failed`.
- `trace_id` is an optional infrastructure correlation identifier on Processing Status. Backend generates and propagates it, AI Core preserves it in execution context and logs, and Android must not depend on it as a product identifier.
- `episode_id` remains the durable product-domain identifier. `job_id` is deliberately not exposed in Contract v0.1.1.
- Evidence includes a source reference, source type, and optional excerpt and confidence.
- Evidence source types distinguish `SUBJECT`, `THIRD_PARTY`, `AI_INFERENCE`, `OBJECTIVE`, and `CALIBRATION` material. Optional span offsets locate transcript evidence; a correction instead points to its audit record.
- Each Memory item carries its kind, content, source type, one or more evidence identifiers, confidence, and model/prompt/schema versions. In v0.2 graph and persona proposals are typed and evidence-linked.
- In v0.3, Twin `response_type` is `ORIGINAL` only for a verified SUBJECT transcript span, `SIMULATION` for labeled inference with evidence, and `UNKNOWN` when evidence is insufficient or contradictory. v0.2's shallow two-value shape remains for old consumers.
- Voice requests require an explicit granted voice-consent reference. Recording consent alone is insufficient.

## Approved v0.1.1 clarification

Issue #16 approved one minimum additive change: Processing Status may include an optional non-empty `trace_id`. Existing payloads remain valid, no data migration is required, and `trace_id` must not be overloaded as an Episode or Job identifier. Backend owns generation at the request boundary and propagation across workers; AI Core must not generate or mutate `episode_id`; Android may ignore `trace_id`.

## Approved v0.1.2 Phase 1 boundary correction

Issue #36 corrected the boundary before module implementations existed. It adds the missing objective evidence type, typed Memory items, optional Capture actor/consent/idempotency fields, AI trace propagation, and an Android-readable Episode Result. The new envelope fields are additive; the Memory item definition deliberately becomes strict so Backend and AI Core cannot freeze incompatible private shapes.

## Known open contract gaps

These are recorded rather than silently resolved. None may be changed without an Issue and Product and Integration Owner approval, because the schema sets `additionalProperties: false` and every one of these is a breaking change.

- **`job_id` visibility.** A Processing Job is distinct from an Episode and from an execution trace, but Phase 1 does not require Android to inspect job identity or retry history. Keep it internal to Backend until a concrete cross-module consumer requires a versioned proposal.
- **Twin and Calibration shapes are shallow.** The v0.2 graph and person-trait proposals are typed. Twin, `dimension_diffs`, `model_updates`, and `followup_questions` remain later-phase work and require a versioned proposal.
- **Voice Synthesis provider metadata is open-ended.** `provider_metadata` intentionally allows any properties so no provider is presumed; treat its contents as non-normative.

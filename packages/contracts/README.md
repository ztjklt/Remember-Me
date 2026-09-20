# Integration Contract v0.1

This package is the source of truth for cross-module payloads. Version `0.1.0` freezes the minimum Phase 1 vocabulary without selecting providers or implementing unapproved business logic.

The machine-readable schema is `schemas/integration-contract-v0.1.schema.json`. Validate payloads at module boundaries. Additive optional fields may be proposed in a Pull Request; removals, renames, type changes, required-field changes, enum changes, or semantic changes are breaking and require an Issue plus Product and Integration Owner approval.

## Contract status by phase

Phase status describes when a contract is expected to be implemented. It does not change any field definition — the schema is unchanged by this table. Contracts marked Planned are **not** frozen, and their details must not be invented by a single member.

| Contract | Phase status | Input | Output |
| --- | --- | --- | --- |
| Capture / Create Episode | P1 COMMITTED | audio + `subject_id` + source + `recorded_at` + metadata | `episode_id` + `upload_status` |
| Processing Status | P1 COMMITTED | `episode_id` | status + progress + error |
| AI Process | P1/P2 | `episode_id` + transcript + `existing_model_version` | `memory_items[]` + `graph_updates[]` + `persona_updates[]` + `evidence[]` + `model_version` |
| Twin Query | P2 PLANNED | `subject_id` + query + actor/policy context | answer + `response_type` + `evidence[]` + `confidence` |
| Calibration | P3 PLANNED | question + `locked_twin_answer` + `human_answer` | `dimension_diffs` + `model_updates` + `followup_questions` |
| Voice Synthesis | P3 PLANNED | `subject_id` + `authorized_text` + `voice_profile_id` + `voice_consent_id` | `audio_ref` + status + `provider_metadata` |

## Shared rules

- IDs are opaque non-empty strings. Timestamps are RFC 3339 UTC date-time strings.
- `subject_id` identifies the modeled person and is required at sensitive boundaries.
- Processing states are `uploaded`, `transcribing`, `extracting`, `modeling`, `ready`, or `failed`.
- Evidence includes a source reference, source type, and optional excerpt and confidence.
- Twin `response_type` is `ORIGINAL` only when direct source content answers the query; otherwise it is `SIMULATION`.
- Voice requests require an explicit granted voice-consent reference. Recording consent alone is insufficient.

## Known open contract gaps

These are recorded rather than silently resolved. None may be changed without an Issue and Product and Integration Owner approval, because the schema sets `additionalProperties: false` and every one of these is a breaking change.

- **`trace_id` on Processing Status.** The engineering baseline expects cross-service calls to carry a trace id and the Backend phase-1 work depends on observability. `processingStatus` has no `trace_id` field today. Proposed resolution: add an optional `trace_id` string, which is additive but still needs approval because the object is closed.
- **Twin and Calibration shapes are shallow.** `dimension_diffs`, `model_updates`, and `followup_questions` are typed only as generic arrays or strings. Deepening them is Phase 2/3 work and requires a versioned proposal.
- **Voice Synthesis provider metadata is open-ended.** `provider_metadata` intentionally allows any properties so no provider is presumed; treat its contents as non-normative.

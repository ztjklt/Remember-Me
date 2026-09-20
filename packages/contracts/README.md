# Integration Contract v0.1

This package is the source of truth for cross-module payloads. Version `0.1.0` freezes the minimum Phase 1 vocabulary without selecting providers or implementing unapproved business logic.

The machine-readable schema is `schemas/integration-contract-v0.1.schema.json`. Validate payloads at module boundaries. Additive optional fields may be proposed in a Pull Request; removals, renames, type changes, required-field changes, enum changes, or semantic changes are breaking and require an Issue plus Product and Integration Owner approval.

## Shared rules

- IDs are opaque non-empty strings. Timestamps are RFC 3339 UTC date-time strings.
- `subject_id` identifies the modeled person and is required at sensitive boundaries.
- Processing states are `uploaded`, `transcribing`, `extracting`, `modeling`, `ready`, or `failed`.
- Evidence includes a source reference, source type, and optional excerpt and confidence.
- Twin `response_type` is `ORIGINAL` only when direct source content answers the query; otherwise it is `SIMULATION`.
- Voice requests require an explicit granted voice-consent reference. Recording consent alone is insufficient.


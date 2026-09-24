# Phase 1 fixtures (set `phase1-v1`, Contract package `0.1.2`)

These checked-in inputs are deterministic, provider-free test material for the
Episode/Transcript → Memory boundary.

- `phase1-happy.json`: a clear first-person statement about a preference and a
  near-term event.
- `phase1-messy.json`: filler words, an interruption, a time reference, and a
  relationship statement.
- `phase1-adversarial.json`: a contradiction and an explicitly uncertain
  claim. The extractor must not turn uncertainty into a confident fact.
- `phase1-long-messy.json`: a longer, fictional recollection with corrected and
  uncertain dates, changing preferences, a third party's perspective, and
  repeated self-qualification. Issues #4 and #2 use it for input and schema
  validation; Issue #14 can reuse it for cross-service fixture wiring.
- `capture/phase1-long-messy.json`: the corresponding pre-upload
  `captureEpisode` envelope for Android and Backend tests in Issues #4 and #14.
  Its `audio_ref` is a fixture-only placeholder: no audio file is included.
  Backend assigns the `episode_id` after upload, so this capture envelope does
  not invent one. The paired AI input uses a stable fixture `episode_id` to
  represent the post-upload boundary.

The top-level JSON fixtures are exactly `aiCoreInput` payloads; the nested
capture fixture is exactly a `captureEpisode` payload. Tests validate both
against the shared JSON Schema, including its date-time format. All values are
fictional, deterministic, usable offline, and contain no provider credentials
or expected model output. Provider and extractor tests own output expectations
so inputs remain reusable across providers. Existing fixture files stay stable;
add a new named fixture when a consumer needs a different scenario.

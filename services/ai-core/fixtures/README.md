# Phase 1 fixtures

These checked-in inputs are deterministic, provider-free test material for the
Episode/Transcript → Memory boundary.

- `phase1-happy.json`: a clear first-person statement about a preference and a
  near-term event.
- `phase1-messy.json`: filler words, an interruption, a time reference, and a
  relationship statement.
- `phase1-adversarial.json`: a contradiction and an explicitly uncertain
  claim. The extractor must not turn uncertainty into a confident fact.

Every fixture is exactly an `AICoreInput` payload from Contract v0.1. The
fixtures do not contain expected model output; provider and extractor tests
own those expectations so the input remains reusable across providers.

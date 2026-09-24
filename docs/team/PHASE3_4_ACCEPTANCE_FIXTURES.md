# Phase 3–4 preparatory acceptance scenarios

These synthetic scenarios are non-binding design inputs for Issues #25/#29
and #30/#34. They do not activate Phase 3 or 4, freeze a cross-module Contract,
select a Voice provider, or assert any Work 3200 SDK capability. The Phase 1
real-device gate and Phase 2 evidence gate remain prerequisites. Both files
describe observable outcomes, not wire request/response fields:

- [Phase 3 calibration and Voice](fixtures/phase3_calibration_voice.json): lock
  the Twin answer before collecting the human answer, compare five dimensions,
  carry the correction into a later answer, and test independent Voice consent,
  subject-only clean samples, authorized text, revocation, and provider failure.
- [Phase 4 hardware and Legacy](fixtures/phase4_hardware_legacy.json): keep
  phone-only Capture complete, gate hardware features on official capability
  evidence, and test scoped activation, baseline freeze, denial, revocation,
  cache invalidation, and audit.

For #25 and #30, Android, AI Core, and Backend owners should identify the
minimum IDs, versions, states, policy context, and failure fields their
boundaries need. Product approves a versioned Contract only after the prior
phase gate and those module inputs are reviewed. A synthetic fixture, a fake
Voice adapter, or a simulated device is useful for development but cannot pass
the corresponding real-provider or real-hardware acceptance gate.

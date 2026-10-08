# Legacy contract proposal

Status: PROPOSED, not approved. This proposal defines the remaining public boundary for wiring the prepared immutable baseline into Phase 4. It does not change `packages/contracts` or enable Legacy access.

## Baseline activation

Propose `POST /api/v1/subjects/{subject_id}/legacy/activation` with `handover_consent_id`, `activation_policy_id`, `activation_evidence_ref` and `idempotency_key`. Actor identity comes only from authenticated credentials. The request cannot mint consent or establish the activation policy.

Backend must verify the prior Subject-authorized handover record, the Actor's steward authority, the approved activation policy and its evidence. The exact activation policy and verification method remain a Product decision; a Recipient, Twin output or arbitrary boolean cannot activate Legacy.

Proposed result: `baseline_id`, `subject_id`, `person_model_version`, `frozen_at`, `content_fingerprint` and `status` (`pending`, `active`, `failed`). The snapshot preserves the existing seven-domain model, evidence and model versions. Activation persistence must be atomic and retries must return the same baseline. The fingerprint establishes content identity, not authorization.

## Recipient grants

Propose a typed grant with `grant_id`, `subject_id`, `recipient_actor_id`, `baseline_id`, `handover_consent_id`, `scopes`, `artifact_ids`, `granted_at` and optional `revoked_at`.

Proposed scopes are `MEMORY_READ`, `ORIGINAL_AUDIO_READ`, `TWIN_QUERY` and `VOICE_PLAYBACK`. `artifact_ids` is an explicit allowlist; an empty list authorizes no content. VOICE playback additionally requires a valid voice authorization covering the selected asset and recipient. This grant never permits cloning, arbitrary-text synthesis, training or persona edits.

The Subject authorizes these future permissions before activation; Steward execution cannot enlarge them. Denied and cross-subject requests return the existing unavailable-record semantics. Revocation invalidates relevant answer/audio caches and removes access immediately.

## Frozen model and changing context

Legacy Twin retrieval resolves only currently accessible source artifacts supporting the frozen baseline. Original/Simulation/Unknown labeling and source distinctions remain. Later world context and Recipient conversation context are separate inputs and cannot update the historical person's traits, values, voice or grants.

Source deletion/revocation must override retrieval of the frozen snapshot: mark affected dependencies inaccessible and recompute the permitted evidence view without inventing a new historical personality. Baseline versioning, revocation tombstones and cleanup retries need explicit migrations and audit records.

## Integration acceptance

1. An unauthorized Actor or missing prior handover authorization cannot activate Legacy.
2. A valid activation records one immutable baseline under repeated requests.
3. Two Recipients receive different artifact allowlists and cannot enumerate each other's content.
4. Recipient/world context leaves the baseline fingerprint unchanged.
5. Revoked/deleted source evidence is unavailable to Twin and voice readback.
6. Voice permissions cannot be derived from recording or handover consent alone.
7. No device or unconfirmed Work 3200 capability is required for the flow.

Approval requires Product and Integration Owner agreement on these shapes, the activation policy and evidence-verification method. After approval, add a versioned schema and migrations and connect the prepared baseline to Backend and client UI. Until then, the helper remains disconnected from runtime APIs.

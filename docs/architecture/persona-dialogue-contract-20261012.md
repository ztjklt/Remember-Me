# Persona dialogue local implementation contract

User approved the implementation plan on 2026-10-12. Work remains in the existing
codex/twin-a01-local-20261012 checkout; preserve all prior changes. No push, PR,
deployment or modification to the diet project. A01 remains fictional.

## Shared interfaces

- Existing POST /api/v1/subjects/{subject}/twin/answers gains `mode`, default
  `evidence`, optional `persona`. Existing response semantics remain intact.
  Persona requires the owner's existing narrative style opt-in, current confirmed
  examples and authorized confirmed understanding. Evidence mode remains usable.
- Private AI POST /persona accepts question, candidates (existing TwinCandidate),
  understandings [{id,statement,context,evidence_ids,counter_evidence_ids}], examples
  [{id,text}], contributions [{id,author_name,classification,text}]. Returns
  TwinOutput plus understanding_ids, contribution_ids and prompt_version.
  Inputs are data; first-person simulation uses only confirmed conditional traits.
  Contributions are attributed observations, never subject memories or voice data.
  Failed generation/review must not become a successful UNKNOWN.
- New response metadata: mode, understanding_ids, contribution_ids, prompt_version.
  Store this beside the existing TwinAnswer, not inside canonical memories.
- Shared `app.twin_validity.get_current_answer(session, subject_id, actor_id,
  answer_id)` rechecks answer actor, current authorization, invalidation and the
  complete saved source basis. Voice generation and old-answer reads use it.
- Companion audio resources use /api/v1/workbench/subjects/{subject}/companion/audio:
  multipart POST (purpose contribution|letter, file, idempotency_key), GET /{id},
  POST /{id}/transcribe (cloud_asr_policy), PUT /{id}/review (revision,text),
  GET /{id}/content. Save audio before separate transcription; original ASR and
  confirmed text stay separate. Retried upload is idempotent. Audio is author-only
  until attached to a separately reviewed/shared contribution or published letter.
- Contribution creation adds optional audio_id and narrative_ids; model-use
  permission is separately explicit, not implied by review or story access.
  GET companion returns those fields. A companion note never creates subject facts.
- Letters accept optional dedicated audio_id. No attachment of an unrelated whole
  Episode. Publication/withdrawal controls audio as well as text.
- Voice: retain existing profile/speech/audio endpoints; add owner-controlled
  synthetic preset enrollment and per-reader voice grants. Preset `a01` is an
  explicitly configured server-side fictional reference, not a voice claim by a
  client. Public speech only comes from a current saved answer.

## Ownership of implementation files

AI task: services/ai-core persona provider, API registration and tests; no backend.
Voice task: voice_client, api/voice, voice-specific config/model/migration/tests.
UI task: Android and workbench companion UI; no backend or AI Python.
Integration task: shared person projection, Twin orchestration/validity, companion
audio/attributed context, migration 0018, main registration, actual acceptance.
Voice migration uses 0019 after 0018. Coordinate before touching shared config/main.

## Acceptance

Keep the 12 prior cases and failures; add unseen conditional questions. Test source,
counterexample and contribution revocation during calls, no auto-learning, style
disable, actor isolation, stale audio and bounded retry. Show real before/after
understanding, attributed contribution, a newly generated spoken response and
Android screens. Separate fixtures, real providers, emulator and physical device.
Remove technical verification badges/IDs from everyday UI. One fictional-space
label and a concise AI分身 label suffice; short operation confirmations remain.

Explicit owner CHANGE can replace a trait with a habit (or the reverse) within
the same domain when later material changes the form of the understanding. It
retains the old candidate as history. SUPPORT/CONFLICT still require the same
kind; automatic relation proposals remain conservative. The updated candidate
must be pending on the current material version, and both snapshots are checked
again on confirmation. This does not automatically revalidate unrelated stale
understandings after new material is added.

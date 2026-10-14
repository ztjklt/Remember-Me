# Automatic spoken introductions in one group recording

2026-10-15 later amendment: required spoken agreement and repeated switches are superseded by [natural capture v0.11](natural-capture-contract-v0.11.md). This document records the historical first slice.

Approved direction: Product / Integration Owner request in the current chat, 2026-10-15: implement speaker identification; associate names automatically from self-introductions in the recording, without a manual “who is this” step. This updates the manual-attribution-first proposal. The first runnable slice is owner-operated, same-recording identification for two or three informed participants. Existing single-person capture, Voice cloning, Twin and Android payloads remain intact.

## Behavior and provenance

Before capture, each participant independently agrees to recording, cloud transcription and voice-based identification for this recording. The operator records that each person has agreed; each person also speaks their introduction and agreement at the start, e.g. “我是小王。我同意录音、云端转写和本次声音识别。” The current policy and recorded statement segment IDs are retained. This operator witness does not turn another participant into an account holder or authenticated Subject.

The selected ASR adapter returns sentence timing and acoustic speaker IDs. Names are extracted only from direct introductions at the beginning, linked to the same acoustic speaker's subsequent speech. A clean, explicit spoken agreement is required for the named association. Unknown voices, absent agreements, contradictory names and overlapping returned intervals keep uncertain identity. Two voices claiming the same name stay separate. A 2/3-person hint assists the provider's grouping; it does not guarantee the count. Identity means a self-described label in this recording; it is not a verified account identity and does not expand access.

No cross-record voiceprint templates or vectors are stored or exposed. No Voice clone is created. Group originals and results are kept in separate owner-scoped storage and never automatically enter Episode, Person Model, Twin RAG or Subject Voice Dataset. This preserves both the requested automatic identity flow and third-party isolation. Other providers report unsupported, preserving local audio; no silent fallback or provider freeze.

## Additive API and data

Contract v0.10 copies every v0.9 `$defs` without modification. Adds speaker recording capabilities, capture metadata, processing request, result/report/list and a dedicated SPEAKER_IDENTIFICATION grant. Capture uses multipart for a mono original plus strict metadata; the JSON Schema represents parsed form values. Caller identity is always derived from the authenticated token. No client-supplied name, account identity, speaker assignment or provider credentials are accepted as the analysis result.

Owner-only prefix: `/api/v1/subjects/{subject_id}/speaker-recordings`.

- GET `/capabilities`: adapter availability, bound policy, notice, introduction guide and `identification_scope=recording`.
- POST base: persist original and `uploaded` row before processing. Requires separate active grant, bound policy, original timestamp/duration, idempotency key and each-participant-consent witness. Optional count hint is 2 or 3.
- GET base / GET `/{recording_id}`: owner list/status/report. Results require current authorization and are not HTTP-cached.
- POST `/{recording_id}/process`: resume the same durable original. Provider tasks use distinct resumable checkpoints from ordinary single-person ASR and from different count hints. An uncertain submit acknowledgement is not replayed.
- GET `/{recording_id}/audio`: owner and current grant only.
- DELETE `/{recording_id}` / grant revocation: tombstone, clear identity/text results, block original access before remote cleanup. Failure to clean remote audio remains visible and retryable. Late provider results cannot publish after deletion/revocation/account-scope changes.

Migration 0022 adds the separate `speaker_recordings` table and registered consent scope. Job claims use compare-and-swap leases; authenticated client processing and the existing private CloudBase tick resume pending tasks. Scope and policy are rechecked around every provider wait and before publishing. Source-format, duration, text-size and returned-timestamp failures preserve the original and expose a failure state.

## What this does not claim

Self-introduction is not proof of legal identity. The provider may merge similar voices, split a voice or lose speech during simultaneous talking; returned interval-overlap checks are not a complete acoustic overlap detector. No automatic separation of mixed audio into clean individual sound tracks, persistent speaker recognition between recordings, imported-persona training or realtime multi-party Twin participation is delivered here. Real-person and noisy-room accuracy requires actual recorded trials; synthetic fixtures and preset TTS tests are engineering evidence only.

# iOS transcript review before AI extraction

Product and Integration Owner decision, 2026-09-27: after a real iPhone recording exposed Chinese STT errors, show the transcript in iOS and let the subject edit it before it is sent to the LLM. This proposal is part of the iOS Person Model slice in Issue #75 and PR #76.

Only new `IOS_MIC` Episodes pause after STT. Android and previously completed Episodes retain their current flow and contract payloads. The worker keeps the original STT text, waits for the capturing Actor to submit a nonblank confirmed transcript, then runs the existing extraction and modeling stages. No transcript is sent to DeepSeek before this confirmation.

New Actor-scoped Backend resource:

- `GET /api/v1/episodes/{episode_id}/transcript-review`: `{state: "transcribing" | "reviewing" | "submitted" | "not_required", transcript: string | null, stt_model_version: string | null}`. Only `reviewing` exposes an editable transcript; the result is private and never cached.
- `PATCH /api/v1/episodes/{episode_id}/transcript-review`: `{transcript: string}`. Valid only for an `IOS_MIC` Episode awaiting review. A retry with the same confirmed text is idempotent. Other Actors receive the same not-found response as for an unknown Episode.

The existing `ProcessingStatus` schema stays unchanged: `transcribing` includes the subject's review pause, and `extracting` begins only after confirmation. The internal Job gains a `waiting` state, not a new client status. The Episode keeps `stt_transcript` as the original machine output, `transcript` as the confirmed version, and the review Actor/time. Audio and Episode identity stay unchanged. This is an additive API proposal; no existing contract enum changes.

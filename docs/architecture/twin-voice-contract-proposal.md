# Twin and local Voice Contract proposal

Product Owner authorization: the 2026-09-27 request to implement the RM memory library, Digital Twin, and local personal voice loop. This records the cross-module decision before integration and supersedes the earlier phase hold only for this iOS-first slice. Android's v0.1/v0.2 payloads remain valid.

## v0.3 additions

- Twin query carries `subject_id`, the user-reviewed question, and a separate `CLOUD_TWIN` consent reference. Backend owns Actor authorization and sends only up to eight retrieved, active memory/evidence snippets to AI Core. Raw audio, Actor token, and Subject identity do not go to DeepSeek.
- Twin answer carries an answer ID, question, model/revision provenance, evidence IDs with source Episodes, and `ORIGINAL`, `SIMULATION`, or `UNKNOWN`. `ORIGINAL` must exactly match a SUBJECT transcript span. `SIMULATION` has cited evidence and a visible inference label. Contradiction or absent evidence may produce `UNKNOWN`. Corrections, deletions, and cloud-consent revocation invalidate old answer text and speech.
- Voice enrollment requires a separate `VOICE` consent and an explicitly confirmed, clean 5–15 second own-voice sample with reviewed text. Only the Backend may request synthesis, by saved Twin answer ID. No arbitrary text synthesis API is exposed to either mobile client. Voice revocation deletes the sample and generated audio; the consent audit remains.
- The Mac-only voice adapter uses Qwen3-TTS Base through MLX. Providers remain behind adapters and secrets remain outside clients. v0.3 adds new definitions rather than changing the existing v0.1/v0.2 fields.

This is a one-person Build Me slice. Recipient/Legacy permissions, live conversation, historical chat import, and calibration comparison are separate future work.

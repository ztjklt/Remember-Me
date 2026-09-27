# iOS-first Twin calibration Contract proposal

Product Owner authorization: the 2026-09-27 instruction to continue product work while deferring physical iPhone acceptance. This proposal records the next PRD slice before changing the shared Contract. It is stacked on PR #76 and does not change Android v0.1–v0.3 requests.

## Scope

- A Subject who has granted `CLOUD_TWIN` can lock one saved, evidence-backed Twin answer for calibration. The lock captures its question, answer, model/version, evidence IDs, and source-memory fingerprint **before** the human answer is uploaded.
- The same Subject records a new `IOS_MIC` Episode with `calibration_id` in the existing optional capture metadata. Recording consent, upload idempotency, local STT, editable transcript, Memory extraction, and Person Model update use the current path.
- Only after the human Episode is `ready` can Backend compare the immutable Twin snapshot with the confirmed human transcript. AI Core returns five typed dimensions: decision, reasoning, value priority, emotional reaction, expression. Each note cites a literal excerpt from the human transcript or says it was not observed. The result and actual model version are saved; a proposed next question may guide another capture.
- The calibration result is a diagnostic, not a new statement by the Subject. The human Episode is the only new source of Memory. It cannot rewrite a trait by itself. If the locked source memory is corrected or deleted before comparison, the calibration becomes stale and requires a new Twin answer.
- Backend verifies Subject/Actor, both consent scopes, the linked Episode, answer order, source fingerprint, and model output. Old contract versions and Android automation remain valid. This slice does not require another phone test now.

This is a bounded Phase 3 calibration slice; unattended voice enrollment, recipient accounts, Legacy, and full fatigue-based Capture Planner remain outside it.

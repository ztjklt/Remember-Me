# Recorder Home Capture Implementation Plan

> **For agentic workers:** Execute with superpowers:executing-plans; the user authorized direct implementation and autonomous routine decisions. Do not add another plan approval gate.

**Goal:** Make the recorder's physical recording lifecycle, saved audio, markers and transcription usable from Today.
**Architecture:** A scoped shared controller owns SDK events independently of composition. A connectedDevice foreground service protects the active session; a pure timeline controls recording/end-file identity and a durable journal feeds existing LocalCapture ingestion.
**Tech Stack:** Kotlin/Compose, Soundcore 1.3.02 Java bridge, Android API 26–35, existing HTTPS backend.
**Spec:** ../specs/2026-10-16-work3200-home-capture-design.md

## Global Constraints
- Preserve account/subject isolation, original files, stable upload keys and explicit upload consent.
- Device start/stop uses physical controls; never request phone microphone in device mode.
- Actual transport percentage, stage-only cloud processing; no invented completion percentage.
- Keep private vendor archive and signing material outside Git. Deliver same-signature internal APK.
- No physical test claims from synthetic audio or emulator evidence.

## Review Focus
- Late end events from a previous recording cannot stop or download the new one (task 1).
- Switching tabs/rotation must not dispose the SDK, but switching identity must (task 2).
- Missing file-list item after stop waits/retries without importing another file (task 2).
- Markers arriving before/after file receipt persist under the correct device/account (task 1/2).
- Uploaded hardware audio remains playable after restart without changing its upload identity (task 3).

### Task 1: Recording timeline and durable markers
Files: hardware/RecorderTimeline.kt, Work3200ImportJournal.kt, test/hardware/RecorderTimelineTest.kt and Work3200ImportTest.kt.
Interfaces: `RecorderTimeline.status(status, durationMs, fileId)`, `duration(ms)`, `elapsedMs()`, `pendingFiles`, `completed(id)`, `mark(offset, origin)`, `disconnected()`; journal `saveMarkers(scope, deviceKey, fileId, marks)` / `markers(scope, deviceKey, fileId)`.
- [x] Write/run failing timeline and marker persistence tests including duplicate/old callbacks and scope isolation.
- [x] Implement pure state/monotonic time and atomic scoped marker files; uploaded prepared audio is reusable.
- [x] Run Android unit suite; record exact evidence and commit.

### Task 2: Shared session, SDK events and automatic file completion
Files: HardwareTransport.kt, Soundcore1302Bridge.java, Work3200Controller.kt, RecorderConnectionService.kt, NativeWorkbenchModel.kt, Work3200Screen.kt, AndroidManifest.xml.
Interfaces: HardwareEvents adds recording/status/duration, binding broadcast and device-recording snapshot; HardwareTransport adds info refresh and realtime acquisition. NativeWorkbenchModel `recorder(): Work3200Controller` reuses identity-scoped instance. Controller exposes StateFlow with capture/markers/percent and prepared callbacks.
- [x] Add instrumentation regression tests using injectable transport at the external SDK boundary; verify panel disposal, stopped-file identity and unstarted realtime handling.
- [x] Route SDK events, readable binding timeout, session ownership, foreground service and activity-independent connection.
- [x] End queues exact file ID, bounded list retry, serial download/verify/decode, raw preservation and marker merge; recoverable file errors preserve connection.
- [x] Verify fake-device lifecycle and genuine SDK initialization; commit.

### Task 3: Home and existing upload integration
Files: RecorderHomeCard.kt, TodayStoryScreen.kt, NativeWorkbenchScreen.kt, NativeWorkbenchModel.kt, CaptureSubmission.kt, BackendClient.kt, DeviceOpusDecoder.kt.
Interfaces: prepared audio callback yields `(HardwareDownloadReceipt, HardwareUploadCandidate)` into scoped native capture; saved source `WORK_3200`; HTTP upload has byte-progress callback.
- [x] Test prepared-file idempotency/persistence across new login sessions, upload progress and UI source selection.
- [x] Add recorder/phone choice, live card, local/device file lists, marker seek, preparation progress and existing consent/upload/review on Today (also simple mode).
- [x] Preserve source and original journal; successful upload links journal episode; uploaded WAV stays playable.
- [x] Run unit/UI checks and existing phone-capture regressions; commit.

### Task 4: Review, signed build and delivery
Files: build version, docs/agent-loop dated handoff, private delivery directory.
- [x] Run full relevant Android suite, signed build, SDK-enabled and optional no-SDK compile; inspect emulator screenshots and final APK behavior.
- [x] Fresh whole-change reviewer per executing-plans skill; fix material findings with regression checks.
- [x] Verify WORK_3200 upload/review with labeled test material using existing test account where available; never equate to physical acceptance.
- [x] Same-signature local APK, SHA256 and concise physical runbook; record limitations and checks. Private LAN server launch was blocked by automatic approval review; no new URL claimed.

## Execution ledger
- Start: baseline 3c81943; existing feature branch and working checkout reused. User approved design and autonomous execution.
- Ruling: use this durable ledger instead of shell-specific SDD helper scripts on Windows; preserve all logs under D:/JOB/hack/delivery/work3200-home-validation. No separate implementation agents; one final reviewer only.
- Preflight: task 1 timeline consumed by task 2; task 2 prepared callback consumed by task 3; task 3 reuses existing server WORK_3200 contract. No new required wire fields.
- Completed source: 0e1880e, ec9d89a, ffa1964. Final 130 unit tests and 8 signed-APK instrumentation tests passed; optional no-SDK compile passed. Actual cloud synthetic 88.34-second audio reached ready after explicit review; MediaPlayer marker seek passed. Fresh reviewer found three defects, all fixed and checked, including requested-vs-active transfer distinction.
- Delivery and evidence: ../../agent-loop/2026-10-16-work3200-home-delivery.md. Desktop APK 0.14.0 is available; new temporary LAN service blocked by automatic approval review. Physical vivo/recorder callback, real audio quality, device marker timing and screen-off acceptance remain user-side checks; no physical completion claim.

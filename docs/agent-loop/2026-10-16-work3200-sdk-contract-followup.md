# 0.14.1 SDK contract follow-up and pre-installation review

User requested a from-device-to-analysis explanation, screenshots and a review before installation. No phone installation or download service was initiated. Emulator installation is test-only.

## Additional findings and fixes

The supplied `sources/sdk-guide.html` inside the private SDK preparation ZIP explicitly says fileID is valid only for RECORDING; STOP/PAUSE may report -1. Status-callback recordingDuration is valid only for STOP. Actual 1.3.02 bytecode forwards these inputs without adding an identity. Earlier test fixtures always supplied positive stop IDs, so 0.14.0 did not cover this contract and is superseded.

`RecorderTimeline` now associates ID-less pause/stop only with a previously observed active recording. It does not guess from storage or an unknown disconnected state. Non-stop durations are ignored. Controller side effects use the resolved ID. STOP total duration replaces interpolation, including delayed pause estimates. Transfer-status marker lists are forwarded; the supplied guide specifies millisecond offsets. Requested realtime state is cleared on stop/pause when no active transfer was observed, allowing resume after cancellation of a pending stream.

UI notices now follow recording/pause states. A completed recording's home action now expands confirmed transcript and all memories locally. It no longer calls the write-once transcript-review endpoint after submission. Waiting recordings still open the actual review page; failed processing can retry.

## Evidence

- Red tests: `recorder-sdk-contract-red.log`, `recorder-stop-duration-red.log`.
- Full unit suite after timeline changes: 132 tests, 0 failures/errors (`recorder-0141-check.log`, Gradle XML).
- Controller instrumentation uses start duration -1, pause/stop ID -1; tests actual decode and durable import under both delayed-active and never-started realtime branches.
- Fresh reviewer checked supplied guide and code; its final-duration interpolation finding was reproduced and fixed.
- `RecorderHomeVisualTest` renders real `NativeWorkbenchScreen` with only the external transport substituted. Device name explicitly says 演示事件. Screenshot evidence is synthetic SDK events, not real physical connectivity. Actual decoder and local capture are used.
- Existing cloud test's 88.34-second synthetic E01 file remains `ready` with four memories; initial test proved zero memories before confirmation. Same-journal later runs reuse existing episode and verify replay/persistence. Completed home transcript expansion has an explicit UI assertion.
- Device buttons publicly corroborated by https://service.soundcore.com/article-description/How-do-I-use-the-recording-feature-on-soundcore-Work ; double-tap highlight by https://www.soundcore.com/products/d3200-soundcore-work-ai-voice-recorder . ToB private SDK source remains the local ZIP/AAR, not unrelated public SDKs.

Final candidate source `cfc3a21b5baa8c75d2fab4708edddb3d07161e6f`; version 0.14.1-device-internal, code20261026, same signing certificate. Canonical candidate: `D:/JOB/hack/delivery/work3200-home-0.14.1-reviewed/`. Earlier 0.14.1 build directories are superseded intermediate artifacts, retained for traceability.

APK SHA256: `123ae02657dcfae8ff2bcdd33aeec3b3b0cdc9e09aa9dacf946cc400ca577e9c`. Size166783095. `signed-tests.log` in canonical folder records final instrumentation outcome.

User review artifact: `C:/Users/sky/Desktop/勿忘我_录音豆流程复核_0.14.1/功能与证据说明.md`. Recording/download/saved/organized screenshots use 0.14.1. Transcript-review screenshot is explicitly attributed to the prior 0.14.0 real cloud test (same unmodified review screen), not relabeled as a new physical result.

## Acceptance boundaries

Real device evidence still consists of the user's connection/device-info screenshots and binding-timeout screenshot. There is no retrieved physical raw sample or accepted end-to-end vivo recording. Current readiness is software review and then physical acceptance, never claimed total completion. Hardware-specific acceptance requires matching one 30-second recording across button events, download, intelligible playback, transcript, confirmed memory; then tab switch, screen-off, reconnect and repeated import.

Remote idle start/end, live transcription, audio replies via recorder speaker, AI weighting of marked sections and long-duration recordings are not claimed delivered. Existing decoder limits remain 8MiB raw, 100MiB PCM, 120s execution. No new Twin Q&A acceptance was run in this slice; existing backend model-stage wiring was inspected.

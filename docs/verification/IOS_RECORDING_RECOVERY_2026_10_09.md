# iOS recording submission recovery — 2026-10-09

The physical iPhone retained a roughly 13-second recording but had no pending
Episode ID. The paired Backend URL referred to the former Mac network address.
The current preview Backend listened only on loopback. The recording therefore
had not reached the real database or STT job queue.

## Changes

- Show uploading separately from asynchronous transcription. Upload failures
  leave the original audio and draft ID available for idempotent retry.
- Limit upload requests to 30 seconds and pairing/status/review requests to 15
  seconds. Long inference and direct transcription budgets remain unchanged.
- Explain network failures in Chinese, including the same-Wi-Fi, local network
  permission, and changed server address checks.
- Permit an unuploaded draft to reconnect only to the same Subject and Actor.
  Refuse moving it to another person and refuse service switching after an
  Episode has already been uploaded.
- Recover draft file URLs when iOS relocates the app data container on update.
  Preserve draft identity, capture metadata, and any question/calibration link.
  Keep the pending record visible if the file cannot be found.
- Offer connection recovery directly from the recording screen; dismiss the
  pairing sheet when the connection changes within the same Subject.

## Verification

`xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe
-destination 'platform=iOS Simulator,id=<local simulator>'
-derivedDataPath build/ios-recording-recovery -only-testing:RememberMeTests
CODE_SIGNING_ALLOWED=NO test`: **18 tests passed**. Regression cases cover
relocated recordings, same-person reconnection, cross-person refusal, refusal
after upload, and retryable upload timeout with a completed busy state.

The original phone recording was backed up locally without printing its content.
Calling the local Whisper sidecar with that actual M4A returned HTTP 200, a
non-empty transcript, and `whisper-ggml-base-60ed5bc3dd14`, in about 0.9 seconds.
This establishes decoding and local STT for this sample; it does not establish
recognition accuracy or the complete phone pipeline.

A separate LAN HTTPS Backend uses the original database and audio directory;
the simulator Backend, STT, AI Core, and worker remain available. No provider
secret was put on the phone. An API-only hosted unit probe on the physical phone
confirmed recovery of the original draft after container relocation. Its HTTPS
pairing attempt then returned `URLError.notConnectedToInternet` before reaching
the Backend. Phone network/permission recovery and a successful upload-to-review
run remain pending; do not describe that probe as passed.

The final production app was built with development signing for the original
installed bundle identifier, covered the existing installation without uninstall,
and launched successfully on the physical iPhone. This confirms installation and
startup only; the network prerequisite above still blocks the phone upload.

## Contract and data impact

No shared contract, API shape, migration, provider, or consent scope changed.
Reconnection uses the existing one-time HTTPS claim and certificate pinning.
Audio and its pending draft are preserved. Local STT does not confirm transcript
text or submit it for cloud extraction; the user's review step remains required.

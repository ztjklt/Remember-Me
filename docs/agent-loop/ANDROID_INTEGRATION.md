# Native Android shared-backend integration

Implemented on `codex/agent-integration` under the approved 2026-10-07 integration plan. Android's default Activity now opens a Kotlin/Compose workbench; the earlier local prototype, repositories, screens and tests remain in place. No WebView, provider SDK credential, client BYOK mode or generated fixture content is used by the integrated route. Existing PR #85 botanical branding and bundled landscapes are reused.

## Native flows and server boundaries

| Flow | Behavior |
| --- | --- |
| Identity and spaces | Enter a backend root URL and issued actor bearer token. `/api/v1/workbench/spaces` determines the actor and spaces; `/stories` determines the current role. Owner actions are unavailable to readers. Tokens stay in memory and are not saved. |
| Capture | Separate local recording confirmation and Android microphone permission. Record, pause/resume, stop; AAC/M4A originals remain in app-scoped storage. Going to background finalizes an active capture. |
| Recovery and ownership | `native-captures.json` journals each new capture at recording start, keyed by a digest of server/actor/subject. Only current owner-space originals are listed. Files from the former local prototype are preserved, but not attributed to an authenticated actor automatically. |
| Upload | Explicit upload confirmation; multipart `/api/v1/episodes` with `source=ANDROID_MIC`, stable recording-derived idempotency key, duration and recording consent. The local absolute path is not sent. Successful and failed uploads retain the local file. |
| Review | Wait for actual STT readiness. Play the complete source audio; edit transcript; explicitly confirm the checked text and server/cloud text processing before PATCH `/transcript-review`. No client-created memories substitute for backend results. Machine transcript and source audio remain visible. |
| Stories and search | Read actual authorized stories and active/pending/superseded memory states, source excerpts and model versions. Search invokes the shared backend's existing memory search. |
| Question answering | Explicit per-question cloud-text confirmation. Owner obtains `CLOUD_TWIN` consent; reader uses an actual cloud-enabled story grant. Show ORIGINAL, SIMULATION and UNKNOWN distinctly, with actual source evidence and complete-source playback. |
| Audio | Native `MediaPlayer` downloads through the authenticated workbench audio endpoint into transient cache. Pause/resume/seek/stop are real player operations. No invented excerpt timestamps. Source cache is removed on playback stop, identity/space changes, relevant evidence/authority changes and backgrounding. |
| Story grants | Select a reviewed, ready story and existing reader actor ID; separately confirm full original audio/words and optional cloud-QA permission. List and revoke actual grants. |
| Revisions | Select an active memory; record supplement/correction/change. Change requires time context. Journal the uploaded Episode before linking its revision, then persist successful linkage. Failed linkage retries the same Episode and blocks its transcript review. Only after the new recording is ready can the owner confirm the displayed old/new relation. |
| Requests | Submit actual requests. Owner may snooze, decline, or answer with a reviewed, ready Episode. Reader sees only the server-authorized answer reference. |
| Profile candidates | Owner explicitly opts into cloud proposal refresh; show actual job state, situation, independent recordings, supporting evidence and counter-evidence IDs. Confirm/reject candidates; confirmed inference can be withdrawn. Candidate confirmation does not relabel inference as original speech. |
| Daily reminder | Off by default. Owner may explicitly enable a generic local notification around 09:00; Android 13+ requests notification permission. Denial/system notification disable leaves it off with a visible explanation. No story/person data, audio, recording start or network operation is included. Logout, identity/space switches and a fresh app session cancel it. |

## Session lifecycle

All network operations use immutable server/token/epoch snapshots. The SessionGate rejects late responses and prevents subsequent old-identity requests. Signing out or switching a space clears stories, answers, search, review text, grants, candidates, capture references and playback. Token input is erased after login submission. Mutation actions invalidate visible answer/search caches before sending the request. A separate playback generation and foreground gate suppress late source downloads after Home/stop; both download publication and native prepared callbacks recheck it before creating cache or playing. Transcript edits live in the retained ViewModel, so configuration recreation keeps the review draft; closing review or changing identity clears it. Consent checkboxes still require fresh confirmation.

Foreground read-only refresh runs every eight seconds while idle. Evidence, grant or candidate changes clear cached answers and stop source playback; failed refresh clears protected remote views and playback. Backgrounded clients do not poll. Remote revocation is observed on the next successful refresh; this is polling, not a push revocation channel. There are no automatic cloud calls. The separately enabled reminder uses an inexact local AlarmManager broadcast and a generic notification, not a background network job. Reminder state starts off; logout/identity/space changes cancel both the alarm and displayed notification.

## Connect to the local stack

Start the shared Backend/AI Core/Whisper stack using `RUNBOOK.md`, apply migrations, and create owner/reader credentials with the backend's local actor tooling. Do not put those tokens or provider keys in Android source.

- Shared workbench started by `run_workbench.py` listens on port **8877** and restricts accepted Hosts to loopback.
- Phone **and emulator**: run `adb reverse tcp:8877 tcp:8877`, then use the default `http://127.0.0.1:8877`.
- Do not substitute `10.0.2.2` for this workbench: its Host allowlist rejects that direct emulator address. With multiple adb devices, select the target using `adb -s DEVICE_SERIAL reverse tcp:8877 tcp:8877`.
- HTTPS server roots are supported. The client rejects HTTP public hosts, user-info URLs, query strings and fragments. The local build's Android network policy allows cleartext for local/private-IP integration; this generates one explicit lint warning and is not a production transport certification.

## Verification, 2026-10-07

Toolchain used:

```powershell
$env:JAVA_HOME='D:/codex_work/remember-me-toolchain/jdk/jdk-17.0.20.1+1'
$env:GRADLE_USER_HOME='D:/codex_work/remember-me-toolchain/gradle'
$env:ANDROID_HOME='D:/codex_work/remember-me-toolchain/sdk'
cd D:/codex_work/remember-me-agent-loop/apps/android
./gradlew.bat testDebugUnitTest assembleDebug lintDebug --console=plain
```

The final run passes 33 unit tests (15 new integration tests and 18 retained baseline tests), APK assembly and lint. Lint reports **0 errors, 8 warnings**: retained prototype/assets warnings, plus the documented local cleartext policy warning. JVM integration tests run real local HTTP sockets for bearer/no-store headers, redirect refusal, ANDROID_MIC multipart provenance, stable retry keys, original-file retention and late-response rejection. Session tests cover identity/space epochs and URL validation. Capture submission tests cover failed revision linkage, durable receipt, retry without duplicate upload, blocked review and mandatory change-time context. Playback regression tests simulate a delayed audio response crossing a background transition and verify that no cache/player publication occurs; old prepared callbacks and superseded identity/request generations cannot play. Reminder-time tests cover before/at 09:00, local timezone and daylight-saving transitions. Android notification delivery/permission, Activity recreation and alarm cancellation are not exercised by JVM tests; draft retention is implemented by ViewModel ownership rather than composable local state.

APK: `D:\codex_work\remember-me-agent-loop\apps\android\app\build\outputs\apk\debug\app-debug.apk`. The APK is about 155 MB because the existing bundled Sherpa/ONNX dependency remains preserved.

The initial `adb devices` probe returned no attached devices; at that time the configured SDK had no emulator/system image and no AVD. The parent integration task subsequently began provisioning an emulator. This Android subtask has not yet executed instrumented/native microphone, native playback/manual listening, real backend-to-Android end-to-end or true cloud-model acceptance: those remain **unverified here**, with any later emulator evidence recorded separately by the parent task. Successful build/JVM tests do not establish those results. Earlier instrumented tests target the retained local prototype and were not executed in this subtask.

## Remaining practical limits

- No production account management, token persistence/rotation, cloud deployment or release signing is claimed.
- No Android calibration or synthesized-voice UI is added in this slice; shared backend/web calibration remains available. Playback is original source audio.
- Counter-evidence IDs are displayed; supporting excerpts and source buttons resolve first through the candidate endpoint's authorized raw evidence, then visible story evidence. Raw references absent from the memory store remain usable. Unknown evidence IDs are not invented.
- A reader's externally revoked grant is rechecked through foreground polling; content already heard/saved cannot be recovered.
- Raw originals remain in app storage when a source memory is deleted. The integrated client only uploads recordings it actually captured and journaled; old anonymous prototype recordings are left intact.
- Reminder delivery may be delayed by system battery policy. Device reboot does not rearm the alarm; a fresh app session resets the option to off. No real notification delivery or permission-denial test is claimed here.

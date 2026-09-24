# Phase 1 Android ↔ Backend integration

This client uses Backend `POST /api/v1/episodes`, `GET /api/v1/episodes/{episode_id}`, and `GET /api/v1/episodes/{episode_id}/result`. The request and response shapes come from Contract v0.1.2. The Android app never calls STT, AI Core, or a provider directly.

## Local setup

In `services/backend`, initialize the local database and create a development Actor, Subject, and **RECORDING** consent:

```bash
mkdir -p var
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked python -m app.seed --subject-name "Ada" --actor-name "Ada"
```

Keep the printed Actor Token private. Start Backend on an interface the Android device can reach, and start its worker in another shell:

```bash
uv run --locked uvicorn app.main:app --host 0.0.0.0 --port 8000
uv run --locked python -m app.worker
```

Use `http://10.0.2.2:8000` in the Android emulator, or `http://<computer-LAN-IP>:8000` on a phone connected to the same network. Debug builds allow cleartext for this local test; release builds require HTTPS for remote Backend addresses. Confirm the phone can open `/health` before testing upload. Do not put the Actor Token in a URL, screenshot, log, or tracked configuration file.

After saving a real recording, choose **上传并处理这段录音** and enter the Backend address, Actor Token, Subject ID, and the active RECORDING Consent ID from the seed output. The onboarding switches are prototype UI and do not create Backend consent; the upload requires an actual Backend consent. The Token is held only in the running app session. On app restart, enter it again.

## What to verify

1. Record, pause/resume, stop, and play a real `.m4a` file. Open its upload screen and start upload.
2. Confirm visible byte progress, the returned `episode_id`, Backend processing states, and a result Memory on the Archive screen. The Memory content, source type, evidence IDs, confidence, and model version must match `GET /api/v1/episodes/{episode_id}/result` for that Episode. Real results have no invented audio-play button because this API does not expose one.
3. Interrupt the network during upload. The error must be visible and retryable; retry the same saved file. The idempotency key is derived from that file path and remains the same after app restart, so a request whose response was lost resolves to the same Episode rather than creating a duplicate.
4. Interrupt status polling after upload. Retry must query the retained `episode_id` without uploading audio again. A terminal Backend `failed` state shows its error and preserves the local recording.
5. Run `cd apps/android && ./gradlew test assembleDebug compileDebugAndroidTestKotlin`; execute the instrumentation tests on a device or emulator with `./gradlew connectedDebugAndroidTest`. Compilation alone does not execute device tests.

With fake STT or fixture AI, this demonstrates wiring only. The Phase 1 gate still requires a real Android recording, real STT, real AI extraction, and the same Episode Memory displayed on the device. PR #46's capture lifecycle fix and owner device verification are separate prerequisites for that gate.

## Code boundaries

`MainActivity` assembles `PhoneMicrophoneCaptureAdapter` through `SelectingAudioCaptureService`, plus `HttpEpisodeGateway`, `EpisodeFlow`, and `EpisodeMemoryRepository`. Composables receive those interfaces or state; they never instantiate a Mock Repository. `HttpEpisodeGateway` owns multipart upload, bearer authentication, bounded HTTP reads, and contract-shaped parsing. `EpisodeFlow` retains the Episode ID across in-session status retries. The Mock Repository remains for previews and tests only.

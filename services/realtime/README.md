# Remember Me real-time voice worker

Approved by the [2026-10-13 realtime proposal](../../docs/architecture/realtime-twin-voice-contract-proposal.md). The owner selected LiveKit Cloud plus Alibaba Cloud Model Studio CosyVoice. The iOS client continues to authenticate only against Remember Me Backend. This worker contains no provider key, Actor bearer token, voice reference or generic voice LLM.

## Deployment

1. Backend applies migration `0019_realtime_voice` and receives the private settings listed below. This branch starts from `codex/ios-cloudbase-backend` at `b6ee30d`; do not replace the cloud Backend with the older iOS checkout's backend. The existing authorized `0018_twin_conversations` work is included as an integration snapshot, and `0019` follows it on a single migration chain. Its source hashes are recorded in the ignored build report.
2. Register at <https://cloud.livekit.io/login>, create the Remember Me project, disable Agent Observability audio/transcript collection, and obtain its WSS URL and server credentials. Keep credentials in the ignored `build/private/realtime.env` file (0600), not chat, source control or the App. `REMEMBER_LIVEKIT_API_URL` uses the same hostname with `https://`.
3. Install the official LiveKit CLI and connect it to your project. Deploy this directory with the official `lk agent create` flow. Supply `REMEMBER_REALTIME_BACKEND_URL` and the same `REMEMBER_REALTIME_WORKER_SECRET` using the CLI's secrets mechanism. Cloud injects the LiveKit connection credentials. No provider key goes to this worker. [Official deployment guide](https://docs.livekit.io/deploy/agents/).
4. Keep the Backend registered/public origin fixed; it exposes short-lived signed enrollment sample reads and service-authenticated WebSocket/PCM routes. It must support WebSocket and streamed HTTP, with idle heartbeats at most 10 seconds. CloudBase's existing API can host these request-scoped operations; its minute-triggered function cannot host this persistent worker. [CloudBase WebSocket guidance](https://docs.cloudbase.net/run/faq/gw).
5. Verify the provider and room connection before setting `REMEMBER_REALTIME_ENABLED=true`. A minted ticket alone does not prove that an agent is running; iOS fails clearly when the agent does not become ready. On the phone, grant the separate VOICE permission, record 5–15 seconds containing only the user's voice, review its actual text, and wait for the provider profile to become ready. Then accept the current call purpose and start a call.

Backend settings: `REMEMBER_REALTIME_ENABLED`, `REMEMBER_LIVEKIT_URL`, `REMEMBER_LIVEKIT_API_URL`, `REMEMBER_LIVEKIT_API_KEY`, `REMEMBER_LIVEKIT_API_SECRET`, `REMEMBER_REALTIME_WORKER_SECRET`, `REMEMBER_REALTIME_PUBLIC_URL`, `REMEMBER_COSYVOICE_API_KEY`, `REMEMBER_COSYVOICE_MODEL`, `REMEMBER_COSYVOICE_BASE_URL`, `REMEMBER_REALTIME_INFERENCE_URL`, and `REMEMBER_REALTIME_ASR_MODEL`. Defaults target Beijing `cosyvoice-v3-flash` and `paraformer-realtime-v2`; use a key from the same region. Existing batch-ASR permission does not prove streaming ASR or clone synthesis permission.

The existing authenticated CloudBase processing tick now retries at most two pending provider deletions after processing. Operators can also call `/internal/realtime/maintenance` with the separate realtime service credential. A voice that the provider failed to delete stays `delete_pending` and cannot be used. Do not report successful remote deletion until maintenance has actually completed it. Signed sample fetch URLs must not appear in access logs; the CloudBase launcher already runs Uvicorn with `--no-access-log`.

## Local worker development

```sh
uv sync --frozen
# Populate environment through a private env file; do not paste secrets into command history.
uv run --env-file /absolute/private/worker.env agent.py dev
uv run pytest
```

The server must be LiveKit Cloud or a properly TLS-configured self-hosted LiveKit server. The iOS client refuses plain WS and never disables TLS checks. SDK audio processing uses native/WebRTC echo cancellation; automatic barge-in is VAD-based, so it may treat short acknowledgements as interruptions. Real headset, speakerphone, Bluetooth and cellular latency need a physical-device check.

## Behavioral guarantees and limits

- Real streaming Paraformer ASR; one active response; user speech immediately clears LiveKit playback and cancels the old provider stream. Late old answers cannot start new speech. Manual interruption is scoped to the old turn so it cannot cancel the next answer.
- Backend reuses its existing validated evidence Twin. It never speaks unchecked partial LLM output. SIMULATION speech includes an inference introduction. UNKNOWN remains visible as text, without impersonated speech.
- CloudBase source invalidation checks still apply. Actor credential expiry/logout, ownership/consent loss, policy changes, profile revocation, call end and the 30-minute lifetime deny further operations. A service watchdog closes the room after authorization loss.
- Session audio/transcript recording is disabled explicitly (`record=False`), and no Egress recorder is configured. Do not enable cloud observability audio/transcript collection without a separate product decision and notice.
- Voice turns do not create Episodes or train the Person Model. Voice turns use the approved multi-turn Twin operation and link the last completed text answer in this call. Interrupting playback cancels audio, not the visible validated text answer; context does not assert that the entire audio was heard. Conversation replies remain explicitly labeled and never become personality evidence.
- Code, fixture tests and simulator builds do not establish real user's voice similarity, provider availability, cellular performance or end-to-end latency. Record actual device and provider observations separately.

## Created Cloud deployment (2026-10-13)

Project `Remember Me iOS Twin` (`p_52jfs83pq79`), media endpoint `wss://remember-me-ios-twin-ot7lrl1c.livekit.cloud`, Agent `CA_tPrXyGHActp3`, region `ap-south`, dispatch name `remember-twin`. The backend API key was created with the owner's explicit approval and stored privately; it is absent from this repository and the iOS client. Agent Observability was disabled when the project was created; `record=False` remains explicit in the worker.

CloudBase caps combined environment variables at 5 KiB. Its public Tencent PostgreSQL CA chain is therefore bundled as `infra/cloudbase/runtime/tencent-postgres-ca.crt`, verified as certificates only; the launcher still forces `sslmode=verify-full`, fixed private schema, and this trust bundle. Operators may still override it using the existing private `REMEMBER_POSTGRES_CA_PEM` option. The image includes FFmpeg for bounded enrollment sample validation.

The agent's Docker build succeeded and runtime logs confirmed registration. A real provider test using the documented `longxiaochun_v3` preset returned PCM and an exact streaming Paraformer transcript; this establishes provider streaming permission, not an enrolled person's voice similarity. Actual cloud transport and physical-device results are kept in the dated verification report.

The continuous recognizer clocks 16 kHz PCM through DTX and muted gaps, consumes authenticated final results directly rather than depending on SDK manual-turn transcript events, and uses backend application-level heartbeats during silence. VAD still interrupts playout. SDK private warning extras are redacted. See the dated verification for observed interruption/audio/quiet-period checks; no actual person’s clone was tested automatically.

Startup authorization is bounded: eight-second HTTP connect timeout, ten-second whole-attempt budget and at most one retry for connection failures only. Denials and read timeouts do not retry; failed authorization, room validation or RTC connection releases the Backend HTTP client. Normal answer reads retain their 120-second budget.

## Frontend call completion 2026-10-14

Authorized by the Product / Integration Owner implementation request. ProxySTT now uses zero SDK retries and nonretryable failures; a lost recognizer ends the call instead of silently resuming. Continuous PCM and the existing 65-second quiet-period behavior are preserved. Backend PCM writes have a two-second bound. The public v0.6/v0.7 contracts and database schema are unchanged.

Opt-in REMEMBER_REALTIME_NETWORK_DIAGNOSTICS records independent numeric speech-burst observations for RTC/worker input and ASR send, final arrival, Twin request/answer and first playout frame. Backend records input/provider-send/final with the same hashed numeric call reference. Stage segment numbers do not prove identity across stages; no PCM, transcripts, tokens or actor/subject identities enter these diagnostics. Diagnostics stay off in normal operation.

The reusable tools/verification/realtime_voice_probe.py requires a dedicated synthetic preset fixture and a protected credential directory. Default dispatch uses the original ticket unchanged; an explicit --qa-agent-name is restricted to a staging test and preserves all microphone-only grants and identity claims. Reports contain only states, counters and times. A separate finally controller must clear the preset reference before revoking the test VOICE grant, so provider maintenance never tries to delete a system preset. Never use a person's voice profile for this regression.

# iOS Twin realtime Voice — 2026-10-13

## Scope and authorization

The Product / Integration Owner requested own-voice realtime Twin conversation with interruption, selected LiveKit Cloud and Alibaba Cloud Model Studio CosyVoice, and explicitly approved creation of backend credentials, private local storage and backend/Agent deployment. The earlier preference to defer this task’s iPhone installation remains respected.

The native changes are in the original checkout. Backend and worker changes are isolated on `codex/ios-realtime-livekit` in the attached `livekit-twin` worktree. The approved conversation snapshot `78574ea` and Twin identity correction `b35c1c2` are included. Android’s working prototype and unrelated native changes were preserved. Contract v0.6 is additive; v0.5 remains unchanged. The approved scope is recorded in [the realtime proposal](../architecture/realtime-twin-voice-contract-proposal.md).

## Current acceptance status

Native code, signed package and Backend deployment are available. The existing Mumbai Agent has been retained. Four observed startup attempts failed in the HTTPX connection stage before TLS or business authorization; subsequent cloud TCP/TLS/HTTP requests recovered. The same business code running as a local Worker passed the complete RTC conversation/interruption control. The initial listening event was emitted before ASR readiness; the worker now waits for the actual Backend ASR ready event and releases resources on timeout. A recovered Cloud call before this fix produced no final text. After the fix, two Cloud voice replies and automatic/manual interruption passed, but the third utterance after 65 seconds of silence produced no new final text within 40 seconds. Final Cloud realtime acceptance therefore remains incomplete. See the [timeout diagnosis and controlled comparisons](IOS_REALTIME_TIMEOUT_DIAGNOSIS_2026_10_13.md).

The account permits one managed Agent only. A separate US diagnostic create was rejected by quota 1/1 and created no deployment. Deletion was not authorized or performed. The current evidence does not establish that moving to the US would repair either failure; diagnosis proceeds on the retained Agent without requiring that replacement.

## Delivered behavior

- The iOS **孪生** page has a phone entry. It checks owner-scoped capabilities and separate VOICE consent, offers a dedicated 5–15 second sample recording, requires reviewed text and an explicit own-voice confirmation, prepares/reconciles the profile, and exposes mute, manual interruption and hang-up. User speech interrupts ongoing playback automatically. Backgrounding, logout, scope changes and consent loss stop the call.
- The Backend keeps provider keys out of both clients. It issues 2-minute microphone-only LiveKit tickets, limits calls to 30 minutes, rechecks actor credentials and grants, validates source-bound Twin answers and PCM generations, signs short-lived private sample reads, and retries provider deletion through the existing authenticated processing tick.
- The worker uses streaming Paraformer, Silero VAD and SDK-managed audio playback. Recognition reads only the authorized owner’s microphone independently of SDK manual turns. A single answer is active; interruption cancels its HTTP/provider stream and clears queued audio. A late old answer cannot resume playback. UNKNOWN remains text-only; SIMULATION includes its introduction.
- Voice conversation reuses the approved Twin conversation context. It does not create Episodes or Person Model evidence. Session recording is explicitly disabled (`record=False`); Agent Observability is disabled.
- The native fixes serialize mute updates and reject stale operations from earlier calls. Connecting-time interruption cannot bypass the readiness timeout. Sample restoration retains its actual owner and file protection; backgrounding invalidates pending microphone permission work.

## Cloud deployment verified

[LiveKit project dashboard](https://cloud.livekit.io/projects/p_52jfs83pq79/overview): **Remember Me iOS Twin**, project `p_52jfs83pq79`, WSS `wss://remember-me-ios-twin-ot7lrl1c.livekit.cloud`. Agent `CA_tPrXyGHActp3` / dispatch `remember-twin` remains in region `ap-south` (Mumbai). The readiness diagnostic update deployed successfully to this same Agent; the earlier bounded-startup version was `fsMd6dHUUYF8`. Project data region is United States. Credentials are ignored private files, directory mode 0700 and file mode 0600; no provider or LiveKit server secret is in the App, Git or project proof screenshot.

CloudBase `remember-ios-api` in Shanghai serves **remember-ios-api-016** with **100% traffic** and status `normal`. `/health` and `/ready` return 200; readiness reports database and object store `ok`. `/api/v1/service-info` reports release **ios-realtime-1475135761e6**, API version `0.7.0`, registration disabled. Migration head is **0019_realtime_voice**, following `0018_twin_conversations` without dropping existing data.

The source bundle is `build/realtime-cloudrun-v7-20261013.zip`, SHA-256 `1475135761e6e97ad244c618c08cb1d78211bddd5d5ad6679d0070bf8fe06b76`. CloudBase task `2348738` reported a startup wait timeout; it was not reported as successful. The desired version subsequently became active, independently verified through traffic records, readiness and the exact release marker. Earlier versions receive zero traffic. A later attempted runtime update was rejected as `ResourceInUse` and produced no configuration change.

The image includes FFmpeg and wsproto. Public Tencent PostgreSQL CA certificates are bundled to fit CloudBase’s 5 KiB environment-variable limit; `verify-full` and the private schema remain enforced. Deployment starts wsproto with protocol Ping interval zero because the managed gateway repeatedly dropped protocol Ping/Pong sessions at approximately 40 seconds. The application watchdog still reauthorizes and heartbeats every second. Only final ASR text is submitted; PCM does not trigger a database query per 20 ms frame. Lossless WebSocket compression, 100 ms batches and a clock reset before transport waits prevent avoidable ASR backlog. SDK reconnects reauthorize and do not replay consumed PCM. A stalled send or live microphone sample delayed over two seconds ends recognition instead of eventually submitting stale speech. Startup authorization uses an eight-second connection timeout and ten-second whole-attempt budget, retries at most once for connection failures only, and releases its HTTP client before failing. Rejected authorization and read timeouts are not retried. Normal answer reads retain their 120-second budget.

The approved AI Core source remains unchanged across the final v6/v7 transport deployments; 39 files were hash compared.

## Tests actually run

| Area | Observed result |
| --- | --- |
| Backend Voice, deployment, conversation, Twin and consent regression | 60 passed, 4 warnings |
| Final compressed real-Uvicorn socket suite | 15 passed, 2 warnings; anonymous rejection, unchanged PCM forwarding and timely revocation closure |
| Final worker regression | 46 passed; prior 36 transport checks, redacted diagnostics, actual ASR readiness, startup failure/timeout and idempotent cleanup |
| Backend hang-up / disconnected socket regression | 25 passed, 2 upstream warnings; pending remote deletion cannot defer durable end and is canceled by its whole-operation deadline. These two small Backend fixes are not yet deployed |
| Regional dispatch configuration regression | Backend 23 passed, including 8 new checks; no production dispatch change |
| AI Core conversation / grounded answers | 38 passed |
| Shared contracts | 21 passed in both checkouts |
| Final native Voice / local recording regression | 30 passed (10 Voice + 20 recording) |
| Earlier native connection / recording / Voice regression | 45 passed; intermediate Voice suite also passed |
| Final signed generic-device build | Passed; package Info.plist inspected as 1.6.2 / 2026101311 |

Exact matching of seven private credential values found no matches in 1,322 backend/worker files, 571 non-ignored original-checkout files or 20 signed App package files. `git diff --check` passed. Upstream deprecation warnings were retained. Failed deployment/probe attempts are not counted as passing checks.

## Real provider and RTC evidence

All automatic cloud tests used a synthetic QA account and documented system preset `longxiaochun_v3`. A temporary QA profile bypassed enrollment solely to exercise transport. This is not the owner’s cloned voice. No personal recording was uploaded and no provider clone was created.

A direct CosyVoice probe returned 229,440 bytes of PCM with a first chunk at 0.44 seconds in that single local measurement. Streaming Paraformer returned the expected synthetic Chinese sentence; enrollment listing returned HTTP 200. A direct deployed-backend probe completed three utterances across 65 seconds of silence with 75 application heartbeats and HTTP 200 call end.

The compressed RTC probe on a preceding worker deployment completed three CONVERSATION replies, received non-silent audio, changed turn IDs during barge-in and showed no old-turn restart. A later independent local Worker control with the current business implementation also completed all three replies, interruption checks and 65 seconds of silence. The interrupted audio gap contained zero non-silent frames. Manual interruption was confirmed against the backend’s cleared active turn. After silence, the next utterance again produced speech. All 397 injected frames were sent and call end returned 200. The local Worker was stopped and its QA fixture was cleaned. These results do not establish Doubao-equivalent latency or stable Cloud Agent acceptance.

A subsequent bounded-worker probe failed before initial `listening`, without injecting speech. Cloud runtime logs show a Backend authorization `ConnectTimeout`; a timeout in the probe’s final DELETE initially obscured that startup failure. The QA runner was corrected to retain primary errors, phase, safe events and bounded cleanup results. Repeats again failed before readiness, with no speech injected and clean producer shutdown. These samples failed during startup. Additional diagnostics later captured healthy Cloud TCP/TLS/HTTP requests, followed by a Cloud RTC run whose ASR connection transmitted PCM and received heartbeats but produced no final result. The latter is a separate post-startup failure and is recorded with the readiness correction in the linked diagnosis. No production route was switched and no Agent was deleted.

The readiness-fixed Cloud control reached true ASR ready and then emitted listening at 9.657 seconds. First question/answer arrived at 16.978/21.383 seconds, second at 35.878/38.862. Automatic interruption showed zero non-silent frames in the gap and no old-turn restart; manual interruption was independently confirmed. Silence lasted 65 seconds with zero non-silent playback. All 397 injected input frames were sent, but the third utterance at 107.805 seconds received no new question/answer during the 40-second deadline. The same ASR connection remained active until test cleanup: 14,088 received microphone frames, 504 speech frames, 58 transmitted speech packets, 135 heartbeats and two final results. These cumulative counters cannot establish which stage received the third utterance. End and VOICE revocation returned HTTP 200, the preset reference was cleared, profile became missing and no QA calls remained active. Diagnostic logging was subsequently disabled explicitly through a successful same-Agent configuration update; no endpoint was pinned in production.

## Native package and remaining own-voice journey

The signed package is at `build/ios-livekit-1.6.2-final/RememberMe.app` in the original checkout. This task has not installed it, honoring the earlier defer-installation preference. A separately authorized one-tap recording task installed **1.6.1 / 2026101310**; its device registry reports that version and the signed package contains both `TwinVoiceCall` and `TwinVoiceCallView`. That installation does not verify the latest 1.6.2 fixes.

After installing the final package, the owner must personally accept the purpose notice, record **10–15 seconds** of clear speech within the 5–15 second limit, review its actual text and confirm it is their own voice. The [official Model Studio guide](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide) recommends 10–20 seconds with at least five continuous seconds of clear speech. This deployment uses the selected Beijing `cosyvoice-v3-flash` endpoint.

Voice similarity, physical-device barge-in, speakerphone echo cancellation, Bluetooth routing, cellular latency and the background transition still require that focused device journey. Cloud startup can fail across the Mumbai–Shanghai path, as observed above; successful probes are not a production availability guarantee.

## Credential incident and owner decision

An overly broad diagnostic print exposed existing backend credentials in earlier tool output. The agent reported this immediately. The newly generated LiveKit Secret was not exposed. The owner chose to rotate the old credentials personally later; none was revoked or rotated on their behalf.

Coordinate updates to the database password in `REMEMBER_DATABASE_URL`, Alibaba `REMEMBER_PARAFORMER_API_KEY` and `REMEMBER_COSYVOICE_API_KEY`, DeepSeek `AI_API_KEY`, storage `REMEMBER_CLOUDBASE_API_KEY`, and timer/API `CLOUDBASE_WORKER_TOKEN`. Timer and API token values must change together; ASR and CosyVoice currently share the selected Alibaba credential. Update private local deployment configuration and the active cloud environment. Never paste replacements into chat.

## Dispatch configuration and packaging

The branch adds the internal `REMEMBER_LIVEKIT_AGENT_NAME` option to Backend and worker, defaulting to `remember-twin`. Names are nonempty ASCII `[A-Za-z0-9_.-]`, at most 64 characters; room metadata remains only the call ID. Production Backend version 016 predates this optional configuration seam and still uses the same default dispatch. The US diagnostic context was prepared with a separate name, but its create request failed before allocation. Private synthetic QA can substitute only that dispatch in a correctly signed microphone-only ticket while retaining all other claims and not extending expiration; native tickets are untouched.

## Owner decision and synthetic cleanup

The owner requested an explanation before deciding on Agent replacement; deletion was not authorized or performed. The existing Mumbai Agent remains. A preliminary HTTP cleanup timed out, then narrowly scoped QA database cleanup cleared the preset reference and sample fields before revoking only the synthetic VOICE grant, and marked that grant’s calls ended. Independent proofs report `profile_cleared=true`, `qa_voice_revoked=true`, `qa_calls_ended=true`, and the selected QA LiveKit room absent. The system preset was not remotely deleted; existing CLOUD_TWIN/RECORDING grants and ordinary account data were preserved.

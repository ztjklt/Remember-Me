# iOS Twin realtime Voice — 2026-10-13

## Scope and authorization

The Product / Integration Owner requested own-voice real-time Twin conversation and interruption, selected LiveKit Cloud with Alibaba Cloud Model Studio CosyVoice, then explicitly approved creation of `Remember Me iOS Twin Backend` credentials, local private storage and backend/agent deployment. The earlier deferred iPhone installation preference remains respected.

The iOS changes are in the original checkout. Backend/worker implementation is isolated in the attached `livekit-twin` worktree, starting at `b6ee30d` of the dedicated iOS CloudBase backend. The separately approved conversation work from `78574ea`, plus the approved `b35c1c2` Twin identity correction, is included; its source hashes are stored in the ignored integration report. Existing Android behavior and the user's other iOS changes remain intact.

## Implementation

- iOS Twin phone entry: scoped service availability, separate purpose notice, dedicated 5–15 second recording, reviewed text and explicit own-voice confirmation, profile preparation/reconciliation, mute, automatic speech interruption, manual interruption and hang-up. Backgrounding, logout, scope change and consent loss stop the call. No provider credential is embedded in the App.
- Backend v0.6: owner-scoped profile/capability/call routes, 2-minute microphone-only room JWT, 30-minute call limit, credential and consent rechecks, current validated Twin answers, generation-bound PCM streams, private signed enrollment sample reads, durable revocation and bounded deletion retries via the existing authenticated processing tick.
- LiveKit worker `remember-twin`: streaming Paraformer proxy, Silero VAD, single active answer, canceled old streams and late-result rejection. Session recording is explicitly disabled. Voice turns reuse approved conversation context and do not create Episodes or Person Model evidence.
- Migration `0019_realtime_voice` follows `0018_twin_conversations`, adds two tables and preserves existing data. The image includes FFmpeg and wsproto; a real Uvicorn WebSocket handshake test covers accepted worker authorization and rejection of anonymous access.
- Public Tencent PostgreSQL CA certificates are bundled, preserving `verify-full` and fixed private schema. This avoids CloudBase's 5 KiB environment-variable cap; no private key is bundled.

## Cloud resources and observed results

LiveKit project: `Remember Me iOS Twin`, ID `p_52jfs83pq79`. WSS: `wss://remember-me-ios-twin-ot7lrl1c.livekit.cloud`. Agent: `CA_tPrXyGHActp3`, `ap-south`. The official Cloud Docker build succeeded; runtime logs confirmed registration as `remember-twin`. Agent Observability was disabled at project creation. Credentials are in ignored private files with mode 0600 and were not included in the bundle, App or new-key screenshots.

A genuine provider streaming test with the documented `longxiaochun_v3` preset returned 229,440 bytes of PCM; first audio chunk was 0.44 seconds in this one local probe. Streaming Paraformer returned the exact synthetic Chinese sentence. Enrollment listing returned HTTP 200. These checks do not establish a cloned person's voice or production latency.

CloudBase source deployment initially exceeded the 5 KiB environment cap; no version was published by that rejected update. After bundling the public CA, `remember-ios-api-009` built and pushed successfully, but the release task reported a startup wait timeout. Read-only inspection of that instance subsequently confirmed `/health` 200 and `/ready` database/object-store `ok`. The prior working version retained traffic. A subsequent deployment includes wsproto; final rollout and transport observations will be appended after verification.

## Tests actually run

- Backend targeted regression: 58 passed, including all 13 realtime Voice cases and the real Uvicorn WebSocket handshake.
- Worker: 6 passed (late answer after interruption, UNKNOWN, close, PCM framing, insecure remote URL).
- AI Core conversation/grounded: 38 passed against the final approved conversation-v2 / twin-identity-v1 prompt.
- Contract: 21 passed, including additive v0.6 and unchanged v0.5 definitions.
- iOS selected regression: 45 passed (26 connection, 13 recording, 6 voice-call tests); after profile-reconciliation UI refinement, the 6 voice tests passed again.
- Simulator build and signed generic-device build passed. The earlier signed artifact was inspected as 1.5.0 / 2026101308; the final Voice signed artifact was inspected as 1.6.0 / 2026101309. No iPhone installation was performed. Initial device build ran out of disk space; only this task's generated scratch build and unused virtual environment were removed before successful retry. A simulator invocation with the wrong OS destination failed, then the existing iPhone 18 Pro / iOS 27 destination passed.
- `git diff --check` passed. Upstream deprecation warnings are recorded; no failed checks are reported as passing.

## Remaining own-voice evidence

The user must personally confirm the purpose notice and record 5–15 seconds containing only their own voice in the App. No personal voice sample was uploaded by the agent. Voice similarity, speakerphone echo cancellation, Bluetooth routing, cellular latency, physical-device automatic interruption and background transitions still require that focused device journey. Synthetic service/transport probes must be labeled as such.

## Credential incident and owner decision

While inspecting old deployment parameters, an overly broad diagnostic print exposed existing backend credentials in tool output. The agent reported this immediately. The newly generated LiveKit Secret was not exposed. The owner chose to rotate all old credentials personally later; no credential was revoked or rotated on their behalf.

Private fields requiring coordinated updates: database password in `REMEMBER_DATABASE_URL`, Alibaba `REMEMBER_PARAFORMER_API_KEY` and `REMEMBER_COSYVOICE_API_KEY`, DeepSeek `AI_API_KEY`, storage `REMEMBER_CLOUDBASE_API_KEY`, and timer/API `CLOUDBASE_WORKER_TOKEN`. The timer and API token must be changed together; Alibaba ASR and CosyVoice currently share the selected application credential. Update the ignored runtime deployment configuration as well as the active cloud environment; never paste replacement values into chat.

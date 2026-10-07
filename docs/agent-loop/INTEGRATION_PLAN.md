# 多人开发融合与真实闭环 — approved 2026-10-07

User approved implementation in this conversation. Work on `codex/agent-integration` from local `464bdeb`; no push, merge, publication or diet-project changes. Upstream pins: develop `4dc3d5a`, colleague `8627f03`, UI #85 `efaa9ec`. Live remote pins verified unchanged before implementation.

## Deliverables and invariant interfaces

1. Port UI commits 279a8f6 / 82fa7e8 / efaa9ec with attribution; preserve actual services and authorization.
2. Weixin text adapter: exact https://chatapi.weixin.qq.com/openai/v1 and Deepseek-v4-flash; json_object, local schema/evidence validation, no thinking/tools, WEIXIN_CHAT_API_KEY server-only. 45 second requests, serial execution, <=3 attempts only for transient failures. No provider fallback.
3. One backend source of truth: reviewed recordings, ownership and story grants, effective source material (24000-character cap), explicit profile candidate approval/rejection, independent reader derivation, correction/deletion/revocation invalidation and short publication checks. Calibration only proposes changes. Android recordings now wait for review.
4. Real workbench using adopted nature/brand assets and garden bound to actual story/memory IDs. Native Android connects same backend, supports recording/review/search/ask/evidence/grants/revisions/requests; retains local audio and clears sessions/caches on identity changes. Optional private reminders off by default. iOS style accepted, runtime not certified on Windows.
5. Three fictional subjects (76-year-old retired bus driver in Alzheimer scenario, 32-year-old female firefighter, 48-year-old seriously ill male). Ten 3–5 minute recordings each, on fictional month days 1/3/6/9/12/16/20/24/27/30. Distinct owner/reader each; scripts, actual audio, raw ASR, reviewed text and gold annotations kept separate.
6. Xiaomi TTS official pay-as-you-go endpoint, fictional voice design -> clone; local Whisper. Three samples must pass whole live loop before remaining27 synthesis. Real Weixin credentials missing is a gate, never fixture substitute. Synthetic voice generation is evaluation tooling, not product voice-cloning functionality.
7. Deterministic rules all pass, 10 named live categories and60 questions; source-change/revocation repeated3 times. Real microphone/emulator/device/manual listening/cloud-model evidence separately reported. Leave failed cases and honest blockers.

## Adoption decisions

- Reuse colleague JSON-object support, original-text access, evidence-linked profile patterns and checkpoint/reminder design; adapt to canonical service rather than importing its old migrations or Android BYOK mode.
- Retain UNKNOWN public enum (map INSUFFICIENT internally). No duplicate experimental API mounted alongside canonical auth.
- New candidate schema is additive. Old contract files remain intact. Confirmed inference never becomes original evidence. Repeated copies do not count as independent observations.
- Exclude inactive/deleted evidence spans from current material; when unsafe to separate, suppress affected story rather than resurrect obsolete facts. Recheck actual content and authority versions after model work.
- Persist cloud credentials only in ignored server config; never print or place in clients/test fixtures.

## Execution ledger

- Setup: clean existing external worktree reused, independent branch created, exact remotes fetched and verified.
- Task1 UI import: completed locally in d14d1d0; attribution to PR85's three commits retained. No upstream merge.
- Task2 provider: implemented in 7f2f49e and a22e20d; 158 AI Core tests passed. Actual Weixin calls remain blocked by missing credential.
- Task3 backend candidate/material and migrations: implemented in 06e174a; 276 backend tests passed. Migrations 0009/0010 checked on database copies before local application; originals backed up. Empty pending-revision sharing and calibration final-publication race fixed during review.
- Task4 real web/Android connection: implemented. Nature garden binds live IDs; native APK built. Android emulator installed/logged in, read actual waiting stories, played/paused/sought original audio, exercised permission denial/recovery and background save. Physical device and full model loop pending.
- Task5 synthetic evaluation: three voice-design samples and three duration-qualified first recordings generated via actual Xiaomi calls, locally transcribed and ingested through normal product APIs. All remain waiting for review. Remaining27 synthesis and60 model QAs intentionally gated on actual sample acceptance.
- Task6 independent review / checks / handoff: review fixes integrated; current evidence and remaining gates in INTEGRATION_ACCEPTANCE.md. No claim of full end-to-end acceptance.

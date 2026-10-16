# Remember Me Engineering Roadmap

2026-10-16 本人授权 [iOS 采集与 Android 花园对齐](../architecture/ios-android-capture-garden-parity-2026-10-16.md)：一次保存、持久草稿、转写校对与累计人物任务，以及原生花田／花瓣阅读／内容侧面等体验。沿用已批准范围，不改变完整 Hardware／Legacy 阶段的条件状态。源码与验证、部署情况分别记录。

2026-10-16 本人已确认并要求启动[持续采集／重点区间](../architecture/wearable-priority-capture-2026-10-16.md)：iOS 实时音频接收、重点开关、后台完整重点保留和普通记忆归并。此次授权只覆盖这条链路；佩戴自动开录与物理单按语义待真实硬件确认，不改变完整 Phase 4 的条件状态。

Execution baseline: [current delivery model](../team/00_TEAM_OWNERSHIP.md). Product goals: [PRD v3.0](../PRD/Remember_Me_PRD_v3.0.docx). This file records phase status and exit gates; staffing is assigned per delegated Issue, not by phase or service.

## Phase status

| Phase | Status | Product goal | Exit gate |
| --- | --- | --- | --- |
| Phase 1 — Golden Path | **COMMITTED / NOW** | Make a real voice actually enter Remember Me | Real-device recording → Backend/STT → AI Memory → the same mobile client shows a real Memory |
| Phase 2 — Core Twin | **iOS-first slice AUTHORIZED / IN PROGRESS** | Move from "it records" to "it is starting to understand me" | Person Model + Evidence Twin + Original Router demonstrable |
| Phase 3 — Calibration + Voice | **iOS-first calibration and local Voice slices AUTHORIZED / IN PROGRESS** | Compare a locked Twin answer with a real answer and create a "sounds like me" perception | Locked answer → human Episode → typed diff; separate Voice grant + own sample + local Twin speech |
| Phase 4 — Hardware + Legacy | **BACKLOG / CONDITIONAL** | Prove the recording device's value and complete the entrustment narrative | Hardware Capture + Handover/Grant/Legacy core path |

Reading Phase 2–4 alone does not authorize starting them. The Product Owner has explicitly authorized the iOS-first evidence Twin and local Voice slice in [the Twin proposal](../architecture/twin-voice-contract-proposal.md), then the locked-answer calibration slice in [the calibration proposal](../architecture/calibration-contract-proposal.md). Full unattended calibration and Capture Planner, Legacy, and cloud deployment remain planned.

**Approved iOS-first scope:** [Issue #75](https://github.com/ztjklt/Remember-Me/issues/75) authorized local STT, evidence-backed memories and the seven-domain model. The later [Twin and Voice decision](../architecture/twin-voice-contract-proposal.md) authorizes evidence retrieval, Original/Simulation/Unknown routing, and separately consented local voice playback. It does not activate recipient accounts, Legacy, cloud deployment, or the full calibration phase.

## Phase 1 — Golden Path (COMMITTED)

The end-to-end proof: `real recording → upload → Episode → STT → Memory extraction → real Memory on the recording client`.

Android and iOS are the two active client tracks. 刘修贤 leads Android; 张天霁 leads iOS. 康欣 and 王昊宇 have no standing queue and help only through an explicitly assigned small Issue when available. The shared path is built in runnable slices: phone recording and local file; upload and durable Episode; STT and structured Memory extraction; status/result readback on the same client. Backend, AI Core, and Voice name logical capabilities and existing code areas, not permanent people or mandatory separate deployments. Neither client waits for the other to finish an intermediate slice.

Phase 1 is not complete until one real device records, uploads, and reads back a real extracted Memory — not a Mock or stubbed response. The other client track does not repeat this gate merely to release the first demo.

## Phase 2 — Core Twin (iOS-first slice authorized)

Person Model and Temporal Memory Graph over real Episodes; Memories screen on real data; Evidence Retrieval; Twin Agent with explicit provenance; Original Router preferring direct subject statements over simulation; memory correction and deletion propagating to derived data.

## Phase 3 — Calibration + Voice (iOS-first slices authorized)

Calibration Agent comparing a locked Twin answer against the human answer across Decision, Reasoning, Value Priority, Emotional Reaction, and Expression; Capture Planner driven by Information Gain × Importance × Uncertainty × Time Urgency ÷ Interaction Cost; Voice consent gate, speaker verification, quality assessment, clean segment selection, dataset, profile, provider adapter, and Twin Voice playback.

## Phase 4 — Hardware + Legacy (BACKLOG / CONDITIONAL)

Work 3200 / recording device integration through a capability-based adapter with a working no-hardware fallback; Marker support only if the official SDK exposes it; Digital Handover grants, activation policy, and the Recipient experience under Legacy state.

## Parallelization rules

A member who finishes their current phase may prepare non-blocking skeletons in the next phase — UI shells, schemas, adapters, test fixtures — but must not freeze a cross-module implementation alone. Phase 2/3 preparation never justifies skipping the Phase 1 Golden Path. The main path is integrated first; any peripheral feature that breaks it is reverted or flagged off.

Undecided external dependencies (STT provider, Voice provider, Work 3200 SDK) are isolated behind adapters and must not block internal contract, Mock, or Stub work.

2026-10-15 当前会话新增批准：见 [声纹、托付与人物模型 v0.12](../architecture/voiceprint-personal-model-contract-v0.12.md)。包括同手机多人对话，人工照护人核验的托付切片；硬件和自动死亡核验仍未启用。

2026-10-16 当前会话新增批准：见[主用户与亲友／游客双模式](../architecture/guest-access-contract-2026-10-16.md)。本轮 iOS 同机游客只读花园与范围内文字／语音 Twin，使用独立后端会话；主用户密码复验后才能恢复管理权限。跨设备邀请与互联网公开访问另行规划。

2026-10-16 当前会话追加修订并启动：[游客暗号托付与 Twin 内设置](../architecture/guest-entrustment-contract-2026-10-16.md)。亲友以游客使用，不绑定接收者账号；本人留下具体私密暗号并确认专属来源，游客在聊天中说出后进入对应记忆库。原账号计划不自动扩大权限，未来交接仍需既有核验；不代表完整 Legacy 或自动身后判定已完成。

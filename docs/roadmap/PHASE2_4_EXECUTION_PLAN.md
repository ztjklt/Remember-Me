# Phase 2–4 execution plan

This plan turns the Phase 2–4 backlog into an ordered delivery path for the four module owners. It follows PRD v3.0, the Team Development Guide, the [roadmap](ROADMAP.md), and the existing Phase 2–4 Issues. The Product / Integration Owner has set **2026-09-26 (Asia/Singapore)** as the target for completing all phases. This is a target, not evidence that a phase has passed its gate.

**Status on 2026-09-25:** Phase 1 remains the only committed workstream and has not passed its real-device gate. Phase 2 is planned; Phase 3 is planned; Phase 4 is conditional backlog. On the evidence currently in this repository, completing all four gates by 2026-09-26 is not feasible: Phase 1 Android upload and real-device acceptance remain open, Backend-to-AI integration has an identified failure, and the Voice provider, Work 3200 capability, and Legacy activation verification depth are undecided. Bring any completed off-repository work and verification into the PRs before reassessing this forecast. No phase is marked complete from fixture output, a UI shell, or an unverified provider integration.

## Delivery rule and immediate decision path

1. Finish the Phase 1 real-device path and record its evidence under [#21](https://github.com/ztjklt/Remember-Me/issues/21). The current blockers are Android [#6](https://github.com/ztjklt/Remember-Me/issues/6) and [#7](https://github.com/ztjklt/Remember-Me/issues/7), Backend [#48](https://github.com/ztjklt/Remember-Me/issues/48) and [#47](https://github.com/ztjklt/Remember-Me/issues/47), and integration [#14](https://github.com/ztjklt/Remember-Me/issues/14). AI Core [#2](https://github.com/ztjklt/Remember-Me/issues/2) must also be verified with a real transcript. The optional hardware adapter [#3](https://github.com/ztjklt/Remember-Me/issues/3) does not displace this path.
2. While the active path runs, owners may prepare independent UI shells, schemas, adapter seams, and deterministic fixtures for later phases. Preparation must not freeze a cross-module wire shape or introduce an unconfirmed provider or SDK capability.
3. After each gate passes, the Product / Integration Owner records the evidence and an explicit activation decision in the corresponding integration Issue, then updates the roadmap and `blocked` labels. A date alone does not activate a phase or waive a gate.
4. Integrate each vertical slice on `develop` through an owner PR. Require Code Owner approval, the protected checks, exact local verification, Contract impact, consent/privacy impact, and a rollback note. Preserve the working Android Compose client and replace Mock bindings incrementally.

### 2026-09-25 to 2026-09-26 triage

| When | Owner action | Evidence to publish |
| --- | --- | --- |
| 2026-09-25 | 张天霁 confirms each Owner's availability, a real Android device, STT and AI provider access, Voice provider readiness, Work 3200 SDK/device availability, and Legacy activation decision owner. | One status update on #21 listing available resources and unresolved dependencies; no provider or SDK is inferred from a placeholder. |
| 2026-09-25 | 刘修贤 focuses on #6/#7; 王昊宇 on #48/#47 and real STT; 康欣 on real-transcript extraction; 张天霁 on #14 integration and PR review. Later-phase Owners prepare only independent fixtures, sketches, or interface proposals. | Exact PRs, local commands/results, device/provider used, and the first failing hop for the Phase 1 path. |
| 2026-09-26, before any Phase 2 implementation | 张天霁 runs the Phase 1 gate and records pass or fail. If it passes, decide explicitly whether to activate Phase 2. | Same `episode_id` across real-device Capture, Backend, AI, and Android; corresponding PR/commit and failure-path evidence. |
| 2026-09-26 deadline | 张天霁 reports each phase as passed, partial demonstration, or blocked; names the next Owner action. | Gate evidence links and missing conditions. No calendar-driven status promotion. |

| Checkpoint | Required decision or evidence | Result if missing |
| --- | --- | --- |
| Phase 1 → 2 | Real Android recording → upload → persisted Episode → real STT → AI Memory → the same Memory shown on Android | Continue Phase 1; Phase 2 remains preparation only |
| Phase 2 → 3 | Versioned Phase 2 Contract and evidence-backed Twin on real Episodes, including Original routing and correction/deletion invalidation | Continue Phase 2; Phase 3 remains preparation only |
| Phase 3 → 4 | Locked-answer calibration changes a later result; separately consented Voice works and revocation fails safely | Continue Phase 3; Phase 4 remains conditional |
| Phase 4 exit | Confirmed device capability and real device run, plus scoped Legacy grant, activation, frozen baseline, revocation, and audit | Record partial work; do not declare Phase 4 complete |

## Phase 2 — Core Twin

**Outcome:** A second real Episode updates a time-aware Person Model; an unseen Twin answer cites accessible evidence and is labelled ORIGINAL only when direct subject material answers it. Correction or deletion changes subsequent results without losing source history.

| Order | Owner and Issue | Deliverable and integration handoff |
| --- | --- | --- |
| 0 | 康欣 [#18](https://github.com/ztjklt/Remember-Me/issues/18), 王昊宇 [#19](https://github.com/ztjklt/Remember-Me/issues/19), 刘修贤 [#20](https://github.com/ztjklt/Remember-Me/issues/20) | Supply non-binding graph/persona, API/policy, and Android-consumer sketches plus common two-Episode/conflict/deletion fixtures. These are design inputs, not separate wire contracts or Phase 2 implementation. |
| 1 | 张天霁 [#23](https://github.com/ztjklt/Remember-Me/issues/23), reviewed by all module owners | Use those inputs to propose the minimum versioned Memory, graph, persona, evidence, Twin policy/query, correction/deletion, and invalidation shapes. Validate shared success, sparse-evidence, conflict, denial, and deletion fixtures before approval. Do not deepen the frozen v0.1 contract unilaterally. |
| 2 | 康欣 [#18](https://github.com/ztjklt/Remember-Me/issues/18) | Build a Temporal Memory Graph with source Episode and effective time; populate seven Person Model domains while keeping third-party material separate. Add counter-evidence, confidence, model version, and changed/context-dependent/unresolved conflict states. Prove a second Episode updates rather than overwrites history. |
| 3 | 王昊宇 [#19](https://github.com/ztjklt/Remember-Me/issues/19) | Persist and serve versioned Memory/Graph/Persona data; provide policy-aware evidence retrieval and Twin Query transport. Implement correction/deletion invalidation through derived facts, retrieval, and caches before recalculating coverage. Backend owns authorization, not Person Model reasoning. |
| 4 | 刘修贤 [#20](https://github.com/ztjklt/Remember-Me/issues/20) | Extend the Phase 1 real-Memory screen to show evidence and Coverage; add Twin question, loading/error, evidence, and textual ORIGINAL/SIMULATION states. Wire correction/deletion to Backend with visible refresh. Keep TalkBack, large text, and one-handed use in the verification path. |
| 5 | 张天霁 [#24](https://github.com/ztjklt/Remember-Me/issues/24) | On `develop`, ask an unseen question over real Episodes, inspect cited evidence and Original routing, then correct/delete a source and confirm downstream result and coverage change. Record the real-device and service evidence before accepting Phase 2. |

**Parallel work:** After the Phase 2 Contract is approved, AI Core graph/model and Backend persistence may advance in parallel against the same fixtures. Android shells can be prepared earlier, but real-data wiring follows the stable APIs. The minimum demonstrable slice is two Episodes → evidence-backed answer → visible ORIGINAL/SIMULATION label; correction/deletion invalidation is required for the full gate.

## Phase 3 — Calibration and Voice

**Outcome:** Calibration compares a Twin answer locked before seeing the human answer and changes a later evidence-backed result. Separately authorized Voice can play approved Twin text; revoked consent, third-party audio, insufficient quality, and provider failure fail safely.

| Order | Owner and Issue | Deliverable and integration handoff |
| --- | --- | --- |
| 1 | 张天霁 [#25](https://github.com/ztjklt/Remember-Me/issues/25), reviewed by all module owners | Approve versioned calibration and Voice boundaries with fixtures for locked answer, five-dimension diff, model update, follow-up, independent Voice consent, sample/profile/status, revocation, and errors. Provider metadata remains non-normative; Android receives no provider secrets. |
| 2A | 康欣 [#27](https://github.com/ztjklt/Remember-Me/issues/27) | Enforce immutable Twin-answer lock before accepting the human answer. Classify model error, context dependence, genuine change, and insufficient evidence across Decision, Reasoning, Value Priority, Emotional Reaction, and Expression. Produce traceable model updates and high-value follow-ups; reject malformed output. |
| 2B | 王昊宇 [#28](https://github.com/ztjklt/Remember-Me/issues/28) | Gate Voice by separate consent; verify speaker and quality, select clean subject-only segments, create dataset/profile, and call clone/TTS through server-side adapters. Persist provenance and audit; make revocation and deletion invalidate derived Voice assets. Use a deterministic fake adapter until a provider is selected and verified. |
| 3 | 刘修贤 [#26](https://github.com/ztjklt/Remember-Me/issues/26) | Connect calibration question, locked answer, human answer, diff, and follow-up; connect Voice consent, seed, quality, confirmation, re-record/revoke, and Twin Voice playback. Keep text and audio answer state consistent and show denial, offline, retryable, and terminal failures. |
| 4 | 张天霁 [#29](https://github.com/ztjklt/Remember-Me/issues/29) | Verify calibration changes a later answer without erasing evidence, then run consent → clean subject sample → Voice profile → approved text → Android playback. Force revoked consent, third-party audio, low quality, and provider failure; inspect audit and no-access behavior. |

**Parallel work:** Calibration and Voice service work may proceed concurrently after the shared Contract is approved. Voice-provider selection is a Product decision before the real Voice gate; an adapter or fake profile does not satisfy the gate. The minimum demonstrable slice is locked-answer calibration plus separately consented confirmation playback; the full gate also requires the negative consent and quality paths.

## Phase 4 — Hardware and Legacy

**Outcome:** Confirmed recording hardware enhances the same Episode path while phone-only Capture stays complete. Handover activates scoped Recipient access without changing the historical Subject model; revocation and denied access propagate through APIs, caches, Voice, and UI.

| Order | Owner and Issue | Deliverable and integration handoff |
| --- | --- | --- |
| 0 | 张天霁 | Record a Phase 4 go/no-go decision, the official Work 3200 capability evidence, and the chosen depth of Legacy activation verification. If hardware evidence is unavailable, retain phone fallback and report the hardware gate as unverified; do not invent markers, live audio, or background recording. |
| 1 | 张天霁 [#30](https://github.com/ztjklt/Remember-Me/issues/30), reviewed by all module owners | Approve versioned capability, sync, grant scope, activation, revocation, audit, and baseline-freeze fixtures. Keep Subject, Actor, Steward, Contributor, and Recipient distinct. Include no-device, denial, revoked-grant, and migration cases. |
| 2A | 刘修贤 [#31](https://github.com/ztjklt/Remember-Me/issues/31) | Implement only confirmed device capabilities behind the adapter, with disconnect/retry/deduplicated sync and the full phone fallback. Add Handover and scope-aware Recipient UI; Legacy Home presents Her Voice, Her Life, Important People, and For You before Ask Her. |
| 2B | 王昊宇 [#33](https://github.com/ztjklt/Remember-Me/issues/33) | Provide per-recipient grants, activation policy/state, audit, denial, expiry/revocation, and scope checks at each sensitive endpoint. Trigger a versioned baseline freeze and invalidate access after revocation. A grant never creates new legal authority or Subject intent. |
| 2C | 康欣 [#32](https://github.com/ztjklt/Remember-Me/issues/32) | Freeze the historical Personality Baseline at activation. Keep post-activation world/Recipient context separate; preserve evidence and Original routing under grant scope. Reject Recipient-driven Person Model mutation. |
| 3 | 张天霁 [#34](https://github.com/ztjklt/Remember-Me/issues/34) | Verify phone-only and confirmed-device Capture through the same Episode path, then scoped grants, activation, denied access, revocation, audit, frozen baseline, and blocked Recipient mutation. Claim the hardware portion only after a real device run. |

**Parallel work:** Grant policy, frozen-model behavior, and UI shells can be prepared independently after the Phase 4 Contract is approved. Hardware implementation waits for official capability evidence. If the device or SDK is unavailable by the deadline, the honest deliverable is a documented phone-only fallback and an unpassed hardware gate; a simulated device is useful for tests but is not hardware acceptance.

## Deadline control and reporting

The 2026-09-26 target requires all four phase gates to pass in sequence; the current evidence does not support a forecast that this can happen by that date. The Product / Integration Owner maintains one visible status for each gate: **passed with evidence**, **blocked with owner and next action**, or **partial demonstration**. The deadline report must name the exact commit/PR, device and provider used, verification command/result, and missing gate evidence. Never promote a partial demonstration to a completed phase.

For a time-limited demonstration, preserve a single working path in this order: Phase 1 real Memory, Phase 2 evidence-backed Twin, Phase 3 calibration and independently consented Voice, then Phase 4 optional hardware and scoped Legacy. Keep incomplete peripheral work behind adapters or a flag so it cannot break the accepted path. This order prioritizes truthful end-to-end evidence; it does not change the full gate definitions or activate later phases by itself.

# Remember Me Engineering Roadmap

Execution baseline: [current delivery model](../team/00_TEAM_OWNERSHIP.md). Product goals: [PRD v3.0](../PRD/Remember_Me_PRD_v3.0.docx). This file records phase status and exit gates; staffing is assigned per delegated Issue, not by phase or service.

The ordered work, dependencies, verification, and 2026-09-26 target for the later phases are recorded in the [Phase 2–4 execution plan](PHASE2_4_EXECUTION_PLAN.md). That target does not change the phase statuses or waive their exit gates.

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

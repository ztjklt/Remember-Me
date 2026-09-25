# Remember Me Engineering Roadmap

Execution baseline: [current delivery model](../team/00_TEAM_OWNERSHIP.md). Product goals: [PRD v3.0](../PRD/Remember_Me_PRD_v3.0.docx). This file records phase status and exit gates; staffing is assigned per delegated Issue, not by phase or service.

## Phase status

| Phase | Status | Product goal | Exit gate |
| --- | --- | --- | --- |
| Phase 1 — Golden Path | **COMMITTED / NOW** | Make a real voice actually enter Remember Me | Real-device recording → Backend/STT → AI Memory → Android shows a real Memory |
| Phase 2 — Core Twin | **PLANNED / NEXT** | Move from "it records" to "it is starting to understand me" | Person Model + Evidence Twin + Original Router demonstrable |
| Phase 3 — Calibration + Voice | **PLANNED** | Verify fidelity and create a "sounds like me" perception | Calibration feeds the model back + Voice Seed/Clone/Twin Voice |
| Phase 4 — Hardware + Legacy | **BACKLOG / CONDITIONAL** | Prove the recording device's value and complete the entrustment narrative | Hardware Capture + Handover/Grant/Legacy core path |

Reading Phase 2–4 does not authorize starting them. Phase 1 Golden Path is the only committed workstream.

## Phase 1 — Golden Path (COMMITTED)

The end-to-end proof: `real recording → upload → Episode → STT → Memory extraction → real Memory in Android`.

The path is built in runnable slices: phone recording and local file; upload and durable Episode; STT and structured Memory extraction; status/result readback in Android. Backend, AI Core, and Voice name logical capabilities and existing code areas, not permanent people or mandatory separate deployments. The Product / Integration Owner works across slices and delegates bounded blockers through Issues and PRs.

Phase 1 is not complete until a real device records, uploads, and reads back a real extracted Memory — not a Mock, not a stubbed response.

## Phase 2 — Core Twin (PLANNED / NEXT)

Person Model and Temporal Memory Graph over real Episodes; Memories screen on real data; Evidence Retrieval; Twin Agent with explicit provenance; Original Router preferring direct subject statements over simulation; memory correction and deletion propagating to derived data.

## Phase 3 — Calibration + Voice (PLANNED)

Calibration Agent comparing a locked Twin answer against the human answer across Decision, Reasoning, Value Priority, Emotional Reaction, and Expression; Capture Planner driven by Information Gain × Importance × Uncertainty × Time Urgency ÷ Interaction Cost; Voice consent gate, speaker verification, quality assessment, clean segment selection, dataset, profile, provider adapter, and Twin Voice playback.

## Phase 4 — Hardware + Legacy (BACKLOG / CONDITIONAL)

Work 3200 / recording device integration through a capability-based adapter with a working no-hardware fallback; Marker support only if the official SDK exposes it; Digital Handover grants, activation policy, and the Recipient experience under Legacy state.

## Parallelization rules

A member who finishes their current phase may prepare non-blocking skeletons in the next phase — UI shells, schemas, adapters, test fixtures — but must not freeze a cross-module implementation alone. Phase 2/3 preparation never justifies skipping the Phase 1 Golden Path. The main path is integrated first; any peripheral feature that breaks it is reverted or flagged off.

Undecided external dependencies (STT provider, Voice provider, Work 3200 SDK) are isolated behind adapters and must not block internal contract, Mock, or Stub work.

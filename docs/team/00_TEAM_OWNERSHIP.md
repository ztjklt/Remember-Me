# Remember Me Team Ownership

This document converts the Remember Me PRD v2.0 into an engineering ownership baseline. The current Android prototype is a runnable product-flow prototype, not a completed product. The team will extend it rather than rewrite it.

## Ownership

| Member | GitHub | Role | Sole ownership domain |
| --- | --- | --- | --- |
| 张天霁 | `ztjklt` | Product Repo Integration Owner | PRD, product experience, contract baseline, review, integration acceptance, demo |
| 刘修贤 | `shuziyuxingxing-stack` | Android Hardware SDK Owner | Android UI and UX, real capture, client state, Work 3200 and recording-device adapter |
| 康欣 | `centraler` | AI Core Person Model Owner | Post-STT AI, memory, temporal graph, person model, Twin, calibration, capture planner |
| 王昊宇 | `qingtian-4` | Backend Voice Infrastructure Owner | API, database, storage, auth, jobs, cloud sync, voice seed, clone, and TTS |

Each module has one final owner. Members may help across boundaries but must not create duplicate interfaces or competing implementations.

## Integration path

`Android and Hardware → Backend Ingestion → STT and AI Core → Memory and Person Model → Twin → Voice → Backend → Android`

The Phase 1 Golden Path is real Android recording, backend upload, Episode creation, STT, memory extraction, and display of a real Memory in Android. Each completed segment is integrated and accepted immediately rather than deferred to the end.

## Product and engineering rules

- Freeze the minimum shared contract before feature work. Extend fields deliberately; do not create incompatible private data models.
- Keep heavy processing asynchronous with explicit progress and failure states.
- Distinguish subject statements, third-party observations, AI inference, and calibration evidence.
- Twin answers must include evidence and provenance. Use Original before Simulation when direct source material exists.
- Voice clone consent is separate from recording consent. Third-party speech is excluded from subject voice datasets.
- No hardware is required for the core app path; device capabilities enhance rather than block it.

## Phases

1. Repo and Contract: monorepo, Android import, collaborators, branches, v0.1 contract, and CI.
2. Golden Path A: real recording through real Memory display.
3. Person Model: explainable update from a second recording.
4. Twin: evidence retrieval and Original or Simulation routing.
5. Voice: separate consent, seed, clone or TTS, and playback.
6. Calibration: locked Twin answer, human answer, diff, model update, and next question.
7. Hardware: capability-based Work 3200 or recording-device adapter.
8. Handover and Legacy: competition-scope permissions and key UI.

## Required first instruction for module owners

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.


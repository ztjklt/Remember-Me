# Remember Me Team Ownership

This document is the engineering ownership baseline for [PRD v3.0](../PRD/Remember_Me_PRD_v3.0.docx) under the [Team Development Guide v1.0](Remember_Me_Team_Development_Guide_v1.0.docx). The current Android prototype is a runnable product-flow prototype, not a completed product. The team extends it rather than rewrites it.

## Ownership

| Member | GitHub | Role | Sole ownership domain | Primary deliverables |
| --- | --- | --- | --- | --- |
| 张天霁 | `ztjklt` | Product / Repo / Integration | PRD, priority, contract freeze, acceptance, PR and integration, demo | PRD v3.0 and product principles, contract approval, Golden Path integration on `develop`, Phase Gate acceptance, demo script and scope control |
| 刘修贤 | `shuziyuxingxing-stack` | Android / Hardware | Android client, Capture, Local Audio, Upload, Hardware Adapter | Compose client, real recording, audio persistence, upload and processing states, capability-based device adapter |
| 康欣 | `centraler` | AI Core / Person Model | Memory, Graph, Person Model, Twin, Calibration, Capture Planner | Schema-validated extraction, temporal graph, seven person domains, evidence retrieval, Original Router, calibration |
| 王昊宇 | `qingtian-4` | Backend / Voice / Infrastructure | API/Auth/DB/Storage/Jobs, STT plumbing, Voice pipeline, deployment and observability | Upload and Episode API, async jobs and status, consent and subject isolation, voice pipeline and provider adapters |

Each module has one final owner. Members may help across boundaries but must not create duplicate interfaces or competing implementations.

**Boundary rule:** 刘修贤 does not own Person Model algorithms. 康欣 does not own Android pages or account/storage. 王昊宇 does not decide Person Model product logic. Cross-module contracts are coordinated and frozen by 张天霁. Covering for each other is allowed; a second owner is not.

## Phase responsibility boundaries

| Phase | Status | 刘修贤 | 康欣 | 王昊宇 | 张天霁 |
| --- | --- | --- | --- | --- | --- |
| 1 — Golden Path | COMMITTED / NOW | Real capture, file persistence, upload, Episode and Processing states | Schema-validated Memory Extractor, provenance, fixtures | Upload API, Episode persistence, STT plumbing, async jobs, result API | Contract freeze, integration on `develop`, Phase 1 acceptance |
| 2 — Core Twin | PLANNED / NEXT | Memories on real data, Person Model and Coverage UI, Twin client, correction/deletion UI | Temporal graph, seven domains, Conflict Detector, Evidence Retrieval, Twin Agent, Original Router | Memory/Graph/Persona API, Twin Query API, recompute and cache invalidation | Evidence Twin acceptance, UX review of Memories and Twin |
| 3 — Calibration + Voice | PLANNED | Calibration UI, Voice Seed/Confirmation UI, Twin Voice player | Calibration Agent, follow-up questions, Capture Planner | Voice consent, speaker verification, dataset, profile, clone/TTS adapter, audit | Calibration and Voice acceptance, consent-scope review |
| 4 — Hardware + Legacy | BACKLOG / CONDITIONAL | Work 3200 adapter, capability probe, Hardware fallback, Handover/Legacy client pages | Legacy Mode evidence and Original Router behaviour, baseline freeze | Trusted People, grant scope, activation state, audit, Legacy policy gate | Legacy acceptance, competition scope control |

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

## Required first instruction for module owners

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, the Team Development Guide, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.

Phase status, owners, and exit gates are tracked in [docs/roadmap/ROADMAP.md](../roadmap/ROADMAP.md).

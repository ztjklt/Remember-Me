# Architecture

Baseline: [PRD v3.0](../PRD/Remember_Me_PRD_v3.0.docx) and the [2026-09-26 dual-client delivery amendment](../team/00_TEAM_OWNERSHIP.md). Android / Kotlin / Jetpack Compose is the existing implementation; iOS is an authorized parallel client track. Both use the same Backend Contract.

## End-to-end path

`iOS or Android Capture → API / Auth → Episode and Job → STT → AI Core → Memory / Graph / Person Model → Twin → optional Voice → the requesting client`

Raw Episodes are persisted before AI or Voice runs, so a downstream failure can never lose the original life record.

For the Phase 1 build, treat this as one shared processing path: either client records and calls the Backend API; Backend preserves the Episode, runs STT and structured extraction behind provider adapters, then returns status and Memory to that client. Backend, AI Core, and Voice are logical responsibilities and existing code areas, not mandatory staffing or deployment splits. Simplify deployment only when it helps the runnable path; preserve the shared Contract and data boundaries while doing so.

## Layers

| Layer | v3.0 components |
| --- | --- |
| Android Client | Kotlin, Jetpack Compose, Material 3, Compose Navigation, ViewModel/StateFlow, Repository, Local Audio, Hardware Adapter |
| iOS Client | New client track; use the same Backend Contract, consent semantics, and provenance presentation without duplicating server processing |
| API / Auth / Policy | Identity, Subject/Actor, device, consent, grant, rate limit, audit |
| Orchestrator | Event bus, task queue, state machine, worker scheduling, idempotency, retry, policy context |
| AI Workers | STT, Speaker Gate, Memory, Persona, Conflict, Calibration, Capture Planner, Twin |
| Memory Layer | PostgreSQL + pgvector + Temporal Graph + Object Storage |
| Voice Layer | Voice samples, profile, provider adapter, clone, TTS — under independent consent |
| Observability | Trace, model/prompt/schema/provider version, cost, latency, error, human correction |

## Android client

Single `app` module, layered Compose. UI consumes page state and domain models only; pages never call a vendor SDK. `MemoryRepository`, `PersonModelRepository`, `LegacyRepository`, `AudioCaptureService`, `SpeechToTextService`, `TwinService`, `VoiceCloneService`, and `HardwareCaptureAdapter` are the replacement points, and real implementations swap in behind them without changing product semantics.

`Subject` (the modeled person) and `Actor` (whoever currently operates the app) are distinct types, so Creator Mode and Legacy Mode can move between actors around one Subject. Important page states use `Loadable` to express Loading, Content, Empty, and Error.

Real recording writes to client-private storage. Permission denial, offline, upload failure, and processing failure each need an explicit state — no silent swallowing on either client.

## Service boundaries

- Backend proposes PostgreSQL/Supabase plus Object Storage; provider choices stay replaceable. Episode states: `uploaded → transcribing → extracting → modeling → ready/failed`.
- Cross-service calls carry idempotency, retry, trace id, and audit. Every request states `actor_id`, `subject_id`, role/relationship, consent, `grant_scope`, and `legacy_state`.
- AI Core takes Episode/Transcript as its input boundary and returns structured memory, graph, and persona updates as its output boundary. Structured output must be schema-validated before persistence, and every important inference keeps provenance, evidence, confidence, and model version. Twin must answer from evidence retrieval — a fixed persona prompt is not memory.
- Voice is decoupled from Person Model with its own consent, dataset, profile, and audit. Pipeline: Consent Gate → Speaker Verification → Quality → Clean Segment → Dataset → Voice Profile/Clone → TTS. Third-party audio never enters a Subject Voice Dataset, and Android receives only status and playable audio.

## Adapter rule

Every external provider — STT, LLM, vector/graph store, voice clone, hardware — sits behind an adapter. Neither mobile client holds provider secrets; both call only the Backend Contract. Hardware uses a capability profile, and the phone microphone path stays functional without an external device.

## Decision records

| ADR | Decision | Status |
| --- | --- | --- |
| [ADR-0001 — Backend platform, data, storage, auth, and failure model](backend-adr.md) | Language, deployment shape, data layer, migrations, object storage, upload transport, auth boundary, job model, provider boundaries, client security, failure model, idempotency, observability, local verification | Proposed — awaiting ratification (Issue #13) |

An ADR records a decision and its rejected alternatives so modules cannot each bind to a different assumed architecture. An ADR does not override `packages/contracts`.

## Relationship to contracts

`packages/contracts` is the integration source of truth and outranks this document. Architecture records added here must not silently override it; a conflict is resolved by a contract proposal, not by an architecture note.

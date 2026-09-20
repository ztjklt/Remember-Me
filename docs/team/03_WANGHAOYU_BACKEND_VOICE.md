# 王昊宇 Backend Voice and Infrastructure Task Brief

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, the Team Development Guide, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.

## Goal

Build the service foundation shared by Android and AI Core, then integrate voice as a separately consented sensitive capability.

## Phase 1 — COMMITTED

1. Establish the Upload API, Episode, Object Storage, STT plumbing, Processing Job and Status, and database persistence.
2. Establish the minimum Auth / Subject / Actor / Consent structure, and guarantee that an Episode is saved before AI runs.
3. Send transcript and Episode context into AI Core, and persist the returned Memory result.
4. Provide a status and result API Android can consume, with retry, idempotency, and logging.

**Definition of done:** real audio upload → Episode → STT → AI task → persist → Android readback.

## Phase 2 — PLANNED

Memory, Graph, and Persona APIs with `model_version`. Evidence retrieval plumbing. Twin Query API with policy context and Original/Simulation `response_type`. Dependency recompute and cache invalidation triggered by memory correction or deletion.

## Phase 3 — PLANNED

Voice consent, speaker verification, quality assessment, clean segment selection, dataset, and voice profile. Voice Provider Adapter with clone and TTS; provider secrets stay server-side. Voice audit, sample provenance, third-party audio exclusion, and revocation/deletion handling. Async status APIs for calibration and voice toward Android.

## Phase 4 — BACKLOG / CONDITIONAL

Trusted People, grant scope, activation state, audit, and the Legacy policy gate. Voice grants with Recipient scope, where different Recipients may access different content. Implementation depth of Legacy activation verification is decided by competition time and compliance conditions.

## Voice boundary

Keep voice-clone consent separate from recording consent. Add speaker verification, quality assessment, clean segment selection, voice dataset, voice profile, provider adapter, and TTS incrementally. Never place third-party speech in the subject voice dataset. Treat deletion, access, and Legacy grants independently.

## Acceptance

Real audio creates an Episode, an asynchronous AI job persists results, Android reads status and result resources, and a later voice-provider loop honors separate consent. Submit migrations, API documentation, environment template, deployment notes, and tests.

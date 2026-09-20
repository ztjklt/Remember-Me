# 王昊宇 Backend Voice and Infrastructure Task Brief

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.

## Goal

Build the service foundation shared by Android and AI Core, then integrate voice as a separately consented sensitive capability.

## Phase 1 tasks

1. Establish the API, database, object storage, user and auth, consent, Episode, Memory, Person Model, and job foundations behind replaceable provider adapters.
2. Implement resumable or retryable audio upload, idempotent Episode creation, asynchronous processing status, and result persistence.
3. Expose the standard Episode and Transcript input to AI Core and stable status and result APIs to Android.
4. Provide development and staging environment guidance, migrations, `.env.example`, logs, and minimum monitoring without committing secrets.

## Voice boundary

Keep voice-clone consent separate from recording consent. Add speaker verification, quality assessment, clean segment selection, voice dataset, voice profile, provider adapter, and TTS incrementally. Never place third-party speech in the subject voice dataset. Treat deletion, access, and Legacy grants independently.

## Acceptance

Real audio creates an Episode, an asynchronous AI job persists results, Android reads status and result resources, and a later voice-provider loop honors separate consent. Submit migrations, API documentation, environment template, deployment notes, and tests.


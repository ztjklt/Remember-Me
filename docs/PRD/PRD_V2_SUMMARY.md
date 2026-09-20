# Remember Me PRD v2.0 Summary

Remember Me is a consent-first product for building a traceable record of how a person remembers, relates, decides, values, and expresses. It is not a transcription tool, an AI memorial, a legal proxy, or a claim of consciousness replication. The product begins while the subject can still participate, then may transition under prior authorization into a Legacy experience for designated recipients.

## Product north star

Increase verifiable Twin fidelity at an acceptable interaction cost. Do not optimize for recording hours, chat volume, or a misleading personality-completion percentage.

The central loop is `Capture → Extract → Model → Simulate → Compare → Correct → Capture`.

## Frozen product principles

- One Capture, Two Models: an authorized recording may support both the Person and Memory pipeline and the separately consented Voice pipeline.
- Original Before Simulation: use direct original evidence or voice when it answers the question; simulate only when evidence is insufficient, and label simulation clearly.
- Zero-Learning Capture: recording must remain usable for older, ill, mobility-limited, and low-digital-literacy users.
- The User Changes, the Person Does Not: keep Subject separate from Actor, Steward, Contributor, and Recipient throughout data, permissions, interface, and agent behavior.
- Raw Life Episodes remain the evidence base. Summaries and inferences never overwrite source history.
- Subject statements, third-party observations, AI inference, objective material, and calibration evidence remain distinct.
- The subject can inspect, correct, delete, export, and revoke consent for important data.
- Third parties cannot train, rewrite, or override a subject's Person Model or Voice without the subject's knowledge and authorization.
- Twin output cannot create a new authorization, will, medical decision, legal direction, or new expression of the subject's intent.
- Legacy activation freezes the Personality Baseline. New world context may be added without changing the historical person.

## Core architecture

1. Life Episodes store audio, transcript, time, speaker, source, and context as evidence.
2. The Temporal Memory Graph stores people, events, relationships, facts, effective time, and provenance.
3. The Person Model organizes Identity, Episodic Memory, Relationships, Preferences, Values and Beliefs, Decision Patterns, and Expression.
4. The Orchestrator routes events, policy context, dependencies, retries, idempotency, versions, and audit data to specialist workers.
5. Twin answering combines authorized retrieval, an Evidence Pack, Original or Simulation routing, an expression layer, and optional separately authorized Voice output.

Every important trait preserves context, confidence, source type, evidence, counter-evidence, effective time, status, and model version. Conflict and change over time are valid states rather than data to flatten.

## Consent and safety boundaries

Recording, Cloud Twin, Voice Clone, third-party contribution, Digital Handover, and Legacy access require distinct consent or grants. Voice data is a separate sensitive asset. Speaker verification and quality checks must prevent third-party speech from entering a subject's Voice Dataset.

Every sensitive operation evaluates Subject, Actor, relationship, consent, grant scope, and Legacy state. Deleting source evidence cascades to or invalidates dependent embeddings, graph facts, persona traits, calibration evidence, voice references, and caches before coverage or readiness is recalculated.

## Competition Golden Path

The competition implementation should prove a real end-to-end path:

`natural recording → real audio ingestion → transcript → Memory extraction → Person Model update → unseen question → evidence-backed Twin answer → Original before Simulation routing → separately consented Voice playback → visible provenance and model change`

Hardware, Digital Handover, and Legacy features build on this path. The app must remain complete without Work 3200 or recording hardware and enhance Capture through a capability-based adapter when hardware is available.

## Platform decision requiring confirmation

PRD v2.0 names an iOS and SwiftUI client in its architecture table. The current engineering baseline and existing prototype are Android and Jetpack Compose. The team is continuing Android for the competition build; a move to iOS would be a separate product and engineering decision, not an implicit requirement from this summary.


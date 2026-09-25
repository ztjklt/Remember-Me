# Remember Me PRD v3.0 Summary

Agent-readable orientation for [Remember Me PRD v3.0](Remember_Me_PRD_v3.0.docx), the current product Source of Truth. PRD v3.0 is an Android-first revision of v2.0: it does not redo the product definition, it moves the client engineering baseline from iOS/SwiftUI to Android/Kotlin/Jetpack Compose and brings the existing Android prototype into the real development path. Where any older repository document still names iOS, Swift, or SwiftUI as the current client, v3.0 wins.

Remember Me is a consent-first product for building a traceable record of how a person remembers, relates, decides, values, and expresses. It is not a transcription tool, an AI memorial, a legal proxy, or a claim of consciousness replication. The product begins while the subject can still participate, then may transition under prior authorization into a Legacy experience for designated recipients.

## Product north star

Increase verifiable Twin fidelity at an acceptable interaction cost. Do not optimize for recording hours, chat volume, or a misleading personality-completion percentage.

The central loop is `Capture → Extract → Model → Simulate → Compare → Correct → Capture`.

## Frozen product principles

These carry over from v2.0 unchanged and must not be deleted or rewritten without an explicit Product Owner decision.

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

## Roles and lifecycle

Subject (the modeled person), Actor/User (whoever operates the Android app, who may be the Subject or later a Recipient), Steward (a pre-designated digital caretaker acting only within grant scope), Beneficiary/Recipient (Legacy content receiver, access by grant scope), and Contributor (an authorized third-party observer whose content carries perspective and never overrides the Subject Person Model). The lifecycle remains Build Me → Entrust Me → Transition → Remember Me.

## Memory and person architecture

1. Layer 1 — Life Episodes: raw audio, transcript, time, source, speaker, and context; the evidence base.
2. Layer 2 — Temporal Memory Graph: people, events, relationships, facts, effective time, and provenance.
3. Layer 3 — Person Model: the system's current structured understanding. Seven domains: Identity, Episodic Memory, Relationships, Preferences, Values & Beliefs, Decision Patterns, Expression.

Every important trait preserves context, confidence, source type, evidence, counter-evidence, effective time, status, and model version. Conflict and change over time are valid states rather than data to flatten.

## Android-first v3.0 changes

| Area | v2.0 | v3.0 |
| --- | --- | --- |
| Primary client | iOS App | Android App (Android First) |
| UI technology | Swift / SwiftUI | Kotlin / Jetpack Compose / Material 3 |
| Client architecture | iOS Client | Compose Navigation + ViewModel/StateFlow + Repository |
| Accessibility | VoiceOver | TalkBack, large text, one-handed and voice-first |
| Local audio | iOS Local Audio | Android Local Audio / app-scoped storage |
| Hardware | Hardware Adapter | Android Hardware Adapter; Work 3200 capability probe + fallback |
| Starting point | Concept architecture | Existing runnable Mock Prototype continues as `apps/android` |

## Android information architecture

Home / Twin, Capture, Processing, Memories, Calibration, Handover, Legacy Home, Settings. Legacy Home deliberately leads with Her Voice, Her Life, Important People, and For You before Ask Her, so the experience is not reduced to a chatbot.

## Capture, Voice, and Agent Harness

Capture has three modes: Free Capture (user-triggered, the agent does not interrupt), Guided Capture (2–4 main questions plus dynamic follow-ups to fill high-value gaps), and Twin Calibration (Twin answers and locks first, then the human answers, then the diff is analyzed and the model updated). Recording must confirm receipt immediately; heavy STT, AI, and Voice work stays asynchronous; the app must remain complete without Work 3200.

Voice is a separate embodiment layer behind its own consent: Person Model decides what is said, Expression decides how, Voice decides whether it sounds like the person. Pipeline is Consent Gate → Speaker Verification → Quality Assessment → Clean Segment Selection → Voice Dataset → Voice Profile/Clone → TTS. Third-party speech must never enter a subject's Voice Dataset. Providers stay behind adapters; Android never binds directly to a vendor.

The logical model is an Agent Swarm, the engineering model is an Orchestrator plus specialist workers (Memory Extractor, Graph Updater, Persona Synthesizer, Conflict Detector, Calibration Agent, Capture Planner, Twin Agent). The first version should be one main LLM with prompt, tool, and JSON-schema workers, not a premature service split.

## Consent and safety boundaries

Recording, Cloud Twin, Voice Clone, third-party contribution, Digital Handover, and Legacy access each require distinct consent or grants. Voice data is a separate sensitive asset. Every sensitive operation evaluates Subject, Actor, relationship, consent, grant scope, and Legacy state. Deleting source evidence cascades to or invalidates dependent embeddings, graph facts, persona traits, calibration evidence, voice references, and caches before coverage or readiness is recalculated.

## Competition Golden Path

`natural recording → real audio ingestion → transcript → Memory extraction → Person Model update → unseen question → evidence-backed Twin answer → Original before Simulation routing → separately consented Voice playback → visible provenance and model change`

## Engineering phases

Product goals for the four phases are defined in the PRD; execution status and exit gates are recorded in the repository [roadmap](../roadmap/ROADMAP.md). Current work assignment follows the [single-path delivery model](../team/00_TEAM_OWNERSHIP.md), which supersedes fixed staffing in the original [Team Development Guide](../team/Remember_Me_Team_Development_Guide_v1.0.docx). Reading Phase 2–4 does not authorize starting them.

| Phase | Status | Product goal |
| --- | --- | --- |
| Phase 1 — Golden Path | COMMITTED / NOW | Move from Mock into the real loop |
| Phase 2 — Core Twin | PLANNED / NEXT | Form "the system really knows me" |
| Phase 3 — Calibration + Voice | PLANNED | Verify fidelity and form a "sounds like me" perception |
| Phase 4 — Hardware + Legacy | BACKLOG / CONDITIONAL | Lower Capture cost and complete the entrustment narrative |

## Open dependencies

Work 3200 SDK/API, the STT provider, and the Voice Clone provider are **not decided**. Keep each behind an adapter with a capability fallback, and do not treat unconfirmed device capabilities such as markers, live audio, or background recording as guaranteed. Provider secrets stay server-side; Android holds none of them.

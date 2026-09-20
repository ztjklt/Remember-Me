# 康欣 AI Core and Person Model Task Brief

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, the Team Development Guide, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.

## Goal

Build the interpretation and personality core so Episode transcripts produce validated, traceable memories and explainable person-model updates.

## Phase 1 — COMMITTED

1. Define the Episode/Transcript → Memory Extractor schema; output events, people, relationships, preferences, values, and emotions.
2. Preserve `source_type`, evidence, confidence, and other provenance fields; validate structured output against the schema.
3. Provide the minimum AI processing interface callable by Backend, plus deterministic test samples.
4. Never write free-form model output directly into the core store.

**Definition of done:** a real transcript reliably produces persistable Memory, and failures return a diagnosable error.

## Phase 2 — PLANNED

Temporal Memory Graph with entity, fact, and relation plus `valid_from`/`valid_to` and source Episode. All seven Person Model domains: Identity, Episodic Memory, Relationships, Preferences, Values & Beliefs, Decision Patterns, Expression. Persona traits supporting evidence, counter-evidence, context, confidence, time, status, and model version. Conflict Detector for changed, context-dependent, and unresolved contradiction. Evidence Retrieval with a Twin Agent that admits uncertainty when evidence is thin. Original Router preferring direct subject statements and skipping unnecessary simulation.

## Phase 3 — PLANNED

Calibration Agent comparing Decision, Reasoning, Value Priority, Emotional Reaction, and Expression. Boundary follow-up questions and trait updates that distinguish model error, context dependence, and genuine change of view. Capture Planner scoring Information Gain × Importance × Uncertainty × Time Urgency ÷ Interaction Cost. Further Tacit Pattern Mining and conflict refinement.

## Phase 4 — BACKLOG / CONDITIONAL

Personality Baseline frozen after Legacy activation; Recipient queries must not keep training the model into a new Subject. Recipient context is interaction context only and must never overwrite the subject's historical person. Evidence and the Original Router stay active in Legacy Mode.

## Next boundaries

Model Life Episodes, a Temporal Memory Graph, and the Person Model domains while allowing conflict and change over time. Twin output must include evidence and Original or Simulation routing. Calibration must lock the Twin answer before seeing the human answer. Use one main LLM with schema workers for the initial version.

## Acceptance

The same Episode produces schema-valid memory and persona updates, a second Episode can update the model with provenance, Twin responses expose evidence, and calibration completes lock, compare, update, and follow-up stages. Document schemas, prompt and model versions, test examples, and fallback behavior.

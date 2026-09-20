# 康欣 AI Core and Person Model Task Brief

You are the sole Owner of this module in the Remember Me team. First read the root PRD summary, TEAM OWNERSHIP, CONTRACTS, and existing code. Do not rewrite another member's module or change a cross-module Contract without approval. Complete your Phase 1 minimum loop first, verify it locally, then submit it through a feature branch and Pull Request.

## Goal

Build the interpretation and personality core so Episode transcripts produce validated, traceable memories and explainable person-model updates.

## Phase 1 tasks

1. Accept the standard Episode and Transcript input defined in `packages/contracts`.
2. Implement one schema-validated Memory Extractor for people, events, relationships, preferences, values, decision patterns, and expression evidence.
3. Preserve source type, evidence, confidence, model version, and failure details; never write free-form model output directly into the core store.
4. Provide deterministic samples and validation tests that backend and Android owners can use during integration.

## Next boundaries

Model Life Episodes, a Temporal Memory Graph, and Person Model domains while allowing conflict and change over time. Twin output must include evidence and Original or Simulation routing. Calibration must lock the Twin answer before seeing the human answer. Use one main LLM with schema workers for the initial version.

## Acceptance

The same Episode produces schema-valid memory and persona updates, a second Episode can update the model with provenance, Twin responses expose evidence, and calibration completes lock, compare, update, and follow-up stages. Document schemas, prompt and model versions, test examples, and fallback behavior.


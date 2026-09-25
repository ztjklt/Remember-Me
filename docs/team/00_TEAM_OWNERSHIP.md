# Single-path delivery and task delegation

Product / Integration Owner decision, 2026-09-26. This is the current execution model and a platform-scope amendment: iOS and Android are the two active client tracks. It supersedes the standing person-to-module assignments in the Team Development Guide v1.0, the original Phase 1 kickoff, and the individual task briefs. Those documents remain useful history for work already in progress; they do not assign future work automatically. PRD v3.0 remains the source of product behavior and consent rules; `packages/contracts` remains the shared interface source of truth.

## Two client tracks, one mainline lead

张天霁 (`@ztjklt`) drives both iOS and Android tracks and the shared processing path: chooses the next user-visible slice, integrates it, and decides when to ask for help. Two other contributors form an on-demand pool for bounded Issues when available. Nobody receives a permanent Backend, AI Core, or Voice queue. A directory or service name describes a code responsibility, not a permanent person or a requirement to deploy another service.

Phase 1 remains the only committed workstream: `real phone recording → upload → Episode persistence → STT → Memory extraction → the same client displays the real Memory`. Android has the existing runnable prototype; iOS is now an authorized parallel client track against the same Backend Contract. The first end-to-end demo may use either platform. The other track does not block it or require a duplicate device acceptance run. An intermediate demo may show a smaller slice, but must say which steps are real and which are fixtures. Phase 2–4 features still require a Product Owner decision.

## When to delegate

The mainline developer works across the repository. Open a separate Issue when a bounded task needs specialist design, independent investigation, or enough time that handing it off will speed the main path. Do not create an Issue merely to preserve a module boundary.

Each delegated Issue names one temporary task owner and states:

1. The concrete outcome and why the main path needs it.
2. Inputs, existing code or contract to reuse, and files or interface boundaries the task may change.
3. One observable acceptance result and the shortest relevant verification command or device step.
4. The expected handoff: a reviewable PR into `develop`, with setup notes if another machine must run it.

The contributor branches from current `develop`, works within that Issue, and opens a PR. The `develop` CI check must pass before merge; a second person's approval is not required for routine slices. The mainline lead can continue on both client tracks while the Issue is in flight, then pull `develop` after its PR merges. Shared Contract changes still need an Issue or proposal and Product / Integration Owner approval before implementation. Avoid parallel implementations of the same capability. `main` keeps its release review and CI checks.

Existing Issues and PRs keep their authors and review history. This decision does not silently cancel work already underway or turn a historical task brief into a new standing assignment. The Product / Integration Owner coordinates any explicit handoff that changes an active task.

## Keep verification proportional

For each PR, record the shortest relevant command or observed action and its result, plus any actual Contract or data impact. Reuse existing evidence; do not demand a long checklist, repeated cross-team sign-off, or another device run solely to reformat a report. Run a focused device check when native recording, permissions, storage, or lifecycle behavior changes, and once for the chosen end-to-end demo path. One person records that result; other contributors do not need to repeat it. A build, fixture, or emulator result is labeled as such.

The mainline lead checks the current end-to-end path at meaningful milestones and records the first failing step. A slice can move forward while another dependency is unfinished; the Phase 1 gate is met only after the complete real path works on one client. Keep recording consent, subject isolation, raw Episode preservation, provenance, model versions, explicit failures, and provider secrets behind server-side adapters. Voice cloning still needs consent separate from recording.

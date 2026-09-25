# Single-path delivery and task delegation

Product / Integration Owner decision, 2026-09-26. This is the current execution model. It supersedes the standing person-to-module assignments in the Team Development Guide v1.0, the original Phase 1 kickoff, and the individual task briefs. Those documents remain useful history for work already in progress; they do not assign future work automatically. PRD v3.0 remains the product source of truth, and `packages/contracts` remains the shared interface source of truth.

## One product path

张天霁 (`@ztjklt`) drives the current product path end to end: chooses the next user-visible slice, integrates it, and decides when to ask for help. Work follows the runnable flow rather than separate Android, Backend, AI Core, or Voice staffing queues. A directory or service name describes a code responsibility, not a permanent person or a requirement to deploy another service.

Phase 1 remains the only committed workstream: `real Android recording → upload → Episode persistence → STT → Memory extraction → Android displays the real Memory`. An intermediate demo may show a smaller working slice, but must say which steps are real and which are fixtures. Phase 2–4 implementation still requires a Product Owner decision. iOS is not the current client baseline; starting it requires an explicit scope decision.

## When to delegate

The mainline developer works across the repository. Open a separate Issue when a bounded task needs specialist design, independent investigation, or enough time that handing it off will speed the main path. Do not create an Issue merely to preserve a module boundary.

Each delegated Issue names one temporary task owner and states:

1. The concrete outcome and why the main path needs it.
2. Inputs, existing code or contract to reuse, and files or interface boundaries the task may change.
3. One observable acceptance result and the shortest relevant verification command or device step.
4. The expected handoff: a reviewable PR into `develop`, with setup notes if another machine must run it.

The contributor branches from current `develop`, works within that Issue, and opens a PR. After required review, the Product / Integration Owner merges it; everyone then pulls `develop` before using the result. If the work needs a shared Contract change, propose that change in the Issue and obtain Product / Integration Owner approval before implementation. Avoid parallel implementations of the same capability.

Existing Issues and PRs keep their authors and review history. This decision does not silently cancel work already underway or turn a historical task brief into a new standing assignment. The Product / Integration Owner coordinates any explicit handoff that changes an active task.

## Keep verification proportional

For each PR, record the command or real-device action actually run and its result, plus relevant consent, privacy, migration, rollback, and Contract impact. Reuse existing logs or a concise result summary; do not demand a long checklist or repeat an unchanged test solely to reformat evidence. A real-device claim needs a real-device observation. A build, fixture, or emulator result is labeled as such.

The integration owner checks the current end-to-end path when it changes and records the first failing step. A slice can move forward while another dependency is unfinished; the Phase 1 gate is met only after the complete real path works. Keep recording consent, subject isolation, raw Episode preservation, provenance, model versions, explicit failures, and provider secrets behind server-side adapters. Voice cloning still needs consent separate from recording.

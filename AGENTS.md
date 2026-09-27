# Coding Agent Instructions

## UI handoff branch context — 2026-09-27

This branch is an explicitly requested dual-client UI handoff based on PR #78 at `f63f7ef`, not current develop. Read `docs/mobile-ui/HANDOFF.md` before continuing. The Android-only wording and older staffing/branch rules below are inherited baseline history; the user authorized parallel Android and iOS UI work, with iOS delivered separately on `codex/ios-ui-alignment`. Do not merge the two branches wholesale or silently replace newer #78 dashboard work. The handoff does not authorize a provider-route or shared Contract change. Native device verification remains pending.

You are working in the Remember Me monorepo. Before changing code, read `README.md`, `CONTRIBUTING.md`, `docs/PRD/PRD_V3_SUMMARY.md`, `docs/team/00_TEAM_OWNERSHIP.md`, `docs/team/PHASE1_KICKOFF.md`, the task brief for the affected owner, `docs/roadmap/ROADMAP.md`, and `packages/contracts/README.md`.

## Source of truth

- `docs/PRD/Remember_Me_PRD_v3.0.docx` is the current product Source of Truth. `docs/PRD/archive/` is history and is not an implementation basis.
- The client baseline is Android / Kotlin / Jetpack Compose. Text naming iOS, Swift, or SwiftUI as the current client is superseded — do not reintroduce it.
- The Team Development Guide v1.0 in `docs/team/` is the engineering execution baseline.

## Phase discipline

- Phase 1 — Golden Path is COMMITTED / NOW and is the only committed workstream.
- Phase 2 — Core Twin is PLANNED / NEXT. Phases 3 and 4 are PLANNED and BACKLOG / CONDITIONAL.
- A planned phase is not authorization to build it. Do not start Phase 2–4 implementation because the roadmap documents them. Preparing non-blocking skeletons such as UI shells, schemas, adapters, or test fixtures is allowed; freezing a cross-module implementation alone is not.
- Do not assume undecided external dependencies are settled. Work 3200 SDK capability, the STT provider, and the Voice provider are all open — keep them behind adapters with capability fallback.

## Boundaries

- Do not rewrite another owner's module or create a competing implementation.
- Do not change a cross-module contract without an Issue or proposal and Product and Integration Owner approval.
- Do not tear down the working Android Compose prototype to pursue architectural tidiness. Replace Mock implementations incrementally.
- Preserve provenance, consent, subject isolation, model version, and failure states.
- Prefer one main LLM with schema workers for the first AI implementation; do not split services only to claim a multi-agent architecture.
- Keep providers behind adapters. Android must not depend directly on a specific backend, STT, LLM, or voice provider, and must hold no provider secrets.
- A feature is not complete until its owner runs it locally and records the verification in the Pull Request.

## Delivery flow

Work from `develop` on the owner-specific feature prefixes listed in `CONTRIBUTING.md`. Keep changes reviewable, update tests and docs with behavior, and disclose contract impact in every Pull Request. Never push directly to `main`.

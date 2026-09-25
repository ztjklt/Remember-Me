# Coding Agent Instructions

You are working in the Remember Me monorepo. Before changing code, read `README.md`, `CONTRIBUTING.md`, `docs/PRD/PRD_V3_SUMMARY.md`, `docs/team/00_TEAM_OWNERSHIP.md`, `docs/roadmap/ROADMAP.md`, and `packages/contracts/README.md`. Read an Issue-specific brief when working on a delegated task.

## Source of truth

- `docs/PRD/Remember_Me_PRD_v3.0.docx` is the current product Source of Truth. `docs/PRD/archive/` is history and is not an implementation basis.
- The client baseline is Android / Kotlin / Jetpack Compose. Text naming iOS, Swift, or SwiftUI as the current client is superseded — do not reintroduce it.
- The current execution model is `docs/team/00_TEAM_OWNERSHIP.md`. It supersedes fixed staffing assignments in the Team Development Guide v1.0 and historical task briefs; it does not change PRD v3.0 or the shared Contract.

## Phase discipline

- Phase 1 — Golden Path is COMMITTED / NOW and is the only committed workstream.
- Phase 2 — Core Twin is PLANNED / NEXT. Phases 3 and 4 are PLANNED and BACKLOG / CONDITIONAL.
- A planned phase is not authorization to build it. Do not start Phase 2–4 implementation because the roadmap documents them. Preparing non-blocking skeletons such as UI shells, schemas, adapters, or test fixtures is allowed; freezing a cross-module implementation alone is not.
- Do not assume undecided external dependencies are settled. Work 3200 SDK capability, the STT provider, and the Voice provider are all open — keep them behind adapters with capability fallback.

## Boundaries

- The Product / Integration Owner may work across the product path. Delegated contributors work within their Issue scope; coordinate active work so two implementations do not compete.
- Do not change a cross-module contract without an Issue or proposal and Product and Integration Owner approval.
- Do not tear down the working Android Compose prototype to pursue architectural tidiness. Replace Mock implementations incrementally.
- Preserve provenance, consent, subject isolation, model version, and failure states.
- Prefer one main LLM with schema workers for the first AI implementation; do not split services only to claim a multi-agent architecture.
- Keep providers behind adapters. Android must not depend directly on a specific backend, STT, LLM, or voice provider, and must hold no provider secrets.
- A feature is complete when its actual path is verified and the result is recorded concisely in the Pull Request. Reuse existing evidence; do not repeat tests solely to reformat a report.

## Delivery flow

Work from `develop` on a descriptive feature branch. Delegate bounded work with an Issue, review its PR into `develop`, and pull the merged result before continuing. Keep changes reviewable, update tests and docs with behavior, and disclose contract impact in every Pull Request. Never push directly to `main`.

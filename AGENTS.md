# Coding Agent Instructions

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
  - User-authorized exception (2026-10-07): the experimental local Android mode may store user-supplied ASR/LLM credentials encrypted with Android Keystore and call providers through adapters. Never bundle keys, export them, log them, or include them in backups. Preserve the remote mode. Implement a single Agent loop; multi-agent delegation and compression are out of scope. See `docs/proposals/ANDROID_LOCAL_AGENT_MEMEX_REVIEW.md`.
- A feature is not complete until its owner runs it locally and records the verification in the Pull Request.

## Delivery flow

Work from `develop` on the owner-specific feature prefixes listed in `CONTRIBUTING.md`. Keep changes reviewable, update tests and docs with behavior, and disclose contract impact in every Pull Request. Never push directly to `main`.

- Follow the commit guidelines in `CONTRIBUTING.md`: one reviewable change per commit, concise Conventional Commits subjects, and optional short bodies.
- Before committing, review the complete staged diff and file count, including new or imported files. Report Git's actual scope rather than an editor's edit count.
- Keep full verification evidence in the Pull Request or linked docs. Verify remote history before reworking local commits; coordinate changes to published history.

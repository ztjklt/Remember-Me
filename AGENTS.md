# Coding Agent Instructions

You are working in the Remember Me monorepo. Before changing code, read `README.md`, `CONTRIBUTING.md`, `docs/PRD/PRD_V3_SUMMARY.md`, `docs/team/00_TEAM_OWNERSHIP.md`, `docs/roadmap/ROADMAP.md`, and `packages/contracts/README.md`. Read an Issue-specific brief when working on a delegated task.

## Source of truth

- `docs/PRD/Remember_Me_PRD_v3.0.docx` remains the source of product behavior. The 2026-09-26 Product Owner amendment in `docs/team/00_TEAM_OWNERSHIP.md` authorizes both iOS and Android client tracks; older Android-only platform wording is superseded. `docs/PRD/archive/` remains history.
- iOS and Android use the same Backend Contract. The current Android Compose prototype stays intact; iOS implementation can start as its own client track.
- The current execution model is `docs/team/00_TEAM_OWNERSHIP.md`: 张天霁 leads iOS, 刘修贤 leads Android, and 康欣 / 王昊宇 take only explicitly delegated small Issues. Backend, AI Core, and Voice have no standing person-to-module assignment.

## Phase discipline

- Phase 1 — Golden Path is COMMITTED / NOW and is the only committed workstream.
- Phase 2 — Core Twin is PLANNED / NEXT. Phases 3 and 4 are PLANNED and BACKLOG / CONDITIONAL.
- A planned phase is not authorization to build it. Do not start Phase 2–4 implementation because the roadmap documents them. Preparing non-blocking skeletons such as UI shells, schemas, adapters, or test fixtures is allowed; freezing a cross-module implementation alone is not.
- Do not assume undecided external dependencies are settled. Work 3200 SDK capability, the STT provider, and the Voice provider are all open — keep them behind adapters with capability fallback.

## Boundaries

- Each client lead drives their route. A delegated contributor works only within an assigned Issue; coordinate concrete shared-interface changes so implementations do not compete.
- Do not change a cross-module contract without an Issue or proposal and Product and Integration Owner approval.
- Do not tear down the working Android Compose prototype to pursue architectural tidiness. Replace Mock implementations incrementally.
- Preserve provenance, consent, subject isolation, model version, and failure states.
- Prefer one main LLM with schema workers for the first AI implementation; do not split services only to claim a multi-agent architecture.
- Keep providers behind adapters. Neither mobile client depends directly on an STT, LLM, or voice provider or holds provider secrets; both use the shared Backend Contract.
- Verify changed behavior proportionally and record what actually ran. CI, peer review, and repeated real-device checks are not mandatory merge gates. Focus device checks on changed native behavior and the selected end-to-end demo; do not require repeated cross-team or cross-platform sign-off.

## Delivery flow

The iOS and Android leads can progress independently. Use descriptive branches and batch related work when useful; a delegated small Issue uses a focused PR for handoff. Neither `develop` nor `main` has branch protection or requires a passing CI check or second-person approval. Direct pushes are allowed. Preserve truthful test results, relevant docs, and Contract impact. Keep `main` as a usable demo snapshot.

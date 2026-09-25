# Coding Agent Instructions

You are working in the Remember Me monorepo. Before changing code, read `README.md`, `CONTRIBUTING.md`, `docs/PRD/PRD_V3_SUMMARY.md`, `docs/team/00_TEAM_OWNERSHIP.md`, `docs/roadmap/ROADMAP.md`, and `packages/contracts/README.md`. Read an Issue-specific brief when working on a delegated task.

## Source of truth

- `docs/PRD/Remember_Me_PRD_v3.0.docx` remains the source of product behavior. The 2026-09-26 Product Owner amendment in `docs/team/00_TEAM_OWNERSHIP.md` authorizes both iOS and Android client tracks; older Android-only platform wording is superseded. `docs/PRD/archive/` remains history.
- iOS and Android use the same Backend Contract. The current Android Compose prototype stays intact; iOS implementation can start as its own client track.
- The current execution model is `docs/team/00_TEAM_OWNERSHIP.md`. It supersedes fixed staffing assignments in the Team Development Guide v1.0 and historical task briefs without changing the shared Contract.

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
- Keep providers behind adapters. Neither mobile client depends directly on an STT, LLM, or voice provider or holds provider secrets; both use the shared Backend Contract.
- Verify the changed behavior once with the shortest relevant check and record the result concisely in the Pull Request. Native-device behavior gets a focused device check when it changes; do not require repeat cross-team or cross-platform checks for every PR.

## Delivery flow

Work from `develop` on a descriptive feature branch. Delegate bounded work with an Issue and merge its PR after the required CI check; routine `develop` PRs do not require a second person's approval. The mainline lead keeps both client tracks moving while delegated work is in flight. Update tests and docs with behavior, disclose Contract impact, and keep `main` behind release review and CI. Never push directly to `main`.

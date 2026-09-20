# Coding Agent Instructions

You are working in the Remember Me monorepo. Before changing code, read `README.md`, `CONTRIBUTING.md`, `docs/PRD/PRD_V2_SUMMARY.md`, `docs/team/00_TEAM_OWNERSHIP.md`, the task brief for the affected owner, and `packages/contracts/README.md`.

## Boundaries

- Do not rewrite another owner's module or create a competing implementation.
- Do not change a cross-module contract without an Issue or proposal and Product and Integration Owner approval.
- Preserve provenance, consent, subject isolation, model version, and failure states.
- Prefer one main LLM with schema workers for the first AI implementation; do not split services only to claim a multi-agent architecture.
- Keep providers behind adapters. Android must not depend directly on a specific backend, STT, LLM, or voice provider.
- A feature is not complete until its owner runs it locally and records the verification in the Pull Request.

## Delivery flow

Work from `develop` on the owner-specific feature prefixes listed in `CONTRIBUTING.md`. Keep changes reviewable, update tests and docs with behavior, and disclose contract impact in every Pull Request. Never push directly to `main`.

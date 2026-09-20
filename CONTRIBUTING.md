# Contributing

Baseline: [PRD v3.0](docs/PRD/Remember_Me_PRD_v3.0.docx), the [Team Development Guide v1.0](docs/team/Remember_Me_Team_Development_Guide_v1.0.docx), and the [roadmap](docs/roadmap/ROADMAP.md). The client baseline is Android / Kotlin / Jetpack Compose.

## Branches

- `main` contains stable demonstrable releases and accepts changes only through reviewed Pull Requests.
- `develop` is the continuous integration branch.
- Android and hardware: `feature/android-*`, `feature/hardware-*`
- AI Core: `feature/ai-*`, `feature/person-model-*`, `feature/twin-*`
- Backend, voice, and infrastructure: `feature/backend-*`, `feature/voice-*`, `feature/infra-*`

Create feature branches from `develop` and open Pull Requests back to `develop`. Release Pull Requests go from `develop` to `main`.

The current owner-by-owner starting order and suggested branch names are recorded in [the Phase 1 kickoff](docs/team/PHASE1_KICKOFF.md).

## Pull Request contract

Every Pull Request must state what changed, how it was tested, whether `packages/contracts` changed, and any consent, privacy, migration, or rollback impact. Cross-module contract changes require an Issue or proposal before implementation.

While the known Hosted Runner dependency-resolution failure is tracked in Issue #17, it is not a Phase 1 product gate. Pull Requests into `develop` still require a Code Owner review and exact local verification evidence. Do not use a skipped, placeholder, or no-op check as a substitute. `main` retains its required CI check and is not released while that check is failing.

## Scope

Phase 1 — Golden Path is the only committed workstream. Phase 2–4 issues are planned, and picking one up requires an explicit decision from the Product and Integration Owner, not just the existence of an issue.

## Issues and milestones

Label issues with the affected area — `android`, `ai-core`, `backend`, `voice`, `hardware`, `integration`, `blocked` — and attach them to the matching Phase milestone. A member's own issues must reference their task brief in `docs/team/`.

## Definition of done

The responsible owner has run the affected path locally, automated checks pass, failure and empty states are handled where relevant, documentation matches behavior, and no secrets or local environment files are committed.

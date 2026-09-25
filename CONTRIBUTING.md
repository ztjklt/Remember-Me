# Contributing

Baseline: [PRD v3.0](docs/PRD/Remember_Me_PRD_v3.0.docx), the [current delivery model](docs/team/00_TEAM_OWNERSHIP.md), and the [roadmap](docs/roadmap/ROADMAP.md). The client baseline is Android / Kotlin / Jetpack Compose.

## Branches

- `main` contains stable demonstrable releases and accepts changes only through reviewed Pull Requests.
- `develop` is the continuous integration branch.
- Use a descriptive `feature/*` branch named for the change, such as `feature/android-real-capture` or `feature/episode-ingestion`. A prefix describes the work, not a permanent owner.

Create feature branches from `develop` and open Pull Requests back to `develop`. Release Pull Requests go from `develop` to `main`.

The [Phase 1 kickoff](docs/team/PHASE1_KICKOFF.md) records the original assignments for historical Issues and PRs. New work follows the current delivery model.

## Pull Request contract

Every Pull Request must state what changed, how it was tested, whether `packages/contracts` changed, and any consent, privacy, migration, or rollback impact. Cross-module contract changes require an Issue or proposal before implementation.

While the known Hosted Runner dependency-resolution failure is tracked in Issue #17, it is not a Phase 1 product gate. Pull Requests into `develop` still require review and a concise record of the command or device path actually run and its result. Link existing evidence rather than rerunning unchanged checks to produce a new report. Do not use a skipped, placeholder, or no-op check as a substitute. `main` retains its required CI check and is not released while that check is failing.

## Scope

Phase 1 — Golden Path is the only committed workstream. Phase 2–4 issues are planned, and picking one up requires an explicit decision from the Product and Integration Owner, not just the existence of an issue.

## Issues and milestones

Open an Issue when a bounded task is worth handing off. Give it one temporary owner, a concrete outcome, inputs, scope, and the shortest useful acceptance check. Area labels — `android`, `ai-core`, `backend`, `voice`, `hardware`, `integration`, `blocked` — are search aids, not staffing assignments. Attach the Issue to the matching Phase milestone.

## Definition of done

The affected path has been run locally or on a real device where required, with the result recorded in the PR. Relevant checks pass, failure and empty states are handled, documentation matches behavior, and no secrets or local environment files are committed. The full Phase 1 gate is assessed on the integrated real-device path, not on every intermediate slice.

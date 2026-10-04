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

## Commits

- Keep each commit focused on one reviewable change, with its relevant tests and documentation. Separate independent fixes from features and order dependent changes so each commit can build. Do not split coupled changes just to meet a file-count target.
- Use a concise [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) subject: `type(scope): summary`. Use the imperative and aim for at most 72 characters, for example `fix(backend): retry transient provider failures`.
- The body is optional. Add only the reason or necessary compatibility/migration details. Keep development chronology and full verification logs in the Pull Request or linked documentation.
- Stage explicit paths. Before committing, inspect `git status --short`, `git diff --cached` and `git diff --cached --stat`, then run `git diff --cached --check`. Report the complete Git change, including new and imported files; an editor's file count is not the commit scope.
- Rework unpublished local commits when needed. Check remote history first and coordinate any rewrite of published commits. These practices follow the [Git contribution guidelines](https://git-scm.com/book/en/v2/Distributed-Git-Contributing-to-a-Project).

## Pull Request contract

Every Pull Request must state what changed, how it was tested, whether `packages/contracts` changed, and any consent, privacy, migration, or rollback impact. Cross-module contract changes require an Issue or proposal before implementation.

While the known Hosted Runner dependency-resolution failure is tracked in Issue #17, it is not a Phase 1 product gate. Pull Requests into `develop` still require a Code Owner review and exact local verification evidence. Do not use a skipped, placeholder, or no-op check as a substitute. `main` retains its required CI check and is not released while that check is failing.

## Scope

Phase 1 — Golden Path is the only committed workstream. Phase 2–4 issues are planned, and picking one up requires an explicit decision from the Product and Integration Owner, not just the existence of an issue.

## Issues and milestones

Label issues with the affected area — `android`, `ai-core`, `backend`, `voice`, `hardware`, `integration`, `blocked` — and attach them to the matching Phase milestone. A member's own issues must reference their task brief in `docs/team/`.

## Definition of done

The responsible owner has run the affected path locally, automated checks pass, failure and empty states are handled where relevant, documentation matches behavior, and no secrets or local environment files are committed.

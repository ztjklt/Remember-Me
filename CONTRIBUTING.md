# Contributing

Baseline: [PRD v3.0](docs/PRD/Remember_Me_PRD_v3.0.docx), the [current delivery model and dual-client amendment](docs/team/00_TEAM_OWNERSHIP.md), and the [roadmap](docs/roadmap/ROADMAP.md). iOS and Android are active client tracks using one shared Backend Contract.

## Branches

- `main` holds usable demo snapshots. Neither a PR review nor CI pass is a required gate, although both can be used when helpful.
- `develop` is the ongoing integration branch, with CI as feedback rather than a merge blocker.
- Use a descriptive `feature/*` branch named for the change, such as `feature/android-real-capture`, `feature/ios-capture`, or `feature/episode-ingestion`. A prefix describes the work, not a permanent owner.

Start feature work from current `develop`. 张天霁 leads iOS and 刘修贤 leads Android; each can batch related work and merge without waiting for routine cross-team sign-off. Delegated Issues use their own small PRs into `develop` so the lead can pull the result locally. Move a usable demo snapshot from `develop` to `main` when ready.

The [Phase 1 kickoff](docs/team/PHASE1_KICKOFF.md) records the original assignments for historical Issues and PRs. New work follows the current delivery model.

## Pull Request contract

Every delegated PR briefly states what changed, what was actually checked, whether `packages/contracts` changed, and any real consent, privacy, or migration impact. A mainline lead may use the same concise format. Cross-module Contract changes still require an Issue or proposal and Product Owner approval before implementation.

CI and review are optional feedback on both `develop` and `main`; neither is a required merge gate. Record one relevant command or observation when it helps explain the result, and report failures honestly. Device checks focus on changed native behavior and the chosen end-to-end demo, not every PR or both clients. Do not present a skipped, placeholder, or no-op check as successful verification. Force pushes and branch deletion remain disabled.

## Scope

Phase 1 — Golden Path is the only committed workstream. Phase 2–4 issues are planned, and picking one up requires an explicit decision from the Product and Integration Owner, not just the existence of an issue.

## Issues and milestones

Open an Issue only when either lead wants to hand off a bounded task. Assign one available contributor for that Issue, with a concrete outcome, inputs, scope, and a short completion check. No Backend, AI Core, or Voice queue is permanently assigned. Area labels — `ios`, `android`, `ai-core`, `backend`, `voice`, `hardware`, `integration`, `on-hold` — are search aids, not staffing assignments.

## Definition of done

The person doing the work knows what changed, records the relevant result without unnecessary repeat runs, handles meaningful failure states, and commits no secrets or local environment files. A failed CI run is visible feedback, not a merge veto. A complete Phase 1 product claim still requires one real integrated recording-to-Memory demonstration.

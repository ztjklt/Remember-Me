# Phase 1 Golden Path — Team Kickoff

This is the operational checklist for the current committed workstream. Product scope and exit criteria remain defined by PRD v3.0 and the roadmap. CI health is tracked independently in Issue #17 and does not block local Phase 1 development.

## Before starting

1. Accept the GitHub repository invitation and confirm that the repository is writable.
2. Read `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/PRD/PRD_V3_SUMMARY.md`, `docs/team/00_TEAM_OWNERSHIP.md`, your task brief, `docs/roadmap/ROADMAP.md`, and `packages/contracts/README.md`.
3. Start every branch from the latest `develop`:

```bash
git fetch origin
git switch develop
git pull --ff-only origin develop
git switch -c <feature-branch>
```

Never push directly to `develop` or `main`. Open a Pull Request back to `develop`, include the exact local verification command and result, disclose Contract impact, and resolve review conversations before merge.

## First work by owner

| Owner | Start now | Then | Do not start yet | Suggested branches |
| --- | --- | --- | --- | --- |
| 刘修贤 `@shuziyuxingxing-stack` | #15 Remove direct Mock repository construction from UI | #6 Real capture and persistent audio | #7 until #6 and Backend #1 interfaces exist | `feature/android-repository-boundary`, then `feature/android-real-capture` |
| 康欣 `@centraler` | #4 Freeze Episode and Transcript fixtures | #2 Memory Extractor MVP while satisfying #5 provenance requirements | Phase 2 Person Model/Twin implementation | `feature/ai-contract-fixtures`, then `feature/ai-memory-extractor` |
| 王昊宇 `@qingtian-4` | #13 Backend ADR | #8 service foundation, then #1 ingestion and async status | Voice implementation and provider freeze | `feature/backend-platform-adr`, then `feature/backend-foundation` |
| 张天霁 `@ztjklt` | Contract review and owner PR review | Prepare #14 Stub Golden Path against frozen fixtures and interfaces | Implementing another owner's module | `feature/integration-stub-golden-path` |

## Temporary verification policy while CI #17 is open

- A failing Hosted Runner caused only by the known AGP dependency-resolution incident is not a Phase 1 product blocker.
- Every PR must still fail closed locally: run the module's real test/build command and paste the command plus result into the PR.
- Android minimum verification is `cd apps/android && ./gradlew test assembleDebug`.
- Contract minimum verification is `cd packages/contracts && npm test`.
- Backend and AI Core PRs must add a deterministic local test command to their README with their first implementation PR.
- No placeholder, skipped, or no-op check may be presented as successful verification.

## Dependency order

- Android #15 and #6, AI Core #4 and #2, and Backend #13 and #8 can proceed independently.
- Backend #1 follows #8 and consumes the AI Core callable interface from #2.
- Android #7 waits for Android #6 and the Backend #1 API boundary.
- Integration #14 begins with fixtures but merges the complete stub path only after Backend #1/#8 interfaces exist.
- Phase 2–4 work remains unauthorized until the Product and Integration Owner records a phase decision.

## Phase 1 acceptance

Only this real-device path closes the phase: `real Android recording → upload → Episode persistence → STT → AI Memory extraction → Android displays the real Memory`. Fixtures prove wiring but do not satisfy the gate.

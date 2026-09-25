# Remember Me

Remember Me is a consent-first system that turns recorded life episodes into traceable memories, an evolving person model, and evidence-backed Twin responses. The existing Android client and the authorized iOS track share one Backend Contract and processing path.

## Current status

The committed workstream is **Phase 1 — Golden Path**: `real recording → upload → Episode → STT → Memory extraction → real Memory in Android`. Phases 2–4 are planned and backlogged; reading them is not authorization to start them.

The Android prototype is runnable. The iOS track is authorized but has no app project in this repository yet. Feature readiness is tracked through the current PRs and the [roadmap](docs/roadmap/ROADMAP.md); a working Phase 1 demo requires a real recording through the shared processing path on one client.

| Phase | Status |
| --- | --- |
| Phase 1 — Golden Path | COMMITTED / NOW |
| Phase 2 — Core Twin | PLANNED / NEXT |
| Phase 3 — Calibration + Voice | PLANNED |
| Phase 4 — Hardware + Legacy | BACKLOG / CONDITIONAL |

## Baseline documents

- [Remember Me PRD v3.0](docs/PRD/Remember_Me_PRD_v3.0.docx) — product behavior source of truth; the current delivery model amends its client scope to iOS and Android
- [PRD v3.0 Summary](docs/PRD/PRD_V3_SUMMARY.md) — agent-readable orientation
- [Current delivery model](docs/team/00_TEAM_OWNERSHIP.md) — 张天霁 leads iOS, 刘修贤 leads Android; other work is delegated only through small Issues
- [Team Development Guide v1.0](docs/team/Remember_Me_Team_Development_Guide_v1.0.docx) — historical engineering guide; fixed staffing assignments are superseded
- [Roadmap](docs/roadmap/ROADMAP.md) — phases and exit gates
- [Phase 1 Team Kickoff](docs/team/PHASE1_KICKOFF.md) — historical first assignments and PR context

PRD v2.0 is archived history in [`docs/PRD/archive/`](docs/PRD/archive/). The 2026-09-26 Product Owner decision in the current delivery model activates iOS alongside Android; it does not revive archived product behavior.

## Repository map

- `apps/android` — Android client (Kotlin, Jetpack Compose) and its build documentation
- `services/backend` — API, persistence, auth, jobs, and storage
- `services/ai-core` — memory extraction, person model, Twin, calibration, and capture planning
- `services/voice` — consent-gated voice dataset, clone, and TTS adapters
- `packages/contracts` — versioned cross-module schemas; the integration source of truth
- `infra` — environments, deployment, migrations, logging, and monitoring
- `docs/PRD` — current PRD and its agent-readable summary
- `docs/architecture` — system architecture baseline
- `docs/roadmap` — phase status, gates, and owners
- `docs/team` — current delivery model and historical task briefs
- `docs/api` — contract field and integration guidance

## Start here

All contributors and coding agents must read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), the [PRD v3.0 summary](docs/PRD/PRD_V3_SUMMARY.md), the [current delivery model](docs/team/00_TEAM_OWNERSHIP.md), the [roadmap](docs/roadmap/ROADMAP.md), and [shared contracts](packages/contracts/README.md) before changing code. A delegated contributor also reads the Issue that defines the task.

Android setup and build commands are in [apps/android/README.md](apps/android/README.md). The local verification command is:

```bash
cd apps/android
./gradlew test assembleDebug
```

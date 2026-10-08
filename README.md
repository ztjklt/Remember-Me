# Remember Me

Remember Me is a consent-first system that turns recorded life episodes into traceable memories, an evolving person model, and evidence-backed Twin responses. This repository contains the Android client and the shared baseline for backend, AI Core, voice, infrastructure, and team integration.

## Current status

The committed workstream is **Phase 1 — Golden Path**: `real recording → upload → Episode → STT → Memory extraction → real Memory in Android`. Phases 2–4 are planned and backlogged; reading them is not authorization to start them.

The current experimental feature branch includes phone recording, the Backend Golden Path, and a user-authorized Android BYOK loop. Local mode adds evidence-backed memory observations, portrait views, questions and corrections; it requires network access to user-configured model services. Hardware integration, voice cloning, accounts and cloud sync remain outside this prototype. Cross-module approval and device verification must precede a stable release.

For the `1.5-local` prototype, see the [phone setup and update steps](apps/android/docs/LOCAL_AGENT.md), [memory/portrait proposal and implementation scope](docs/proposals/MEMORY_PORTRAIT_PLAN_2026_10_08.md), and [verification record](docs/verification/ANDROID_MEMORY_PORTRAIT_2026_10_08.md).

| Phase | Status |
| --- | --- |
| Phase 1 — Golden Path | COMMITTED / NOW |
| Phase 2 — Core Twin | PLANNED / NEXT |
| Phase 3 — Calibration + Voice | PLANNED |
| Phase 4 — Hardware + Legacy | BACKLOG / CONDITIONAL |

## Baseline documents

- [Remember Me PRD v3.0](docs/PRD/Remember_Me_PRD_v3.0.docx) — current product Source of Truth (Android First)
- [PRD v3.0 Summary](docs/PRD/PRD_V3_SUMMARY.md) — agent-readable orientation
- [Team Development Guide v1.0](docs/team/Remember_Me_Team_Development_Guide_v1.0.docx) — engineering execution baseline
- [Roadmap](docs/roadmap/ROADMAP.md) — phases, exit gates, owners
- [Phase 1 Team Kickoff](docs/team/PHASE1_KICKOFF.md) — first tasks, branch names, dependency order, and temporary local-verification policy

PRD v2.0 is archived history in [`docs/PRD/archive/`](docs/PRD/archive/). Older text naming iOS, Swift, or SwiftUI as the current client is superseded by PRD v3.0.

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
- `docs/team` — team development guide, ownership, and individual task briefs
- `docs/api` — contract field and integration guidance

## Start here

All contributors and coding agents must read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), the [PRD v3.0 summary](docs/PRD/PRD_V3_SUMMARY.md), the [Team Development Guide](docs/team/Remember_Me_Team_Development_Guide_v1.0.docx), [team ownership](docs/team/00_TEAM_OWNERSHIP.md), the [Phase 1 kickoff](docs/team/PHASE1_KICKOFF.md), your own task brief in `docs/team/`, the [roadmap](docs/roadmap/ROADMAP.md), and [contract v0.1](packages/contracts/README.md) before changing code.

Android setup and build commands are in [apps/android/README.md](apps/android/README.md). The local verification command is:

```bash
cd apps/android
./gradlew test assembleDebug
```

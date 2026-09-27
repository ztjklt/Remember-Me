# Remember Me

> **2026-09-27 移动 UI 交接分支：** 当前第六版原型、Android 实现、品牌及图形源资产的入口在 [docs/mobile-ui/HANDOFF.md](docs/mobile-ui/HANDOFF.md)。iOS 代码在独立的 `codex/ios-ui-alignment` 分支。本分支固定基于 #78 的旧提交，下面继承的 Android-only 状态文字属于上游历史；双端安排、当前能力和未完成验证请以交接说明为准。此分支不是 main/develop 的发布状态。

Remember Me is a consent-first system that turns recorded life episodes into traceable memories, an evolving person model, and evidence-backed Twin responses. This repository contains the Android client and the shared baseline for backend, AI Core, voice, infrastructure, and team integration.

## Current status

The committed workstream is **Phase 1 — Golden Path**: `real recording → upload → Episode → STT → Memory extraction → real Memory in Android`. Phases 2–4 are planned and backlogged; reading them is not authorization to start them.

The Android prototype is runnable and tested, but it is a Mock product-flow prototype, not a working product. Real microphone capture, upload, STT, AI extraction, person modeling, Twin, voice cloning, backend persistence, accounts, cloud sync, and Work 3200 integration are **not yet implemented**.

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

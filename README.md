# Remember Me

> **本地 Agent 工作台分支，2026-10-07：** 本分支实现了所有者/读者身份、故事授权、核对后整理与跨录音修订。查看[启动说明](docs/agent-loop/RUNBOOK.md)和[验证记录](docs/agent-loop/ACCEPTANCE.md)。真实云端模型验收仍待密钥配置；本分支不代表手机或生产发布验收。

> **2026-09-27 双端集成：** Android 的 #78／#79 和随后提交的 #81 界面与 iOS 的 #76／#77／#80 已接合。Android 单元测试、APK 构建与 lint 通过；iOS UI v6 在 Mac 的 Xcode 27 模拟器目标构建通过。真机运行结果另记，不能由构建结果推断。

Remember Me is a consent-first system that turns recorded life episodes into traceable memories, an evolving person model, and evidence-backed Twin responses. The existing Android client and the authorized iOS track share one Backend Contract and processing path.

## Current status

The iOS voice-to-Person-Model slice was authorized in [Issue #75](https://github.com/ztjklt/Remember-Me/issues/75). The Product Owner subsequently authorized an iOS-first evidence Twin and separately consented local Voice loop in the [Twin proposal](docs/architecture/twin-voice-contract-proposal.md), followed by a locked-answer [calibration slice](docs/architecture/calibration-contract-proposal.md). This work uses the existing Phase 1 recording path; cloud deployment and multi-user accounts remain later work.

The latest Android portrait UI from #81 opens the locally working recording and archive flow from #79. The graph and agent pages label unconnected preview content. Its real memory-processing adapter is not connected in the default build; the Android APK contains no provider credentials. The iOS SwiftUI project lives in [apps/ios](apps/ios/README.md); its paired Mac stack uses local Whisper and DeepSeek V4 Flash behind Backend and AI Core adapters. Audio remains local; confirmed transcript text is sent to DeepSeek. Local Qwen remains an adapter option. Feature readiness is tracked through the [roadmap](docs/roadmap/ROADMAP.md); physical iPhone evidence is recorded separately from simulator builds and synthetic audio probes.

| Phase | Status |
| --- | --- |
| Phase 1 — Golden Path | COMMITTED / NOW |
| Phase 2 — Core Twin | iOS-first slice AUTHORIZED / IN PROGRESS |
| Phase 3 — Calibration + Voice | iOS-first calibration and local Voice slices AUTHORIZED / IN PROGRESS |
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
- `apps/ios` — iOS SwiftUI client, local pairing and device runbook
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

For the local iOS voice-to-Person-Model path, follow [apps/ios/README.md](apps/ios/README.md).

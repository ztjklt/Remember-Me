# Remember Me

> **2026-10-10 团队交接入口：** [当前流程、采用范围与四人分工建议](docs/agent-loop/TEAM_HANDOFF_2026-10-10.md) · [19 张顺序截图](docs/agent-loop/screenshots/2026-10-10/README.md) · [构建/运行说明](docs/agent-loop/TEAM_RUNBOOK_2026-10-10.md) · [本次复验结果](docs/agent-loop/HANDOFF_VALIDATION_2026-10-10.md)。Android 模拟器可直接连接 ECS，完成原生录音、Paraformer 转写、文字核对、DeepSeek 整理、记忆/人物候选、来源问答、邀请与亲友补问。模型质量仍有已知问题；真机与本次 iOS 未验收。

> **历史材料说明：** 10 月 8 日三人 30 段合成语料使用过 Groq 等路线，见[原始结果与边界](docs/agent-loop/GROQ_LIVE_RESULTS_2026-10-08.md)。这些不能冒称已全部重新跑过 Paraformer。旧启动说明用于解释历史，新队友以本次运行说明为准。

> **2026-09-27 双端集成：** Android 的 #78／#79 和随后提交的 #81 界面与 iOS 的 #76／#77／#80 已接合。Android 单元测试、APK 构建与 lint 通过；iOS UI v6 在 Mac 的 Xcode 27 模拟器目标构建通过。真机运行结果另记，不能由构建结果推断。

Remember Me is a consent-first system that turns recorded life episodes into traceable memories, an evolving person model, and evidence-backed Twin responses. The existing Android client and the authorized iOS track share one Backend Contract and processing path.

## Current status

The current integration branch includes ordinary accounts, owner-approved story sharing, transcript review, evidence-backed memories, profile candidates, reviewed story organization, Twin answers and locked-answer calibration. The ECS deployment uses Paraformer ASR and the Weixin DeepSeek adapter; credentials remain on the server. The default Android entry is the native shared-backend workbench. Use the internal build or an explicit service URL; the debug default remains local development.

Android's legacy local prototype remains available in source, but its Mock graph/agent pages are not evidence for the connected product. The iOS project lives in [apps/ios](apps/ios/README.md); this handoff includes the earlier UI adoption, not automatic integration of the latest PR #86 or a new iOS device acceptance. Historical phase labels below describe authorization, not current test coverage. Current results and limitations are in the dated team handoff above.

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

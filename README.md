# Remember Me

> **2026-10-15 ECS＋Android 0.12.1 已同步：** [下载、账号和操作说明](docs/agent-loop/ANDROID_0121_QUICK_START_2026-10-15.md) · [实跑结果与已知问题](docs/agent-loop/CLOUD_SYNC_RESULTS_2026-10-15.md) · [12 张原生截图](docs/agent-loop/screenshots/cloud-sync-20261015/README.md)。API、AI、录音与人物任务统一升级；自动纠错已开启，记忆修订与亲友再分享、连续语音在公网 HTTPS 上实测。属于模拟器验收的内测试用，尚未稳定两秒，人物模拟仍有失败与偏强推断。PR #94 保持未合并。下方各日期记录保留当时状态。

> **2026-10-15 增量交接：** [新增功能、版本范围与分工建议](docs/agent-loop/TEAM_HANDOFF_2026-10-15.md) · [接手运行与发布步骤](docs/agent-loop/HANDOFF_RUNBOOK_2026-10-15.md) · [原速视频与结果入口](docs/agent-loop/demos/20261015/README.md)。继续更新 `codex/continuous-voice-20261014` / [PR #94](https://github.com/ztjklt/Remember-Me/pull/94)，不合并。包含语音提速与 Step 试用、记忆修订联动、ASR 后 LLM 自动校对。代码、ECS 和公开 APK 的启用范围分别列明；自动校对默认关闭，尚未完成云端与手机实跑验收。

> **2026-10-14 Android 0.11.0 连续语音试验版：** [下载安装与语音/校准操作](docs/agent-loop/ANDROID_0110_QUICK_START_2026-10-14.md) · [真实结果、延迟与未完成项](docs/agent-loop/CONTINUOUS_VOICE_RESULTS_2026-10-14.md) · [队长会议要求对照](docs/agent-loop/CONTINUOUS_VOICE_REQUIREMENTS_2026-10-14.md)。ECS与同签名APK已接入持续收音、流式播放和插话取消，先向两个陈守义演示账号开放。模型生成与审阅仍需数秒，尚未达到1—2秒自然接话；实体手机声学与耳机未验收。PR #94待团队评审，未合并。

> **2026-10-13 Android 0.10.0 云端交付：** [下载安装、账号与双角色体验](docs/agent-loop/ANDROID_0100_QUICK_START_2026-10-13.md) · [部署、验证结果与剩余事项](docs/agent-loop/CLOUD_TWIN_DELIVERY_2026-10-13.md) · [录音豆 SDK 接入准备](apps/android/docs/WORK_3200_PREPARATION.md)。ECS 已升级 Twin 与亲友/声音接口，签名内测 APK 直连公网 HTTPS。设备 SDK 仍是接入准备，不是录音豆实机通过。

> **2026-10-12 Twin 与交互融合交接（历史）：** [本次功能、进展与待解决项](docs/agent-loop/TWIN_TEAM_HANDOFF_2026-10-12.md) · [新电脑本地运行](docs/agent-loop/TWIN_LOCAL_SETUP_2026-10-12.md) · [10 张 Android 实跑截图](docs/agent-loop/screenshots/twin-20261012/README.md)。已融合右侧两批按钮与音频交互；该日期的结果仅为本地评审。ECS 后续升级见上方 10 月 13 日记录。CI APK 仍默认连接模拟器宿主机 `10.0.2.2:8891`，不要与签名云端包混用。

> **Android 0.9.3：** [下载并开启简明模式](docs/agent-loop/ANDROID_093_QUICK_START.md) · [范围、实跑结果与截图](docs/agent-loop/SIMPLE_MODE_2026-10-11.md)。记录者可直接讲述、听故事和继续整理，亲友直达原音；保留完整模式和花田。客户端更新，ECS 沿用现有版本；真人长辈试用仍待进行。

> **Android 0.9.2：** [安装与双角色体验](docs/agent-loop/ANDROID_092_QUICK_START.md) · [人物理解、真实问答与 ECS 修复](docs/agent-loop/PROFILE_VALIDITY_FIX_2026-10-11.md) · [模拟器验收与截图](docs/agent-loop/PROFILE_ANDROID_ACCEPTANCE_2026-10-11.md)。修复新增问答同意导致人物理解失效，以及 Android 15 页面重建白边；ECS 已更新，数据库与权限范围不变。

> **Android 0.9.1：** [下载安装与两种身份使用说明](docs/agent-loop/ANDROID_091_QUICK_START.md) · [藤蔓花径、固定视角与横向故事阅读](docs/mobile-ui/GARDEN_NAVIGATION_2026-10-11.md) · [实跑截图](docs/agent-loop/screenshots/garden-navigation-20261011/README.md) · [Agent 实现及尚未解决的问题](docs/agent-loop/AGENT_CAPABILITIES_2026-10-11.md)。移除双指缩放，修复多空间默认选错；同签名覆盖升级，本轮未更换 ECS 程序。

> **Android 0.9.0：** [下载安装、陈守义十段样例与两人使用说明](docs/agent-loop/ANDROID_090_QUICK_START.md) · [连续花田、人物内容及验收边界](docs/agent-loop/IMMERSIVE_GARDEN_ACCEPTANCE_2026-10-11.md) · [本轮模拟器截图](docs/agent-loop/screenshots/immersive-garden-20261011/README.md)。同签名覆盖升级；新材料已进入ECS，本轮未更换服务端代码。

> **Android 0.8.2：** [花田浏览、背景预览与记忆阅读打磨](docs/agent-loop/ANDROID_GARDEN_POLISH_2026-10-11.md) · [19张本轮截图](docs/agent-loop/screenshots/2026-10-11-garden-polish/README.md)。同签名覆盖升级；本次未重新部署ECS。

> **Android 0.8.1：** [恢复原稿写实蓝花、自然枝叶与花瓣入口](docs/agent-loop/ANDROID_GARDEN_RESTORE_2026-10-11.md)。[下载安装与简单8位演示账号](docs/agent-loop/ANDROID_QUICK_START_2026-10-10.md)。旧包和截图保留；iOS与新版真机未验收。

> **首次试用先看：** [下载安装、公开演示账号、记录者与亲友操作说明](docs/agent-loop/ANDROID_QUICK_START_2026-10-10.md)。公开账号专用于虚构测试，所有试用者共用；原四组内测账号继续私下交接。

> **Android 0.7.1 内测下载：** [下载与双角色操作说明](docs/agent-loop/ANDROID_TEAM_DELIVERY_2026-10-10.md)。2026-10-10 经所有者批准，App HTTPS 可从不同网络访问；注册仍关闭，使用管理员私下提供的普通账号。模型密钥只在 ECS。实体手机和本次 iOS 仍待验收。

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

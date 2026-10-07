# Remember Me Android 架构

首期采用单 `app` module 的分层 Compose 架构，目标是足够清晰以便增长，同时避免为原型创建大量 Gradle module。

UI 消费页面状态与领域模型。生产使用真实仓库，`MockRememberMeRepository` 仅在 androidTest。
`MemoryRepository`、`AudioCaptureService`、`AgentGateway` 与 `HardwareCaptureAdapter` 是当前接入边界；其他未接入接口保持原型性质。
供应商经 HTTP 协议适配，不引入供应商 SDK；实验设置页可显示协议/模型名称以便用户配置。

### Repository assembly boundary

Repository implementations are selected and constructed outside the Compose UI tree, at the application assembly boundary, then passed to navigation and screens through repository interfaces. `MainActivity` provides the real `EpisodeMemoryRepository` as `MemoryRepository`; `RememberMeApp` routes it to `MemoriesScreen`, and the screen only collects its `Flow<Loadable<List<Memory>>>`. Tests inject `MockRememberMeRepository` through the same screen parameter.

Repository construction audit for this change:

| Location | Construction | Classification |
| --- | --- | --- |
| `app/src/main/java/me/remember/app/MainActivity.kt` | `EpisodeMemoryRepository()` | Production assembly binding; outside Compose UI |
| `app/src/androidTest/java/me/remember/app/data/mock/MockRememberMeRepositoryTest.kt` | `MockRememberMeRepository()` | Test fixture; outside production UI |
| `app/src/androidTest/java/me/remember/app/MemoriesInstrumentedTest.kt` | `MockRememberMeRepository()` | Instrumentation fixture injected through `MemoryRepository` |
| `app/src/main/java/me/remember/app/feature/` | None | No repository construction |
| `app/src/main/java/me/remember/app/navigation/` | None | Receives repository interfaces from the app boundary |
| `app/src/main/java/me/remember/app/ui/` | None | No repository construction |

Definition of Done: no composable directly constructs a repository. Switching between the Mock and real implementations requires changing only the application assembly binding, with no screen-code changes. `RepositoryBoundaryTest` enforces the UI boundary; `MemoriesInstrumentedTest` checks both injected Mock content and a real Backend result.

The boundary rule was already present in the repository architecture baseline; this change clarifies where implementations are selected and how the no-screen-change replacement requirement is verified.

### Capability-based capture adapter

`AudioCaptureService` is the app-facing capture boundary. `SelectingAudioCaptureService` selects an available external `HardwareCaptureAdapter` only when it can retrieve the saved recording; otherwise it routes the whole session through the phone-microphone fallback. The selected adapter is pinned from start through pause, resume, and stop, so a device disconnect cannot silently switch an in-progress recording to another source. It also finalizes that selected source on Capture-page exit or Activity stop, retaining the safe recording lifecycle from #46/#60.

Each adapter reports `CaptureDeviceState` and a `CaptureCapabilityProfile`; the app checks advertised capabilities before optional pause/resume, recording retrieval, and local playback operations. The Capture UI hides Pause and Playback when the selected source cannot provide them, while retaining Stop/Save and Upload. It also exposes the latest saved recording and whether a specific recording is available. The phone fallback uses Android's microphone and app-private `filesDir/recordings` storage and reports the capabilities it implements. With no external device present, recording, pause/resume, save, retrieval, and playback continue through this fallback.

The adapter API contains only app-owned Kotlin types. No Work 3200 or vendor SDK types, and no assumptions about markers, live audio, or background recording, cross this boundary. A future hardware implementation can be supplied at the application assembly point without changing `RecordingScreen` or the phone fallback.

电脑模式消费 Backend Contract，跨模块 payload 以 `packages/contracts` 的 schema 为准。
实验本地 BYOK 是用户授权实现，仍待 Product/Integration 追认，张天霁确认后才能合并；不将其写成全项目通用密钥规则。
Android 不绑定具体供应商的 SDK；硬件经 capability profile，无设备时使用手机麦克风。

`Subject` 表示被记录的人，`Actor` 表示当前操作产品的人，两者是不同类型。Creator Mode 与 Legacy Mode 因此可以围绕同一 Subject 切换不同 Actor，而不把 Subject 等同于 Current User。

归档状态以 `Loadable` 表达，处理状态显式区分运行、失败、暂停、完成和无结果。页面不直接依赖供应商或构造仓库。

Phase 1 Backend 接线在 `MainActivity` 组装：`HttpEpisodeGateway` 负责上传/状态/结果 HTTP 边界，`EpisodeFlow` 负责异步状态与安全重试，`EpisodeMemoryRepository` 只发布 Backend 真正返回的 Memory。Compose 页面接收接口和状态，不直接创建 Mock/Real Repository，也不持有 STT、AI 或 Voice Provider 凭据。当前开发环境需输入 Backend 签发的 Actor Token、Subject ID 与录音同意 ID；详见 [联调说明](BACKEND_INTEGRATION.md)。

## 实验本地模式

`MainActivity` 的 Activity ViewModel 装配 `LocalAgentSession`；其中持有引擎、设置草稿及仓库，导航按模式选择既有 `MemoryRepository` 的本地/远程实现。
`CaptureFlowViewModel` 只在内存中交接录音，Activity 重建保留；进程恢复缺失时页面提供返回提示。
`LocalAgentEngine` 经 Mutex 顺序执行一个 Agent 的 CAPTURE/ASK/CORRECT 任务，没有子 Agent、工具执行、检索或压缩。
ASR 检查点先持久化，理解/校正成功才发布新 revision；失败保留任务，用户显式重试或取消。取消理解保留已完成的原文。

| 边界 | 实现与数据 |
| --- | --- |
| 推理 | `HttpLocalModelClient`，语音原生或兼容音频协议、文字兼容接口；模型地址和名称运行时配置 |
| 业务存储 | `SqliteLocalState` journal：episodes/materials/traits/revisions/calibrations/job；内部格式，shared schema 未变 |
| 凭证 | `LocalSettingsStore`：Keystore AES-GCM 加密、no-backup 文件；草稿仅 ViewModel 内存，禁止 saved state |
| 录音 | `RecordingLibrary`：私有录音文件及 sidecar；同一 journal 投影到既有 Memory 模型 |
| 历史 | 本地读取 calibrations；远程仅缓存已知记录，复用 GET by ID，无新增端点 |
| 删除/恢复 | 来源级联失效、内容清除及文件删除；版本不兼容保留原始 payload，恢复导出只投影原文 |

Debug `BuildConfig.LOCAL_AGENT_ENABLED=true`，首次进入本地模式；release 为 false，不打开本地日志/凭证或展示本地入口。
release 忽略旧模式偏好但不删除资料。Backend `REMEMBER_AGENT_ENABLED=false` 是独立服务端实验门，两者无需同步。
本地原文仍发送给用户选择的模型服务，不是离线推理。参数不预置密钥，凭证不进日志、系统备份或导出。
明确留存/恢复范围见 [LOCAL_AGENT.md](LOCAL_AGENT.md)，页面路由见 [SCREEN_FLOW.md](SCREEN_FLOW.md)。

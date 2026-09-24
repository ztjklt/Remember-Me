# Remember Me Android 架构

首期采用单 `app` module 的分层 Compose 架构，目标是足够清晰以便增长，同时避免为原型创建大量 Gradle module。

UI 只消费页面状态与领域模型。Mock repository 负责稳定演示数据；`MemoryRepository`、`PersonModelRepository`、`LegacyRepository`、`AudioCaptureService`、`SpeechToTextService`、`TwinService`、`VoiceCloneService` 与 `HardwareCaptureAdapter` 是替换点，真实实现应在这层之后接入，不改变页面的产品语义。真实供应商名称不进入 UI。

### Repository assembly boundary

Repository implementations are selected and constructed outside the Compose UI tree, at the application assembly boundary, then passed to navigation and screens through repository interfaces. `MainActivity` provides the real `EpisodeMemoryRepository` as `MemoryRepository`; `RememberMeApp` routes it to `MemoriesScreen`, and the screen only collects its `Flow<Loadable<List<Memory>>>`. Tests inject `MockRememberMeRepository` through the same screen parameter.

Repository construction audit for this change:

| Location | Construction | Classification |
| --- | --- | --- |
| `app/src/main/java/me/remember/app/MainActivity.kt` | `EpisodeMemoryRepository()` | Production assembly binding; outside Compose UI |
| `app/src/test/java/me/remember/app/data/mock/MockRememberMeRepositoryTest.kt` | `MockRememberMeRepository()` | Unit-test fixture; outside production UI |
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

客户端只消费 Backend Contract，跨模块 payload 以 `packages/contracts` 的 schema 为准；Android 不直接绑定 DeepSeek、STT、Voice、Supabase 或 Work 3200，也不持有 provider secret。硬件一律经 capability profile，无设备时手机录音路径必须完整可用。

`Subject` 表示被记录的人，`Actor` 表示当前操作产品的人，两者是不同类型。Creator Mode 与 Legacy Mode 因此可以围绕同一 Subject 切换不同 Actor，而不把 Subject 等同于 Current User。

重要页面状态以 `Loadable` 表达 Loading、Content、Empty 和 Error。首期重点渲染 Content，导航和 Demo Menu 负责验证主流程。后续加入依赖注入时，应保持接口边界并将 ViewModel 按 feature 引入，而不是让页面直接依赖网络或硬件实现。

Phase 1 Backend 接线在 `MainActivity` 组装：`HttpEpisodeGateway` 负责上传/状态/结果 HTTP 边界，`EpisodeFlow` 负责异步状态与安全重试，`EpisodeMemoryRepository` 只发布 Backend 真正返回的 Memory。Compose 页面接收接口和状态，不直接创建 Mock/Real Repository，也不持有 STT、AI 或 Voice Provider 凭据。当前开发环境需输入 Backend 签发的 Actor Token、Subject ID 与录音同意 ID；详见 [联调说明](BACKEND_INTEGRATION.md)。

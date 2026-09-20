# Remember Me Android 架构

首期采用单 `app` module 的分层 Compose 架构，目标是足够清晰以便增长，同时避免为原型创建大量 Gradle module。

UI 只消费页面状态与领域模型。Mock repository 负责稳定演示数据；`MemoryRepository`、`PersonModelRepository`、`LegacyRepository`、`AudioCaptureService`、`SpeechToTextService`、`TwinService`、`VoiceCloneService` 与 `HardwareCaptureAdapter` 是未来替换点。真实供应商名称不进入 UI。

`Subject` 表示被记录的人，`Actor` 表示当前操作产品的人，两者是不同类型。Creator Mode 与 Legacy Mode 因此可以围绕同一 Subject 切换不同 Actor，而不把 Subject 等同于 Current User。

重要页面状态以 `Loadable` 表达 Loading、Content、Empty 和 Error。首期重点渲染 Content，导航和 Demo Menu 负责验证主流程。后续加入依赖注入时，应保持接口边界并将 ViewModel 按 feature 引入，而不是让页面直接依赖网络或硬件实现。

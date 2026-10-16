# Android 录音与超时核查

核查日期：2026-10-16（Asia/Singapore）。本轮只新增本报告，没有修改 Android 源码、现有 UI 工作、Contract、部署或账号数据。

## 版本边界

| 检查对象 | 版本与目录 | 可以说明什么 |
| --- | --- | --- |
| 当前工作区 Android | `673c2a2`，`/Users/jitian/Documents/ChatGPT/Remember Me/apps/android`，另有原有 UI 未提交修改 | 默认入口是本地录音与本机转写；`MainActivity.kt:22` 只注入 AudioCapture 与 Sherpa ASR，没有 Backend processor。不能用这套源码解释已安装云端 Android 的所有行为。 |
| 历史云端集成 Android | PR #89 固定快照 `13280fe`；另只读检查 `/Users/jitian/.codex/worktrees/android-team-local-test/Remember Me` 的 `cc500d2` | 已有登录、原音上传、核对、记忆、文字 Twin 和分享。这两个快照的下述网络及刷新实现一致。历史发布版的来源说明见 `ANDROID_CORE_AUDIT_2026_10_10.md:5`，本轮没有重验 APK 内容。 |

下文 Kotlin 类路径均从各自 `apps/android/app/src/main/java/me/remember/app/` 起算，Gradle 与资源路径从各自 `apps/android/` 起算；“集成”指上述独立历史集成工作区，不能误认为当前默认装配已包含这些类。

## 确认的缺口与可靠性问题

- **当前包的本机转写缺模型。** `app/src/main/assets/paraformer` 只有 `tokens.txt`，没有 `model.int8.onnx`；当前 `data/repository/AndroidSherpaOnnxAsrService.kt:20` 因此会明确失败并保留原音。这是功能未装配，不是网络超时。目录中的原音录制与回听不依赖网络。
- **集成版一次全量刷新会阻塞其他操作。** 集成 `integration/NativeWorkbenchModel.kt:225` 顺序请求 spaces、stories、grants、requests、capabilities、portrait 等，Owner 且相关能力开启时共 15 个请求；`integration/BackendClient.kt:100` 对每个请求设置连接 15 秒、读取 210 秒。`NativeWorkbenchModel.kt:516` 共用 `busy`，`261` 的开始录音也检查此标记；`138` 每 8 秒检查是否自动刷新。慢请求会使页面长时间处于忙碌状态。210 秒是每次读取等待配置，并非整轮总期限；本轮未制造网络故障验证实际最坏耗时。
- **集成版刷新失败会清空已展示内容。** 集成 `NativeWorkbenchModel.kt:214` 任一刷新异常清空 stories、portrait、answer、候选等，并停止播放。这里确认的是代码行为；没有证据表明服务端数据因此删除。
- **集成版上传与后续刷新共用错误出口。** 集成 `NativeWorkbenchModel.kt:322` 已持久保存接收的 Episode，`330` 写入“上传已接收”后仍执行全量刷新，刷新失败进入 `523` 的通用错误。因此上传已接收也可能同时出现操作失败提示；需区分原音接收与列表刷新，不应推断原音丢失。
- **实时通话不是这两套 Android 实现已有的能力。** 当前 Twin 明示尚未接入（`feature/ChatHistoryScreen.kt:44`）；所查历史集成版提供文字 Twin，没有实时语音通话。用户当前的通话超时需继续按实际 iOS／服务端及安装版本定位。

另有待复现风险：当前 `AndroidSherpaOnnxAsrService.kt:70` 的 MediaCodec 解码循环缺少协程取消检查和无进度截止，异常解码器可能持续等待。缺模型时无法进入此路径，本轮没有把它记为已复现故障。

## 只读服务连接

历史集成 `app/build.gradle.kts:37` 的 internal 服务地址是 `https://39.108.183.47`，对应 internal 专用证书配置，不是当前 iOS 后端。使用该工作区原有 `app/src/internal/res/raw/remember_ecs_ip_demo.pem` 作为可信证书，执行一次匿名 `GET /api/v1/service-info`，得到 HTTP 200，耗时约 0.216 秒，返回 `api_version=0.7.0`、`release_id=9f70117ee6ae0ad27e8910cfb753a640169018e5`、`registration_allowed=false`。未登录、未发送凭据、未改数据。这只证明当时该公开端点可达，不能证明录音处理或 Twin 链路正常。

系统默认 curl 信任库首次无法验证该自签证书；随后按应用已有信任配置验证成功，没有关闭 TLS 校验。此现象不应直接记为 Android 证书故障。

## 实际执行的验证

在当前工作区 `apps/android` 执行：

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
ANDROID_HOME=/Users/jitian/Library/Android/sdk \
./gradlew testDebugUnitTest assembleDebug lintDebug
```

结果：`BUILD SUCCESSFUL`，18 项单元测试全部通过，0 failure、0 error、0 skipped；APK 构建与 lint 通过。18 项包括 RepositoryBoundary 1、MockRepository 1、RecordingWorkflow 9、CaptureState 7。构建有 SDK 元数据版本等警告，不影响此次结果。最初未设 Java 的尝试失败；Android Studio 附带 JDK 25 也不适用于此 Gradle，改用已安装 JDK 17 后通过。

`adb devices` 无连接设备；没有运行仪器测试，没有验证实体 Android 麦克风、长录音、后台、解码、断网恢复或安装版本。未执行历史集成版构建、真实上传、账号登录、Twin 提问或实时通话。上述单元和构建结果不能代替真人端到端验收。

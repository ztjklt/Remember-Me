# Work 3200 离线接入准备

> 2026-10-16 更新：下文保留为此前准备阶段的记录。现已新增主 App 设备页面、可选私有 SDK 运行适配、服务端授权接口、下载校验和基于官方固定帧格式的试听解码器。当前实现与实物验收边界见 [设备联调说明](WORK_3200_DEVICE.md)。历史的“未进入主 App”不再描述新设备构建；真实蓝牙与实际录音仍需现场验收。

本批已实现可以离线验证的硬件前置模块，未连接录音豆。主 App 没有实例化厂商 SDK，也没有新增设备 UI。现有手机录音、后台转写和人工核对仍是工作路径；这些代码不构成真实设备验收。

## 已实现的边界

`app/src/main/java/me/remember/app/hardware/`：

- `Work3200Contract.kt`：不含厂商类型的能力、完整六字段 AuthResult、设备文件元信息及无凭证默认 provider。凭证不使用自动输出字段值的 `toString`。没有 app_key 配置入口。
- `Work3200Session.kt`：一次 SDK 初始化允许离线结果后再收到在线结果；`success=true` 但 `tokenExpired=true` 时要求续期。会话/操作票据阻止旧回调污染新用户，设备列表去重、传输字节进度、重复连接及倒退状态也有保护。`FILE_RECEIVED` 只表示 SDK 文件收到，不能表示可播放或可上传。
- `Work3200ImportJournal.kt`：独立应用私有根目录，`raw/` 保留 SDK 原文件，`prepared/` 保存派生音频，原子写入 `entries/` 台账。以服务器、Actor、Subject、设备本地代号和文件 ID 隔离；导入重试复用持久化 key/Episode，内容冲突拒绝。读取、准备、关联 Episode 均校验调用方作用域；标识/路径穿越拒绝，上传前重新核对两个文件的哈希。
- `Work3200Audio.kt`：仅检查 16-bit PCM RIFF/WAVE 的真实头、chunk 边界、大小、采样率、声道和帧对齐。改名的 raw Opus、截断/伪 WAV 被拒绝。**这是格式检查器，不是 Opus 解码器，也不证明派生文件与原始录音的语音一致。**

设备唯一代号必须是应用生成的 `[A-Za-z0-9_-]{1,128}` 本地 pseudonym，不能用不可信设备名、MAC 或文件路径。SDK 的 MAC/UUID 只用于传输连接；文件 ID 是整数元信息。调用方应在授权时固定 server/Actor/Subject，并在回调注册时捕获票据；不得在旧回调交付时从新会话取票据。

适配器只暴露已知能力：已有录音的暂停/恢复、离线文件、标记接收。没有“从空闲开始录音”“结束录音”“创建标记”“设备说话”实现，不能将 pause/resume 冒充 start/stop。硬件不可用时凭证 provider 返回 null，手机流程不依赖硬件。

## 真实 SDK 编译示例

`hardware-sdk-example/` 在主 App source set 之外。`Soundcore1302Bridge.java` 引用真实 `SoundcoreSDK`、`SDKInitConfig`、认证/扫描/连接/文件回调；`SoundcoreCallbacks.java` 实现当前 1.3.02 的 38 个业务回调签名。示例实际写出扫描、连接、同步时间、离线列表、蓝牙传输、暂停/恢复的调用，并把认证与文件模型转成前述类型。

示例注入静默 `LogInterface`，因为 SDK 的日志模板会输出 token；也不能直接输出 SDKInitConfig。鉴权回调保留 `success/isOnline/licenseValid/licenseExpireTime/tokenExpired/error`，error 的字符串表示已屏蔽消息。初始化凭证由调用方提供；示例没有 get_token HTTP 调用、固定 token、license 或 app_key。

只编译，不执行 SDK。先构建 App 类，再运行：

```powershell
./hardware-sdk-example/compile.ps1 `
  -JdkDirectory '<JDK 17 directory>' `
  -SdkClassesJar '<external SDK 1.3.02 classes.jar>' `
  -AndroidJar '<Android SDK>/platforms/android-35/android.jar' `
  -KotlinStdlibJar '<Gradle cache>/kotlin-stdlib-2.0.21.jar' `
  -AppClassesDirectory './app/build/tmp/kotlin-classes/debug'
```

本轮该命令已成功。Java 编译允许保持主工程 Kotlin 2.0.21；没有关闭 Kotlin metadata 检查，没有升级 Kotlin，没有将 SDK jar 加入 App。**这不证明 SDK 完整运行依赖已经解析、可以被 D8/R8 完整打包，或真实设备可用。** Android SDK 发行说明为 Kotlin 2.2.21 / coroutines 1.11.0 / OkHttp 5.2.1 / Ktor 2.3.13，与旧文档依赖表冲突，正式集成仍需准确依赖图和独立 APK 验证。

`syncTime(UInt)` 被 Kotlin 生成为 `syncTime-jXDDuk8`，Java 示例以已核对的 1.3.02 方法名反射调用。javac 不验证这个反射调用；公开 jar 签名已静态核对，运行失败会给出 `sync_time_binding` 错误。正式 Kotlin 2.2 bridge 可直接调用 `syncTime`。

示例会拒绝前一初始化/连接尝试的回调，并验证收到文件仍在指定下载目录内。SDK 的全局业务回调没有请求 ID，因此同一连接内重叠列表/传输必须由调用方串行化，并绑定 Session 的操作票据；示例本身不是可直接打开给用户的完整控制器。未选取的 WiFi/OTA/实时/设备日志回调为显式 no-op，不代表功能完成。

## 当前测试和交接入口

`Work3200SessionTest` 与 `Work3200ImportTest` 使用完整的假回调事件和本地临时文件。测试覆盖授权续期/过期、多用户旧回调、分批列表、重复导入/重启恢复、Episode重放、文件冲突、路径穿越、跨账户读取/准备/上传、raw Opus改名、WAV损坏以及原音/派生音修改。标准 WAV 是手工构造的测试信号，不能当作 SDK 实机样本。

```powershell
./gradlew.bat --offline :app:testDebugUnitTest --tests 'me.remember.app.hardware.*'
./gradlew.bat --offline test assembleDebug
```

本机已有依赖缓存位于 `D:/codex_work/remember-me-toolchain/gradle`；默认 `C:/Users/.../.gradle` 离线缺部分依赖，首轮因此未到测试。应通过本进程 `GRADLE_USER_HOME` 指向已完整安装的缓存。不要用缓存缺失失败声称产品测试失败，也不要隐藏未运行。

与 UI/后台连接时，只有 `uploadCandidate(importId, currentScope)` 返回的容器文件才可进入硬件上传通路；其 `episodeId` 非空就复用既有 Episode，网络结果未知时用同一 idempotencyKey 重试。台账不会替用户同意上传，不会自动发起转写，不会删除设备或本地原音。调用方还须固定上传开始时的会话及作用域，不接受用户切换后的异步结果。

## 实机前仍需的材料

1. get_token 的完整请求/签名/响应、比赛环境、App deviceId/用户绑定和 token/license续期规则。不要根据术语猜签名。厂商离线 license 的生成与验证不能伪造。
2. v1.3.02 完整 Demo/POM/依赖，以及二进制和 APK 的明确分发范围。工具资料的比赛凭证不得外传，SDK 的通用公开再分发授权未被资料证明。仓库仅提交自有适配代码，不提交厂商库/资料/凭证。
3. 当前固件的 30–60 秒 raw 文件、回调序列与解码示例。文档所称裸 Opus 16kHz/双声道/20ms/160byte 尚未经设备确认；没有按 160 字节猜拆包，没有执行许可试探请求。
4. 确认双声道含义与容器封装后再实现 `raw → prepared WAV`。当前 Paraformer 请求只选第 0 路，不能默认覆盖双声道全部内容。格式检查通过仅证明 WAV 结构，不证明声道/文字质量。
5. 在设备按键完成录音后，验证绑定/充电盒确认、蓝牙权限、时间同步、列表完整性、断连/重试及原音回放，再接主 App 的导入入口。UI、runtime permission 与后台 adapter 的真实接线仍是后续工作。

首轮不要求 WiFi、OTA、实时传输。现场改动范围取决于上述鉴权、依赖与音频材料，当前不能保证必然只需改配置。

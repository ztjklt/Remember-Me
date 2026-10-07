# Remember Me Android Prototype

Remember Me 是一个以声音为入口、可追溯且可纠错的 Digital Twin 与数字托付产品。本仓库是 Android 原生交互原型：录音、上传、处理、Memory 与实验 Agent 接入 Backend；声音克隆、硬件和 Legacy 体验仍为 Mock 或接口占位。

## 手机独立模式（1.3-local）

Debug 新版默认在手机保存原文、理解、问答、校正及未完成任务，直接调用用户配置的 ASR/LLM。release 关闭实验本地入口，使用电脑模式。
不需要电脑服务、ADB 或手填会话 ID；仍需要网络。安装和设置见 [手机独立模式](docs/LOCAL_AGENT.md)。
电脑模式保留，旧电脑数据不会自动迁入手机。多 Agent、Memory 重构和内容压缩未纳入本轮。

## 运行

要求：Android Studio Stable、JDK 17、Android SDK 35，以及手机或 Android Emulator。使用 Android Studio 打开 `apps/android`，等待 Gradle Sync，选择设备，运行 `app`。

已安装 APK 的使用者不需要运行 Gradle；Gradle 是电脑编译工具，不会启动 Backend。
`JAVA_HOME` 报错、现有演示会话的 ID 填写和无线连接步骤见 [手机联调快速开始](docs/PHONE_QUICKSTART.md)。

命令行（在 `apps/android` 目录，先配置 JDK/SDK 环境）：

```bash
./gradlew clean test assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n me.remember.app/.MainActivity
```

## Local audio capture

Capture requests `RECORD_AUDIO` at runtime after explaining that microphone audio is stored in app-private storage. Recordings use AAC in an MPEG-4 container (`audio/mp4`, `.m4a`), 44.1 kHz, mono. Each recording has a JSON sidecar in `files/recordings` with `durationMillis`, `mimeType`, `byteSize`, `sampleRate`, `channelCount`, and `created_at`. The Capture screen can pause, resume, stop, and play the saved file locally. Upload and backend processing are not part of this local capture path. See [录音权限与本地存储](docs/CAPTURE_PERMISSION_AND_STORAGE.md) for permission denial, file lifecycle, and backup behavior.

## 产品评审路径

启动后依次完成 Welcome → Explanation → Consent → Introduce → Recording → Processing → Twin Birth → Voice Seed → Creator Home。Creator Home 右上角 `•••` 打开 Demo Menu，可直达 Calibration、Handover 和 Legacy Mode。

## 工程结构

- `core/designsystem`：Remember Me 颜色、字体、间距和形状
- `ui/components`：可复用 Compose 组件
- `feature`：按体验区域拆分的页面
- `navigation`：首期导航图
- `model`：不把 Subject 与当前 Actor 写死的领域模型
- `data/repository`：未来服务接口
- `data/mock`：稳定且非真实个人信息的 Mock 数据

Mock/Real 切换的边界由 repository 与 service interfaces 定义。可以用构造注入替换 `MockRememberMeRepository`，无需修改页面的产品语义。

Phase 1 Backend 路径已 COMMITTED，通过 shared contract 接入 Backend：真实录音、上传、Episode 与 processing state、并展示真实 Memory。该路径不持有 provider secret，经 Backend Contract 与 Adapter 调用。2026-10-07 用户授权的实验本地模式仍待 Product/Integration 追认（张天霁确认后才能合并），见根目录 AGENTS.md：用户自行填写 ASR/LLM 配置，Key 由 Android Keystore 加密保存；不扩展至 Voice、Supabase 或 Work 3200 SDK。

更多信息见 [架构](docs/ARCHITECTURE.md)、[开发说明](docs/DEVELOPMENT.md)、[CI](docs/CI.md) 和 [下一阶段](docs/NEXT_PHASE.md)；Phase 规划见 [Task Brief](../../docs/team/01_LIUXIUXIAN_ANDROID_HARDWARE.md) 与 [Roadmap](../../docs/roadmap/ROADMAP.md)。

Phase 1 真实上传、状态查询与 Memory 展示的本地配置和验收步骤见 [Backend 联调说明](docs/BACKEND_INTEGRATION.md)。该路径需要 Backend Actor Token、Subject ID、有效录音同意 ID 和运行中的 worker；fixture 路径不能代替真实 STT/AI 与真机验收。

## Agent loop integration

`1.1-agent`（versionCode 2）将网页版已验证的流程接入原生 Compose 页面：

1. 录音页点击“查看已有录音与理解”，连接已有 Backend 会话；也可先录音、上传，处理完成后进入理解页。
2. 主页面依次显示“记忆原文”“当前理解”“提问与回答”“校正与更新”。上传入口显示本次录音，其他入口显示最近的授权录音。
3. 点击“提问”一次生成并保存待校正回答。填写本人校正，点击“保存校正并更新理解”，再提问验证。修改问题或理解版本变化时必须重新提问。
4. 校正后保留旧回答和本人文字，展示更新结果。回答依据、模型版本、五维比较、恢复记录、同意撤回和连接设置位于折叠区。

在电脑模式中，Provider 密钥只在服务端，Backend 会话 token 只在内存；fixture 页面明确标注固定转写。设备接入见 [Backend 联调说明](docs/BACKEND_INTEGRATION.md)，供应商和既有实验 API 见 [Agent loop guide](../../docs/architecture/AGENT_CORE_LOOP.md)。本次构建与运行结果见 [安卓验证记录](../../docs/verification/ANDROID_AGENT_2026_10_06.md)。

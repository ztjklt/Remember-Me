# Remember Me Android

当前入口是 UI v6 的「今天 / 档案 / 我的」。可以在手机录音、暂停、保存、播放、核对本机转写，并在档案中检索录音和已整理的记忆。#78 的画像与关系图页面代码仍在仓库中，但尚未接入真实数据，不能当作已生成的 Person Model。

默认构建不配置记忆整理服务。核对后的文字只会在用户明确同意、且应用装配了 `ReviewedMemoryProcessor` 时发送；当前版本会提示服务未连接。本机 ASR 需要单独提供模型权重。DeepSeek 等供应商凭证只应配置在 Backend，不能放入 Android APK。

## 运行

要求：Android Studio、JDK 17、Android SDK 35。使用 Android Studio 打开 `apps/android`，等待 Gradle Sync，然后运行 `app`。

命令行：

```bash
./gradlew testDebugUnitTest assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n me.remember.app/.MainActivity
```

## Local audio capture

Capture requests `RECORD_AUDIO` at runtime after explaining that microphone audio is stored in app-private storage. Recordings use AAC in an MPEG-4 container (`audio/mp4`, `.m4a`), 44.1 kHz, mono. Each recording has a JSON sidecar in `files/recordings` with `durationMillis`, `mimeType`, `byteSize`, `sampleRate`, `channelCount`, and `created_at`. The Capture screen can pause, resume, stop, and play the saved file locally. Upload and backend processing are not part of this local capture path. See [录音权限与本地存储](docs/CAPTURE_PERMISSION_AND_STORAGE.md) for permission denial, file lifecycle, and backup behavior.

## 产品评审路径

「今天」→「开始录音」→ 保存并查看录音 → 本地播放／转写与核对 →「档案」。整理服务未连接时，录音与核对文字仍保留在手机，可稍后重试。

## 工程结构

- `core/designsystem`：Remember Me 颜色、字体、间距和形状
- `ui/components`：可复用 Compose 组件
- `feature`：按体验区域拆分的页面
- `navigation`：首期导航图
- `model`：不把 Subject 与当前 Actor 写死的领域模型
- `data/repository`：本地录音、转写及可注入的记忆处理接口
- `data/mock`：尚未接入的演示数据

记忆整理通过 `ReviewedMemoryProcessor` 接入。客户端必须经过共享 Backend Contract，不在构建配置或本地文件中保存供应商密钥。

Phase 1 — Golden Path 已 COMMITTED，Android 必须通过 shared contract 接入 Backend：真实录音、上传、Episode 与 processing state、并展示真实 Memory。但 Android **不得直接调用** DeepSeek、STT、Voice API、Supabase 或 Work 3200 SDK，也不持有任何 provider secret——一律经 Backend Contract 与 Adapter。

更多信息见 [架构](docs/ARCHITECTURE.md)、[开发说明](docs/DEVELOPMENT.md)、[CI](docs/CI.md) 和 [下一阶段](docs/NEXT_PHASE.md)；Phase 规划见 [Task Brief](../../docs/team/01_LIUXIUXIAN_ANDROID_HARDWARE.md) 与 [Roadmap](../../docs/roadmap/ROADMAP.md)。

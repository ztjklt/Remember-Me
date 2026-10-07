# Remember Me Android

2026-10-07 默认入口已改为连接共享后端的原生 Compose 工作台，沿用 #85 的植物品牌和自然背景。输入后端身份凭据后，服务端返回本人／授权读者空间。录音原音保存在本机，上传以 `ANDROID_MIC` 标记来源，实际转写必须核对后才能整理。故事、来源原音、搜索、问答、故事授权／撤销、新录音修订、问题请求和人物候选均通过同一后端读取与操作。

后端地址默认 `http://10.0.2.2:8000`（Android 模拟器）；USB 手机可执行 `adb reverse tcp:8000 tcp:8000` 后使用 `http://127.0.0.1:8000`。身份凭据只在本次会话中保留。上传和云端文字处理需明确确认；每日提醒默认关闭。供应商凭证只配置在 Backend，不能放入 Android APK。完整路径、API、测试与未验证项见 [原生集成记录](../../docs/agent-loop/ANDROID_INTEGRATION.md)。原有本地原型和本机 ASR 代码保留，其权重仍需另行提供。

## 运行

要求：Android Studio、JDK 17、Android SDK 35。使用 Android Studio 打开 `apps/android`，等待 Gradle Sync，然后运行 `app`。

命令行：

```bash
./gradlew testDebugUnitTest assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n me.remember.app/.MainActivity
```

## Local audio capture

Capture requests `RECORD_AUDIO` at runtime after explaining that microphone audio is stored in app-private storage. Recordings use AAC in an MPEG-4 container (`audio/mp4`, `.m4a`), 44.1 kHz, mono. Each recording has a JSON sidecar in `files/recordings` with `durationMillis`, `mimeType`, `byteSize`, `sampleRate`, `channelCount`, and `created_at`. The native Capture page can pause, resume, stop, and play the saved file locally. Separate confirmation uploads a retained copy to Backend; backend STT readiness and mandatory transcript review precede memory extraction. See [录音权限与本地存储](docs/CAPTURE_PERMISSION_AND_STORAGE.md) for permission denial, file lifecycle, and backup behavior.

## 产品评审路径

身份登录 → 选择本人空间 →「记述」本机录音 → 明确确认上传 →「故事」核对转写并同意文字整理 → 阅读真实记忆 →「提问」搜索／云端问答与来源原音 →「管理」授权、修订、请求与人物候选。服务失败保留原音和已核对文字，显示实际错误并提供重试。真机录音、原音播放与真实云端闭环尚未在本轮验证，不由 APK 构建通过推断。

## 工程结构

- `core/designsystem`：Remember Me 颜色、字体、间距和形状
- `integration`：原生工作台、共享后端传输、会话隔离、录音上传与修订恢复
- `ui/components`：可复用 Compose 组件
- `feature`：按体验区域拆分的页面
- `navigation`：首期导航图
- `model`：不把 Subject 与当前 Actor 写死的领域模型
- `data/repository`：本地录音、转写及可注入的记忆处理接口
- `data/mock`：尚未接入的演示数据

默认工作台通过共享后端完成记忆整理；保留的旧本地原型仍使用 `ReviewedMemoryProcessor` 注入边界。客户端不在构建配置或本地文件中保存供应商密钥。

Phase 1 — Golden Path 已 COMMITTED，Android 必须通过 shared contract 接入 Backend：真实录音、上传、Episode 与 processing state、并展示真实 Memory。但 Android **不得直接调用** DeepSeek、STT、Voice API、Supabase 或 Work 3200 SDK，也不持有任何 provider secret——一律经 Backend Contract 与 Adapter。

更多信息见 [架构](docs/ARCHITECTURE.md)、[开发说明](docs/DEVELOPMENT.md)、[CI](docs/CI.md) 和 [下一阶段](docs/NEXT_PHASE.md)；Phase 规划见 [Task Brief](../../docs/team/01_LIUXIUXIAN_ANDROID_HARDWARE.md) 与 [Roadmap](../../docs/roadmap/ROADMAP.md)。

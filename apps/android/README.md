# Remember Me Android

2026-10-10：默认入口是原生 Compose 工作台，沿用 #85 的植物品牌和自然背景。普通账号登录后进入本人／授权读者空间，不需要填写 actor_id。原音保存在本机，上传以 `ANDROID_MIC` 标记来源，经 ECS Paraformer 转写后必须核对才能整理。故事、八个内容侧面、四个人物视图、候选审核、来源播放、问答、邀请、修订与问题请求通过共享后端处理。查看[团队运行说明](../../docs/agent-loop/TEAM_RUNBOOK_2026-10-10.md)与[19 张实跑截图](../../docs/agent-loop/screenshots/2026-10-10/README.md)。

`internal` 0.7.1 包直接连接 `https://39.108.183.47`，保留该 IP 的证书验证；不需要电脑 ASR 或 ADB reverse。[下载安装与双角色说明](../../docs/agent-loop/ANDROID_TEAM_DELIVERY_2026-10-10.md)。经所有者批准，App IPv4 HTTPS 入口不再限制指定 Wi-Fi，注册仍关闭，普通账号由管理员提供。源码 `debug` 默认 `http://127.0.0.1:8877`，仅本机开发时才需要 ADB reverse；连接 ECS 时按下面命令显式传入 URL；PR 的 CI 会显式构建 ECS debug 包。上传和云端模型处理需明确确认，每日提醒默认关闭。供应商密钥只在服务端。原有本地原型和本机 ASR 代码保留，当前共享后端主线不依赖手机 ASR 权重。

## 运行

要求：Android Studio、JDK 17、Android SDK 35。使用 Android Studio 打开 `apps/android`，等待 Gradle Sync，然后运行 `app`。

命令行：

```bash
./gradlew testDebugUnitTest assembleDebug -PrememberServiceUrl=https://39.108.183.47
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n me.remember.app/.MainActivity
```

## Local audio capture

Capture requests `RECORD_AUDIO` at runtime after explaining that microphone audio is stored in app-private storage. Recordings use AAC in an MPEG-4 container (`audio/mp4`, `.m4a`), 44.1 kHz, mono. Each recording has a JSON sidecar in `files/recordings` with `durationMillis`, `mimeType`, `byteSize`, `sampleRate`, `channelCount`, and `created_at`. The native Capture page can pause, resume, stop, and play the saved file locally. Separate confirmation uploads a retained copy to Backend; backend STT readiness and mandatory transcript review precede memory extraction. See [录音权限与本地存储](docs/CAPTURE_PERMISSION_AND_STORAGE.md) for permission denial, file lifecycle, and backup behavior.

## 产品评审路径

普通账号登录 →「今天」本机录音/试听 → 同意上传 →「档案」核对转写、同意整理、看故事/记忆/人物依据 →「对话」提问与来源原音 →「我的」邀请、批准、修订与补问。模拟器新录音、真实 ECS 处理和亲友操作已有分步截图；输入为注入模拟麦克风的虚构合成语音。真机、全部恢复行为及 iOS 仍需独立验证，不由构建成功推断。

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

# Remember Me Android Prototype

Remember Me 是一个以声音为入口、可追溯且可纠错的 Digital Twin 与数字托付产品。本仓库是第一阶段 Android 原生交互原型，重点验证 Onboarding、Capture、Twin Birth、Voice Seed、Creator Home 与 Legacy Mode 的产品体验；所有 AI、声音克隆、后端与硬件能力目前均为 Mock 或接口占位。

## 运行

要求：Android Studio Stable、JDK 17、Android SDK 35、Android Emulator。使用 Android Studio 打开仓库根目录，等待 Gradle Sync，选择 `RememberMe_API_35`（或任意 API 35 手机模拟器），运行 `app`。

命令行：

```bash
./gradlew clean test assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n me.remember.app/.MainActivity
```

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

Phase 1 — Golden Path 已 COMMITTED，Android 必须通过 shared contract 接入 Backend：真实录音、上传、Episode 与 processing state、并展示真实 Memory。但 Android **不得直接调用** DeepSeek、STT、Voice API、Supabase 或 Work 3200 SDK，也不持有任何 provider secret——一律经 Backend Contract 与 Adapter。

更多信息见 [架构](docs/ARCHITECTURE.md)、[开发说明](docs/DEVELOPMENT.md)、[CI](docs/CI.md) 和 [下一阶段](docs/NEXT_PHASE.md)；Phase 规划见 [Task Brief](../../docs/team/01_LIUXIUXIAN_ANDROID_HARDWARE.md) 与 [Roadmap](../../docs/roadmap/ROADMAP.md)。

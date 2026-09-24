# Remember Me Android 开发说明

使用 Kotlin、Jetpack Compose、Material 3、Compose Navigation、Coroutines Flow、Gradle Kotlin DSL 和 Version Catalog。最低 Android 版本为 26，编译和目标 SDK 为 35，Java toolchain 为 17。

开发节奏应保持每一阶段都能 `./gradlew test assembleDebug`。新增页面先使用可预期 Mock 数据，随后才接 ViewModel 和实现类。不得在 UI 内调用具体 AI、Voice 或硬件供应商。Consent scope 必须保持独立，Original Evidence 与 AI Simulation 必须有文字标签而不能只依赖颜色。

调试评审使用 Home 右上角 Demo Menu。Release 版本前应通过 `BuildConfig.DEBUG` 隐藏该入口，并补齐 instrumentation smoke test。

## 本地录音生命周期

录音页面离开组合或进入后台时，会结束仍在运行（包括已暂停）的录音并保存音频和 sidecar；重新进入页面会读回最近保存的录音并显示播放入口。若音频太短导致系统无法完成文件，录音服务会清理无效文件；页面仍可见时会显示保存失败。测试用权限检查入口可注入，用于验证缺少麦克风权限的界面，不在运行中的 instrumentation 进程内撤销权限。

## 本地验证与 CI

本地最低验证命令为 `./gradlew --no-daemon test assembleDebug --stacktrace`。CI 使用仓库专属的 self-hosted macOS ARM64 Runner 执行同一条真实测试与构建命令，并上传 Debug APK；Runner、网络和安全边界见 [CI.md](CI.md)。CI 不使用跳过测试或强制成功的占位步骤。

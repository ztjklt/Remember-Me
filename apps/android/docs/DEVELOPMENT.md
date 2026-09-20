# Remember Me Android 开发说明

使用 Kotlin、Jetpack Compose、Material 3、Compose Navigation、Coroutines Flow、Gradle Kotlin DSL 和 Version Catalog。最低 Android 版本为 26，编译和目标 SDK 为 35，Java toolchain 为 17。

开发节奏应保持每一阶段都能 `./gradlew test assembleDebug`。新增页面先使用可预期 Mock 数据，随后才接 ViewModel 和实现类。不得在 UI 内调用具体 AI、Voice 或硬件供应商。Consent scope 必须保持独立，Original Evidence 与 AI Simulation 必须有文字标签而不能只依赖颜色。

调试评审使用 Home 右上角 Demo Menu。Release 版本前应通过 `BuildConfig.DEBUG` 隐藏该入口，并补齐 instrumentation smoke test。

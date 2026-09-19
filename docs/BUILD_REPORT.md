# Remember Me Android Build Report

报告日期：2026-09-19。当前状态是工程与产品原型代码已完成首轮搭建，Gradle 配置检查成功；由于 Mac 锁屏且 Google SDK 下载连接反复重置，Android SDK、APK 编译和 Emulator 运行尚未完成，因此本报告明确标记为待设备验收，不宣称第一阶段已全部完成。

## 安装和配置

已安装 Android Studio Stable 2026.1.4.8 ARM64、OpenJDK 17.0.20.1、Gradle 8.9 Wrapper。已建立 Android Native Kotlin、Jetpack Compose、Material 3、Compose Navigation、Flow、Gradle Kotlin DSL 与 Version Catalog 工程。Gradle `tasks` 配置检查成功。

Android SDK、adb、Build Tools、Emulator 与 AVD 尚未安装完成。官方 command-line tools 下载多次发生 connection reset；Android Studio 首次向导无法自动操作，因为 Mac 当前锁屏。

## 项目位置和启动

项目位于 `/Users/jitian/Documents/ChatGPT/Remember Me`。解锁 Mac 并由 Android Studio Setup Wizard 安装 SDK 后，打开此目录，选择 `RememberMe_API_35`，运行 `app`。命令行方式见根目录 README。

## 已实现页面

已实现 Splash、Welcome、Product Explanation、Consent、Introduce Yourself、Recording、Processing、Twin Birth、Voice Seed、Creator Home、Memories、Twin、Calibration、Digital Handover、Legacy Home 与 Debug Demo Menu。录音、波形、处理、Voice Preview 和 Twin 回答均按首期要求使用 Mock 状态。

## 工程决定

首期使用单 app module 的分层结构，避免过度模块化。Subject 与 Actor 分离。Original Evidence 与 AI Simulation 有显式文字标签。Recording、Cloud Twin 和 Voice Clone consent 独立。真实 STT、Twin、Voice、Repository 与 Hardware 通过接口替换，UI 不依赖供应商。

## 未完成和已知问题

尚未完成 APK clean build、单元测试执行、instrumentation smoke test、AVD 创建、安装启动与真机视觉检查。现有页面虽按可访问尺寸和 Compose 自适应布局实现，仍需 Emulator 上检查系统大字号、键盘和小屏溢出。Debug Menu 尚未通过 `BuildConfig.DEBUG` 对 release 隐藏。

## 下一阶段

先完成 SDK 与 Emulator 验收并修复编译或布局问题，再由产品负责人评审视觉。视觉通过前不要接真实 AI、Voice、Backend 或 Work 3200 SDK。

完成环境后应首先打开 `RememberMe_API_35`，从 Welcome 走完整 Onboarding；随后在 Creator Home 右上角 `•••` 打开 Demo Menu，切换到 Legacy Mode 评审第二种产品状态。

# Remember Me Android Build Report

报告日期：2026-09-20。第一阶段 Android Prototype 已完成构建与 Emulator 验收，可进入产品视觉评审。

## 安装和配置

已安装 Android Studio Stable 2026.1.4.8 ARM64、OpenJDK 17.0.20.1、Gradle 8.9 Wrapper、Android SDK 35、Build Tools、Platform Tools、Emulator 和 ARM64 system image。已创建并启动 `RememberMe_API_35`。

`./gradlew test assembleDebug` 成功；Debug APK 安装与冷启动成功。Compose instrumentation smoke test 已通过 adb 运行，结果为 `OK (1 test)`，覆盖 Welcome → Consent → Introduce → Recording → Processing → Twin Birth → Voice Seed → Home。

## 项目位置和启动

项目位于 `/Users/jitian/Documents/ChatGPT/Remember Me`。Android Studio 打开此目录，选择 `RememberMe_API_35`，运行 `app`。命令行方式见根目录 README。

## 已实现页面

已实现 Splash、Welcome、Product Explanation、Consent、Introduce Yourself、Recording、Processing、Twin Birth、Voice Seed、Creator Home、Memories、Twin、Calibration、Digital Handover、Legacy Home 与 Debug Demo Menu。录音、波形、处理、Voice Preview 和 Twin 回答均按首期要求使用 Mock 状态。

## 工程决定

首期使用单 app module 的分层结构，避免过度模块化。Subject 与 Actor 分离。Original Evidence 与 AI Simulation 有显式文字标签。Recording、Cloud Twin 和 Voice Clone consent 独立。真实 STT、Twin、Voice、Repository 与 Hardware 通过接口替换，UI 不依赖供应商。

## 未完成和已知问题

真实录音、STT、LLM、Voice Clone、Backend 和 Work 3200 按首期边界未接入。当前依赖下载需要本机网络代理，Gradle 已记录本机回环代理设置；换电脑时应按当地网络删除或调整。SDK 工具版本会输出 XML schema 兼容警告，但不影响构建。Debug Menu 入口只在 Debug build 显示。

## 下一阶段

由产品负责人先评审视觉、文案节奏和 Legacy 氛围。视觉通过前不要接真实 AI、Voice、Backend 或 Work 3200 SDK。

现在应打开正在运行的 `RememberMe_API_35`，从 Welcome 走完整 Onboarding；随后在 Creator Home 右上角 `•••` 打开 Demo Menu，切换到 Legacy Mode 评审第二种产品状态。

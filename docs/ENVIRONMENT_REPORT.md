# Remember Me Android 环境审计报告

审计日期：2026-09-19。设备为 Apple Silicon Mac，首期目标是维护一个主 Android Phone AVD。

| 项目 | 状态 | 版本或结果 | 是否满足 |
|---|---|---|---|
| macOS | 已安装 | 26.6.2 build 25G83 | 是 |
| CPU | 已识别 | arm64 Apple Silicon | 是 |
| 内存 | 已识别 | 16 GB | 是 |
| 系统盘可用空间 | 已识别 | 约 186 GiB | 是 |
| Homebrew | 已安装 | `/opt/homebrew/bin/brew` | 是 |
| Git | 已安装 | 2.53.0 | 是 |
| JDK | 已安装 | OpenJDK 17.0.20.1 | 是 |
| Android Studio | 已安装 | Stable 2026.1.4.8 ARM64 | 是 |
| Android SDK / adb / Emulator | 缺失 | 官方 command-line tools 下载因连接重置失败；Android Studio 首次配置因 Mac 锁屏无法继续 | 否 |
| Gradle Wrapper | 已生成 | Gradle 8.9；Gradle 配置检查成功 | 是 |
| AVD | 初检缺失 | 计划创建 `RememberMe_API_35` Pixel phone ARM64 | 创建并启动后满足 |

本次操作只安装项目必需的稳定工具链，没有安装多套 SDK 或多个 AVD。Gradle 对 Maven Central 的直接访问返回 403，因此工程配置将阿里云公共镜像置于官方仓库之前，官方仓库仍作为回退。

**当前唯一需要用户完成的动作：解锁 Mac。** 解锁后首次打开 Android Studio，接受 Android SDK 许可并让 Setup Wizard 安装 SDK Platform 35、Build Tools、Platform Tools、Emulator 和一个 ARM64 phone system image。随后即可创建 `RememberMe_API_35` 并完成构建与模拟器验收。

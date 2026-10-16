# 本人音色通话播放修复包 — 2026-10-16

本人要求安装[通话噪声修复](IOS_PERSONAL_VOICE_NOISE_2026_10_16.md)，并确认录音与通话都已结束。修复包为 **1.16.3 / 2026101613**，沿用 `me.remember.personal.ios`。

当前状态：已覆盖安装到 iPhone 15 Pro Max「黑幕」，安装回执成功，设备应用列表独立读回 **1.16.3 / 2026101613**。原9段录音、3段声音样本及其目录内全部22个文件的路径、大小、mtime、属主和权限核对一致，扩展属性无差异。没有卸载、重置容器或自动发起录音／通话。

## 冻结范围

为避开同工作区尚未发布的录音改动，以已安装 **1.16.2 / 2026101612** 的完整冻结源码为基线。128 项输入经摘要核对；只有以下四项与安装基线不同：

- `PersonalVoicePCMPlayback.swift`：非 MainActor 读取、固定采样时钟、重新缓存、尾帧与取消。
- `VolcengineVoiceTransport.swift`：仅播放函数及三个无内容数字诊断字段。
- `PersonalVoicePCMPlaybackTests.swift`：九项播放测试。
- `project.yml`：主 App 与录音活动扩展版本同步到 1.16.3 / 2026101613。

没有把工作区后续录音、设备采集或 UI 改动混入此包。当前工作区此前39项测试与此冻结安装包34项测试是两个基线，不能相加为不重复用例。

## 已完成验证

冻结包 **34 passed / 0 failed**：新播放9项、安装基线国内语音25项。Release真机目标构建通过。App与RecordingActivity扩展版本一致，签名、描述文件有效期和「黑幕」设备授权核对通过；身份／Keychain／App Group相关描述文件许可与1.16.2相同。六个既有嵌入框架齐全，Release不含DEBUG离线测试入口。

已生成签名归档并解包为安装副本；原构建与解包副本都通过 `codesign --verify --deep --strict`，冻结输入摘要保持一致。没有部署后端或改变现有音色。

## 安装与数据核对

准备的安装流程仅使用 `devicectl device install app`，没有卸载、重置、终止进程或自动发起录音／通话。安装前再次核对旧版本，避免覆盖构建期间由其他任务安装的新版本；本人确认无活动后再检查原录音目录文件信息20秒内稳定。安装后独立读取版本，并核对原文件路径、大小、mtime、属主和权限；系统扩展属性差异单列，不将其冒充音频变化。

本轮初次只执行到安装前应用版本查询，设备不可用（CoreDevice 4016）就停止，没有执行安装命令。本人随后确认已解锁并连接；重新核对原版本、文件20秒内稳定，以及安装前即时版本后完成覆盖安装。安装后独立读回新版，再完成上述22个文件的信息核对。未自动启动App或替本人发起通话；实际外放听感仍需本人用新版本验证。

## 本机证据

- `build/device-voice-noise-20261016-2026101613/`：冻结源码与manifest、播放专项补丁、Release日志、34项测试结果、签名版本证明和安装脚本。
- `build/releases/RememberMe-1.16.3-2026101613.app.zip` 及同名 `.manifest.json`：已验签的归档。
- ignored `build/private/voice-noise-install-20261016-1613/attempt1-device-unavailable.*`：安装前离线回执；没有写入手机。
- 同私密目录的 `install.json`、`installed-app.json`、`originals-before.json`、`originals-after.json`：成功安装与文件核对回执。公开数字摘要在 `build/device-voice-noise-20261016-2026101613/installation-proof.json`。

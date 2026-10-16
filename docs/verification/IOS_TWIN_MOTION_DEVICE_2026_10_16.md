# 孪生界面与音量动效真机交付

2026-10-16，Asia/Singapore。按本人“部署在真机上我看看”的直接要求，将宣传片风格孪生界面及真实音量驱动的环形动效覆盖安装到 iPhone 15 Pro Max「黑幕」（iOS 26.6.2）。

- 安装前：`me.remember.personal.ios`，1.15.4 / 2026101609。
- 安装后：相同 bundle ID，**1.16.0 / 2026101610**；设备应用列表已独立读回核对。
- 正常启动成功，未使用测试参数。进入「孪生」查看夜色界面，从右上角电话进入通话观察声音动效；关联原音回听使用金色。
- 安装前后 `Library/Application Support/Recordings` 中 7 个原音文件的相对路径及完整文件 metadata 一致。未卸载、重置容器或读取原音内容；此检查不等同于整个应用数据的内容校验。

## 构建与产物

主 App 与 RecordingActivity 扩展统一为 1.16.0 / 2026101610。使用现有 `project.hardware.yml` 保留 Soundcore 录音豆能力、VolcEngine RTC、LiveKit 与原后台模式。SDK 内容及嵌入规则沿用已安装版本。

首次 Release 构建期间原工作区有并行修改。安装采用随后复制的固定 iOS 源码快照，在 ignored `build/twin-motion-device-20261016/source/ios/` 独立生成硬件工程并重新构建；122 个构建输入前后摘要一致。快照包含当时共享工作区已有的其他 iOS 改动，没有重置或丢弃它们。

最终 Release 构建成功，主 App／扩展的版本、bundle ID、签名团队、描述文件有效期和目标设备授权均已核对；归档前及解包后 `codesign --verify --deep --strict` 通过。Release 可执行文件不包含 DEBUG 音频动效测试入口。

签名包：`build/releases/RememberMe-1.16.0-2026101610.app.zip`；同名 manifest 保存版本、可执行文件／归档摘要和框架清单。实际安装来自该归档的解包副本。

## 证据和范围

- Release 日志、冻结源码清单、签名和安装安全摘要：`build/twin-motion-device-20261016/`。
- 原始设备应用列表、安装／启动回执及录音 metadata：ignored `build/private/twin-motion-*-20261016.json`。
- 动效的 83 项单元与 3 项 UI 检查、最终计量复验及实际模拟器录屏见 [音量动态验证](IOS_TWIN_AUDIO_MOTION_2026_10_16.md)；视觉实现见 [宣传片适配](IOS_TWIN_FILM_STYLE_2026_10_16.md)。

本轮证明签名构建、覆盖安装、版本读回、已知录音文件保留和正常进程启动。没有代替本人发起通话、录音、许可确认或音色试听验收，也没有把启动回执称为真机视觉／通话验收。用户实际声音驱动效果由本人在手机上查看。

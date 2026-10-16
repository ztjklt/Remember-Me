# 实时通话默认手机扬声器

2026-10-16 已按用户要求与声纹姓名一起覆盖安装至「黑幕」，版本 1.13.2 / 2026101508。手机锁屏，尚未确认启动或真人外放体验；新结果见[统一部署记录](IOS_SPEAKER_DISPLAY_DEPLOYMENT_2026_10_16.md)。下文未安装状态为 10 月 15 日历史。

2026-10-15，Asia/Singapore。本人要求手机实时通话直接适配扬声器，不绑定蓝牙。

## 行为和实现

- 每次开始通话默认手机扬声器＋内置麦克风，无需蓝牙绑定或连接。沿用 LiveKit 音频引擎及回声消除、自动增益和降噪；麦克风启用后才调用 iOS `.speaker` 输出覆盖，避免在非录放类别下提前操作音频。
- 通话页显示实际输出及对应图标，提供“手机扬声器”和“听筒／已连接耳机”选项。取消以固定耳机图标和系统 AirPlay 入口暗示耳机必需的界面；连接前明确默认手机外放。
- 扬声器模式下，蓝牙设备断开不会结束通话。设备或类别变化清除外放覆盖时重新应用；自己的 `.override` 通知不重复触发切换。选择听筒也不依赖外部设备；仅用户正在使用的外部输出真正断开时，为避免意外外放而结束通话。
- 挂断或失败先停止本地媒体，再清除本次输出覆盖并恢复原 SDK 扬声器偏好。未就绪、已挂断或过期的启动操作不能切换输出。切换失败结束通话并给出提示。
- 修改位于 `TwinVoiceCall.swift`、`TwinVoiceCallView.swift` 及定向测试。没有 Backend／Worker／Contract／授权用途或供应商配置变更。此前[云端连接超时](IOS_VOICE_CONNECTION_DIAGNOSIS_2026_10_15.md)仍未证明彻底解决。

## 实际检查

- `TwinVoiceCallTests`：**23 passed**。新增覆盖外设已连接时仍选择手机外放、先启麦后切换、听筒／扬声器切换、静音保持输出、外设断开和类别变化、避免覆盖通知循环、挂断及晚到启动不改输出、输出失败清理；原授权、旧轮、插话、静音和重连检查保留。
- 两个 UI 场景：**2 passed**。实际类名为 `SimpleFlowUITests/testVoiceCallShowsRouteForegroundNoticeAndHangup` 和 `RMDesignSystemUITests/testUnidentifiedSpeakerDoesNotShowAMatchedNameAtLargeType`。覆盖普通／极大字号下外放路线、无需蓝牙说明、输出入口与挂断可达，导出截图已目视检查。
- 前两次命令误用文件名 `AndroidParityUITests` 选择 UI 类，该选择没有执行对应 UI；23 项逻辑测试及另选的大字号检查实际执行。纠正为 `SimpleFlowUITests` 后，两次 UI 检查暴露父容器覆盖按钮无障碍标识的问题，修正后最终两个 UI 均通过。不将未匹配的选择或失败轮次算作 UI 通过。
- Release iPhone 签名构建及 `codesign --verify --deep --strict` **通过**。保留待统一发布的 **1.13.2 / 2026101508**，包位于 `build/voice-speaker-device/Build/Products/Release-iphoneos/RememberMe.app`。
- 最终逻辑结果：`build/voice-speaker-final-20261015.xcresult`；最终 UI：`build/voice-speaker-ui-verified-20261015.xcresult`；截图：`build/voice-speaker-ui-verified-images-20261015/`；签名构建日志：`build/voice-speaker-device-final-20261015.log`；源码指纹及检查摘要：`build/voice-speaker-proof-20261015.json`。

定向命令使用 `xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe -destination 'platform=iOS Simulator,id=10BAAA0D-3912-4F01-9CD6-92897F1A1695'`，分别选择上述逻辑类与 UI 方法运行。没有为该改动重复全部模块回归。

## 交付状态

“黑幕”当前为 unavailable，未安装或启动新包，未卸载或清空数据。按此前“下次一起正式部署”的要求保留源码及候选包。模拟器路线为明确标注的隔离预览，没有实际收音或播放。外放音量、扬声器回声和真人通话仍需在新版实体手机确认，不能用假音频路线或签名构建替代。

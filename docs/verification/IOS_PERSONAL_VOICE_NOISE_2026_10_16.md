# 本人音色通话断续／电流声排查 — 2026-10-16

本人报告已可使用本人音色通话，但手机外放听到断续、电流声。本轮取回当前音色的服务器合成试听供对照，本人明确回复「原音干净，通话里有噪声」。因此本轮修复聚焦 iOS 通话 PCM 播放，不重做或替换已有音色。

## 证据与原因

- 实体「黑幕」独立读回仍为 **1.16.2 / 2026101612**。设备需要密码解锁，最新 `VoiceDiagnostics/latest.json` 受完整文件保护无法复制；没有启动、安装、挂断或控制真人通话。
- 当前 profile 已就绪且 review 为 accepted。只 GET 当前 profile／review／preview，合成前后 profile 相同；没有写审核、重新训练或修改音色。
- 当前试听原文件为 24 kHz、mono、16-bit PCM WAV，5.26 秒；RMS −26.66 dBFS、峰值 −6.48 dBFS、削波比例 0、DC 约 0.000025。没有明显工频功率或 10 ms 边界异常。数值不代替听感，本人完成的原音／通话对比才支持本轮缩小排查范围。
- 已安装冻结源码和当前 `playPersonalAudio` 使用相同节拍：首包 9600 B（200 ms），后续 480 B（10 ms）。这个包长符合本地 SDK 头 `ByteRTCMediaPlayer.h` 及[官方混音指南](https://docs.volcengine.com/docs/real_time_communication/Playmusicfilesremixes?lang=zh)；首包大小本身不是缺陷。
- 原实现每次将下一帧定时重置为 `max(deadline, now) + 10ms`。唤醒迟到永久累加，而 SDK 仍按采样率实时消费，逐渐耗尽 200 ms 初缓；同一 MainActor 循环还逐字节消费网络数据，增加与 UI 争用的机会。它可以造成播放欠载、断续和点击噪声。此次不能以此证明所有真机噪声都已消除。

## 修复

`PersonalVoicePCMPlayback.swift` 在非 MainActor 的异步循环读取字节，只在推完整 PCM 帧时切到 MainActor 调用 SDK。后续帧按固定采样时钟每 10 ms 推送，短暂迟到不会延长以后的每一帧；长网络停顿则保留原字节并重新缓存，不发送大段追赶数据。末尾完整保留样本，只为不足 10 ms 的尾帧补零，并等待 SDK 播完缓存。

保留 4 MiB 上限、逐段取消、旧播放 ID 隔离与恢复期间禁播。通话结束、插话、撤权和连接恢复仍走既有停止／清理流程；没有更改共享 Backend Contract、录音采集、Live Activity、音色、授权或供应商配置。新增数字推送次数、重新缓存次数和最大迟到统计，不记录音频／文字／身份。

## 验证

定向模拟器检查 **39 passed / 0 failed**：新增 `PersonalVoicePCMPlaybackTests` 9 项，既有 `VolcengineVoiceTests` 30 项。覆盖固定时钟下 8 秒播放的唤醒抖动／SDK 耗时、网络长停顿恢复、字节完整性、尾帧、短流、非法样本、大小上限、推送失败和等待网络时取消；既有通话用例覆盖恢复、撤权、静音、旧回包、结束和麦克风异步失败。

确定性时钟场景：每次唤醒晚 1 ms，旧公式计算得到最后一次推送在 8580 ms，已经超过整段 8000 ms 音频；新实现测试实测在假时钟的 7801 ms 完成最后推送，保留 SDK 播放余量。此结果是调度回归证据，不是真机听感验收。

初次 `CODE_SIGNING_ALLOWED=NO` 编译成功，但模拟器拒绝加载未签名 VolcEngineRTC，测试启动失败（exit 65），没有将其记为通过。改用模拟器 ad-hoc 签名后重跑成功：

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,id=10BAAA0D-3912-4F01-9CD6-92897F1A1695' \
  -derivedDataPath build/voice-noise-20261016/DerivedData \
  -resultBundlePath build/voice-noise-20261016/PCMTestsSigned.xcresult \
  -only-testing:RememberMeTests/PersonalVoicePCMPlaybackTests \
  -only-testing:RememberMeTests/VolcengineVoiceTests \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- CODE_SIGNING_REQUIRED=NO test
```

原排查轮未覆盖安装手机或部署后端。本人随后要求安装：以当前手机1.16.2冻结基线只叠加播放修复，完成34项冻结版本检查与签名构建，**1.16.3 / 2026101613 已覆盖安装到「黑幕」**，设备版本及原音文件信息核对通过；见[安装记录](IOS_VOICE_NOISE_DEVICE_2026_10_16.md)。没有部署后端，真人外放／耳机实际音质仍待新版通话验证。

## 本机证据

- 当前试听和脱敏数值：ignored `build/private/voice-noise-20261016/current-preview.wav` 与 `numeric-proof.json`；私有声音未加入源码。
- 初次启动失败日志／结果：`build/voice-noise-20261016-test.log`、`build/voice-noise-20261016/PCMTests.xcresult`。
- 最终成功日志／结果：`build/voice-noise-20261016-test-signed.log`、`build/voice-noise-20261016/PCMTestsSigned.xcresult`。

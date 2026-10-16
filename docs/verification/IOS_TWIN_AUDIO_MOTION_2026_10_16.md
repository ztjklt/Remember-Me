# iOS 孪生音量动态效果

2026-10-16，Asia/Singapore。按本人追加要求，为宣传片风格的孪生界面接入随真实声音起伏的环形动态效果。

## 行为

- 勿忘我外圈的 112 根细光条随实际音量伸缩，花朵与辉光轻微同步变化；使用快起、慢落的平滑包络。它是音量可视化，不声称频谱或生物声纹分析。
- 通话监听时使用未静音的麦克风音量，孪生回应时使用对应远端声音。默认声音、本人复刻音色均可驱动；待连接、思考、资料不可用等状态不生成声音波形。
- 回听当前有效回答中明确关联的本人原音时使用金色，合成音色试听仍使用蓝色。没有音频报告时不伪造振幅。
- 静音、暂停、停止、结束、断线恢复和旧会话回调均有状态清理；缺失的通话音量报告在 400 ms 后失效。音频恢复时重新开始采样。
- 光环最高 24 Hz，在可见、前台且存在实测音量／短暂回落时刷新；静默回落后休眠。系统减少动态效果或打开遮挡面板时停用动态变化，保留静态提示；减少透明度与增强对比度回退为清晰实色。

## 音量来源与范围

火山 RTC 复用现有 100 ms 音量回调，按当前引擎、房间及 Twin 身份过滤；本人音色由实际推送的 24 kHz PCM 计算 RMS。LiveKit 使用当前房间参与者的真实 audioLevel。回听原音与试听复用 AVAudioPlayer 测量，每 50 ms 读取平均功率，位置仍每 200 ms 更新；暂停／结束停止计时，使用 common run-loop 模式，滚动时也能正常回落。

所有变化均在现有 iOS 客户端。没有新增音频上传、录音、长期存储、权限或 Backend Contract；没有改变原音、合成音色或独立授权的语义。

## 实际验证

- Swift 完整编译、签名模拟器运行通过。首轮链接发现 SDK 未导出的 ByteRTCMediaPlayer 被可选值相等判断触发引用，改为原有的可选值解包写法后通过；未改 SDK 或工程依赖。
- 83 项单元测试通过：LocalRecordingTests、RMDesignSystemTests、TwinVoiceCallTests、VolcengineVoiceTests。新增检查覆盖真实生成音频的能量／静默、暂停与结束、无效数值、包络和几何边界、减少动态效果／后台、静音、重连、迟到事件及报告超时。
- 3 项 UI 检查通过：实际本机合成音频驱动及暂停／停止清理、通话详情／结束控制、多轮聊天与输入栏。
- 最后修正滚动期间的计时模式及面板遮挡门控后，3 项播放计量单元与音频动效 UI 复验全部通过。共 86 个不同用例，另有 4 项重复复验。
- 两个 xcodebuild 命令在用例全部完成后等待可选 simctl diagnose 采集；结束本轮的两个诊断子进程后，均以 0 退出、输出 TEST SUCCEEDED，结果文件可正常导出。

命令、日志和结果：`build/twin-audio-motion-20261016/verified.log`／`verified.xcresult` 与 `final.log`／`final.xcresult`。使用独立 iPhone 18 Pro / iOS 27.0 模拟器 `51C3B520-EE5D-4DF3-BFB0-8D47E1697116`，构建参数为 `CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=-`。

## 可查看预览

`build/twin-audio-motion-20261016/twin-audio-motion.mp4` 是实际模拟器录屏的约 8 秒片段，查看了不同时间的光条变化。`audio-motion-preview.png` 为其中一帧；原始录屏保留在 `native-audio-motion-full.mp4`。`screens/` 为最终 UI 检查附件。

预览通过 DEBUG 限定的 `--uitest-offline --uitest-twin-audio-motion` 入口播放本机生成的 330／440 Hz 音调与静音，使用正式的 AVAudioPlayer 计量链路；明确标记合成测试音频，不是真人的原音、声音样本或通话。普通和 Release 启动不会进入预览。

本轮未覆盖安装实体 iPhone，未进行真人通话或云端发布。真实 RTC 在设备上的动效仍需使用新版客户端观察。本轮开始时及过程中有其他未提交工作，保留它们；本轮局部差异另存到 ignored 构建目录。

## 后续真机交付

2026-10-16 已按本人要求以 1.16.0 / 2026101610 覆盖安装到「黑幕」，设备版本读回与正常启动成功，7 个原音文件 metadata 保留。详见[真机交付记录](IOS_TWIN_MOTION_DEVICE_2026_10_16.md)。

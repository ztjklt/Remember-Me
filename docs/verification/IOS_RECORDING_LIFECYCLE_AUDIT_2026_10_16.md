# iOS 录音、实时活动与本机转写生命周期复核

2026-10-16（Asia/Singapore）。本轮聚焦录音及 Live Activity 的稳定性，按已批准的 `docs/architecture/background-wearable-capture-2026-10-15.md` 保留后台录音、独立用途、原音和状态过期边界。未部署、未安装设备、未改变 Backend Contract。原有界面与设备工作保留。

## 已定位并修复

| 问题 | 修复与文件 |
| --- | --- |
| 本机转写等待系统授权时还没有占用 continuation，多次调用可覆盖首个请求；旧识别、取消或超时回调也可能结束下一段识别 | `apps/ios/RememberMe/OnDeviceSpeech.swift:82` 在授权前保留唯一 operation；授权等待也支持取消；识别、deadline、取消及晚到授权均检查 operation ID。终态只恢复一次 continuation 并清理识别任务和 deadline。同步返回终态的驱动也清理资源。仍强制 `requiresOnDeviceRecognition`，不回退云端。 |
| 复用 AVAudioRecorder delegate 时，旧 recorder 已排队回调可调用新录音的 finished closure；编码错误和完成回调可能重复结束 | `apps/ios/RememberMe/RecordingAudioEvents.swift:6` 绑定弱 recorder，回调只投递 ObjectIdentifier；回到主线程先核对身份，再一次性消费。AppModel 由主任务接入 recorder 的设置／清理，本子任务没有编辑 AppModel。 |
| 实时活动 update、end 各自开 Task；快速停止再开始会在旧活动尚未结束时申请新活动，旧更新也可能晚到 | `apps/ios/RememberMe/RecordingActivityController.swift:59` 串行执行 update／end／request，generation 淘汰过期排队动作；替换先等待旧活动结束。活动申请尚未执行时会采用最新的暂停／来源状态。 |
| 暂停活动原 staleDate 为 nil，进程不再更新后仍可能无限显示“录音已暂停” | 同文件 `76`：暂停和录制都在最后一次更新 90 秒后显示系统过期状态；来源变动立即更新，不必等 30 秒。Shared 展示继续由 `context.isStale` 显示“状态待确认”，没有伪造后台存活。 |
| Sidecar 原子写完后才设保护等级，后台 checkpoint 的临时文件会先继承默认保护等级 | `apps/ios/RememberMe/LocalRecordings.swift:108` 在 atomic 写入创建临时文件时就指定已有保护等级。普通完成稿仍为 complete；正在录音／设备导入仍沿用原先的 completeUntilFirstUserAuthentication，没有降低已完成文字的保护策略。 |

## 验证范围

新增 `apps/ios/RememberMeTests/RecordingLifecycleTests.swift` 最初 10 项 XCTest，覆盖：授权期间重复请求、授权等待取消及晚到回调、跨录音旧识别结果、拒绝后重试／同步终态、90 秒识别期限清理、暂停活动过期与来源切换、等待旧活动结束再替换、停止淘汰排队 request／update、旧 recorder 与重复终态、原子 checkpoint 内容替换。识别和 ActivityKit 使用隔离驱动；没有请求系统麦克风或调用云端。

本子任务实际执行并通过：

```bash
xcrun swiftc -swift-version 6 -typecheck apps/ios/RememberMe/OnDeviceSpeech.swift
xcrun swiftc -swift-version 6 -target arm64-apple-ios17.0-simulator \
  -sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk \
  -typecheck apps/ios/Shared/RecordingActivityAttributes.swift \
  apps/ios/RememberMe/RecordingActivityController.swift \
  apps/ios/RememberMe/RecordingAudioEvents.swift apps/ios/RememberMe/OnDeviceSpeech.swift
```

上述文件及新增测试的 Swift 语法解析通过，相关已跟踪文件 `git diff --check` 通过。遵照主任务分工，本子任务没有执行 Xcode build／test。

主任务随后对首轮冻结快照执行了 331 项 iOS 测试，发现本文件原保护等级断言失败：iOS Simulator 对 Data.write 的保护选项不提供 `.protectionKey` 属性，实际返回 nil。不能把 nil 当作真机保护正确。现将原子内容替换测试保留为无条件验证，另增加 `testSidecarDataProtectionClassesOnPhysicalDevice`；模拟器明确 XCTSkip，物理设备才断言两种保护等级。因此该文件当前定义 11 项。主任务最终冻结快照中，本文件 10 项通过、1 项明确跳过；整个单元套件 349 项执行、347 项通过、2 项跳过、零失败（20:09:46）。首轮失败记录保留，typecheck 没有代替 Xcode 测试。

## 多人录音追加复核

仅调整 `SpeakerRecordings.swift`、`SpeakerRecordingView.swift` 及其测试：

- 多人录音原无 recorder delegate／音频重置处理。现复用身份校验的 RecordingAudioEvents，接收中断、设备断开及 Media Services Reset，停止并归档当前原音；View 根据 workspace 的 starting／recording 状态同步 `model.isSpeakerRecording`，不再仅靠手动结束按钮清理。
- 权限返回后再次核对 App 为前台；后台／离开视图会作废待开始请求。系统权限弹窗的短暂 inactive 只停止播放，不误当真正后台。录音计时任务绑定 recording ID、使用 recorder 的实际时长；停止后取消，旧 recorder 回调不能结束替代录音。
- 准备文件后先原子保存 owner／用途回执，再开麦；回执失败不开始麦克风。进行中的音频使用 completeUnlessOpen，回执使用 completeUntilFirstUserAuthentication，完成后恢复 complete。最终时长优先读取已保存文件。结束时档案写失败保留文件及本机记录，提供本地重试保存；单个损坏 sidecar 不隐藏其余档案。
- 分段播放有界检查时间范围，播放截止绑定原 player 和 generation，旧片段任务不再停止替代播放器。

`SpeakerRecordingTests` 新增 5 项隔离测试，覆盖前台核验、系统重置后的真实文件时长及状态清理、旧 recorder 回调、初始／结束归档失败与原音保留重试、分段播放替代与非法范围。主任务最终冻结 Xcode 测试中，该类全部 10 项通过；上述 5 项包括在内。此前 Swift 解析与独立 typecheck 仅作前置检查。

主任务最终冻结源为 `build/realtime-priority-audit-20261016/source/ios`，输入摘要为同目录上两级的 `ios-inputs.json`；使用独立 iOS 27 模拟器 `61C07DCA-2BF9-4617-BD96-5A85236CA02D`。结果写入 `/tmp/remember-realtime-priority-final-20261016.xcresult`。该轮相关 UI 6 项全通过，包括实际系统 Live Activity 创建／结束；命令退出 0，xcresult 独立读回 Passed／353 passed／2 skipped／0 failed。完整命令、诊断收集、源码摘要及设备边界见 [第二轮总报告](REALTIME_PRIORITY_AUDIT_2026_10_16.md)。中间另一冻结快照因并行任务的设备文件清理旧实现失败，最终已用更新源码复跑；具体失败与源码边界也保留在总报告。

## 仍需主任务与设备验证

- 主任务已接入：录音 Timer 的排队 Tick 同时核对 isRecording 和当前 recording ID，停止后清理旧时基；Timer 加入 common run loop。录音时长优先以 recorder／实际文件时长为准，避免墙钟及中断漂移。辅助录音与上传让位也已纳入最终 App 编译和回归。
- 已向主任务提示：音频设置为 complete 后，锁屏后台继续读取原音可能失败。自动转写／上传需在受保护数据可用时继续，不应为消除超时而放宽原音保护。
- Media Services Reset、系统来电、耳机切换、长时间锁屏、快速停止再开始、进程被系统终止后的原音恢复，尚无本轮实体 iPhone 结果。ActivityKit 关闭或系统拒绝活动时，录音本身应继续；未实际验证灵动岛显示或系统调度延迟。
- 这些修复解决已确认的本机竞态；不能单凭它们宣称普通录音云端处理或实时 Twin 通话的全部超时已解决。

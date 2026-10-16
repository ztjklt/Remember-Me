# 第二轮稳定性审计：录音、通话和实时活动优先

日期：2026-10-16（Asia/Singapore）。承接 [首次超时排查](APP_TIMEOUT_AUDIT_2026_10_16.md)，本轮重点检查普通录音、多人录音、自然通话和录音 Live Activity 的启动、取消、中断、资源竞争与迟到回调。当前改动在工作区源码中；本轮没有提交、部署 Backend / AI Core 或安装客户端，没有修改 Backend Contract 或数据库迁移。工作区已有其他任务的改动，均保留。

## 持续优先级

已在仓库 `AGENTS.md` 的 Boundaries 中记录：每次涉及相关功能，优先保护正在进行的录音、实时语音和录音 Live Activity；可选刷新、识别、学习及设备同步须有界，并避免阻塞实时链路；按变化验证中断、取消、重连与清理，明确记录未验证的设备行为。

这是一项执行规则，不能承诺系统调度或外部供应商永不失败。

## 本轮确认并修复的问题

| 范围 | 原故障与处理 |
| --- | --- |
| 前台音频与设备上传 | 上传占用状态原本会挡住新录音；取消后的旧上传还可能清除新任务状态。现在录音、辅助录音、多人录音和自然通话可暂停可重试的上传，保留原音及原幂等键；上传 generation 防止迟到结果污染新任务，实时音频及前置请求结束后再恢复队列。交叉检查另发现进入录音页仍使用连接切换的宽限制，已改为录音限制；不使用音频会话的 utility 文件导入可与前台采集并行，导入期间仍禁止切换身份。 |
| 通话启动与结束 | 关闭界面、后台切换或取消任务时，旧权限／建连请求可能继续启动；旧断开及状态错误可能结束替代通话。现在每一步核对请求身份、取消状态与前台状态；结束操作绑定当前通话，先清理本机状态，再等待旧远端请求。可恢复 RTC 警告与致命错误分开处理，采集失败不伪装成正在聆听。 |
| 音频会话竞争 | 档案播放可把录音的音频会话改成播放；旧原音下载错误可能覆盖新录音界面。现在所有档案播放入口检查实时音频状态，下载回调核对自身身份。 |
| 普通与辅助录音 | delegate、Media Services Reset 和 Timer 旧回调可能作用于下一段录音。现在回调绑定 recorder／录音 ID，终态消费一次；Timer 在 common run loop 中读实际录音时间，保存后优先读实际文件时长。重置时结束并保留当前原音，不自动重新开麦。 |
| 多人录音 | 原无完整音频中断处理，最终 sidecar 保存失败会失去界面中的记录。现在先保存 owner／用途回执再开麦；系统重置、中断和设备断开结束当前采集并同步视图状态；保存失败保留原音和本机记录，支持重试。分段播放和计时绑定原任务身份。 |
| 录音 Live Activity | 独立的 update／end Task 可能乱序，旧活动尚未结束便申请新活动。现在串行更新、结束和申请，用 generation 作废旧操作；暂停活动也有 90 秒过期边界，进程停止更新后显示状态待确认。ActivityKit 不可用时不阻断录音。 |
| 本机转写 | 等待授权时连续请求可覆盖 continuation；旧结果、取消及超时可能结束下一次识别。现在在授权前占用唯一 operation，所有回调核对 ID，终态只完成一次并释放任务。仍仅使用设备端识别。 |
| 服务端事件循环和事务 | 游客／旧账号托付的同步数据库、STT 和 Twin 工作原可堵住异步事件循环，回答返回还可能留下发布锁。现在移入工作线程，并在返回／等待上传前释放事务。详见 [服务端复核](BACKEND_REALTIME_PRIORITY_AUDIT_2026_10_16.md)。 |
| 流式取消与首音期限 | SSE 断开原可取消自身清理，迟到模型结果仍会落库；ASR 子任务晚于 WebSocket 关闭才取消。现在先退役旧轮次并保护清理，先回收识别泵；stop／DONE 的成功边界也有回归。TTS 使用 5 秒连接、12 秒首音、8 秒包间和 90 秒总预算，超时释放连接。 |
| 后台学习与前台通话 | 后台模型提取原与通话共用唯一槽；声纹计算和上传原在全局发布锁内执行。现在同一模型保留默认 2 个前台交互槽，后台仍有自己的有界额度；声纹准备移到锁外，短事务重新核验后发布。保留限流和既有失败状态。 |

## 验证记录

iOS 使用独立模拟器 `RM Timeout Audit 20261016`（`61C07DCA-2BF9-4617-BD96-5A85236CA02D`，iOS 27）与冻结源码，避免其他任务同时编辑／测试影响结论：

- 冻结源：`build/realtime-priority-audit-20261016/source/ios`；127 项输入摘要：`build/realtime-priority-audit-20261016/ios-inputs.json`。
- 首次全量执行 331 项、1 项跳过，出现同一保护等级用例的 2 个断言失败：Simulator 不提供 `.protectionKey` 属性。保留无条件的原子内容替换检查；保护等级另立物理设备用例，在 Simulator 明确跳过，不能把 nil 当作通过。失败结果保留在 `/tmp/remember-realtime-priority-unit-20261016.xcresult`。
- 第二次冻结全量执行 349 项、2 项跳过，设备临时文件清理用例有 2 个断言失败。冻结输入未变动；另一任务在并行修改该模块，其后源码已把目录 URL 的相等检查改成规范路径比较，补充删除后局部重放检查。本任务未覆盖该改动，将更新后的源码连同最终录音入口小修重新冻结验证。失败结果为 `/tmp/remember-realtime-priority-final-unit-20261016.xcresult`；旧源与摘要保留为 `source-final-unit-349`、`ios-final-unit-349-inputs.json`。测试结束后为避免等待冗长诊断，只停止了该次失败运行自己创建的可选 simctl diagnose 子进程，测试失败日志和结果保留。
- 最终 iOS 单元套件：349 项执行，**347 passed、2 skipped、0 failed**；其中录音生命周期 10 项通过／1 项物理设备保护等级检查跳过，多人录音全部 10 项通过。另一跳过项需要短期 Soundcore QA 凭据。
- 同一签名产物的相关 UI：**6 passed、0 skipped、0 failed**，覆盖四个中文 Tab、默认声音入口、单击录音／权限拒绝不留音频、通话路线／挂断、系统 Live Activity 创建／结束及多人录音界面。
- 最终 Xcode 命令退出 0、`TEST SUCCEEDED`，xcresult 读回 **355 total／353 passed／2 skipped／0 failed／Passed**；结果包 `/tmp/remember-realtime-priority-final-20261016.xcresult`，摘要 `build/realtime-priority-audit-20261016/ios-final-summary.json`。全部用例结束后，可选 simctl diagnose 收集迟迟未结束；仅停止该运行自身的诊断收集子进程，未停止测试或更改用例结果，之后 Xcode 正常退出并成功读取结果包。独立模拟器在验证结束后关闭，未操作其他任务的模拟器。
- 测试结束后重算 127 项输入摘要：冻结源零变化，与当时 canonical iOS 编译输入零差异；结果为 `build/realtime-priority-audit-20261016/ios-source-verification.json`。这不覆盖之后其他任务继续编辑的版本。
- Backend 全量：**1021 passed、7 skipped、0 failed**，命令退出 0；最新 JUnit 1028 项、0 failures／errors。常规套件跳过 PostgreSQL 专用检查，另在真实 PostgreSQL 实跑 **28 passed，无跳过**。AI Core 全量 **324 passed**；最后流／TTS／国内通话 **43 passed**。详细命令、最后 stop／DONE 小修的定向补验及共享源码按导入时点加载的边界见服务端复核。

最终 iOS 使用 `xcodebuild test`，项目为上述冻结源中的 `RememberMe.xcodeproj`，scheme `RememberMe`，destination 为独立模拟器，`-parallel-testing-enabled NO`，模拟器 ad-hoc 签名 `CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=-`。选择整个 `RememberMeTests` 及上述 6 个实际 UI 方法；构建与完整测试共用 `build/realtime-priority-audit-20261016/DerivedData`，固定依赖 `build/ios-livekit-packages`。完整命令与日志为 `/tmp/remember-realtime-priority-final-20261016.log`。

本机转写、ActivityKit 排序、录音旧回调和多人录音的定向用例说明见 [iOS 录音生命周期复核](IOS_RECORDING_LIFECYCLE_AUDIT_2026_10_16.md)。自动化使用隔离音频、可控服务及测试账号，不等同真实计费通话。

## 上线与设备边界

前一轮已解除生产数据库的单次阻塞，并记录当时健康检查恢复。本轮 20:08:40 只读复核 `/health` 为 HTTP 200／2.440 秒，版本接口 200／1.425 秒，仍为 `ios-latest-f54e295dc7d4`（CloudBase 054）；脱敏结果为 `build/realtime-priority-audit-20261016/final-public-probe.json`。这是一个时点的连通检查。现场独立安装的 iOS 1.16.2 不包含本轮全部新增修复。因此不能把本轮源码测试当作现网已经修复的证据。

本轮没有实体 iPhone 上的持续通话、长时间锁屏、系统来电、耳机切换、原音恢复及灵动岛调度结果；Data Protection 的真实等级也待物理设备核验。Android 当前根项目仍是本地原型，本轮没有将它改为生产语音客户端；前轮 Android 验证结果见首次审计。

Xcode 另外记录 5 条 AVAudioSession 运行警告，涉及主线程同步设置／激活音频会话（LocalRecordingTests 与 TwinVoiceCallTests 触发）。本地播放测试确实经过生产路径；普通录音、辅助录音、多人录音及播放仍有 MainActor 同步 `setCategory`／`setActive`，固定 LiveKit 依赖内部也有同步调用，不能全部归为测试夹具警告。自动检查没有因此失败，也没有本轮实测的卡死时长或线上超时因果证据；TwinVoiceCall 测试警告的具体调用栈未归因。因此不能声称所有主线程音频阻塞风险已经消除。后续应先记录真实设备上的调用耗时和栈，再协调 SDK 的会话所有权与执行顺序；本轮未在收尾时简单把全局会话调用搬到后台而引入新的启动／取消竞态。这与已复现的数据库自锁证据分开记录，避免把警告直接当作本次线上超时原因。

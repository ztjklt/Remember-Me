# 持续采集与重点区间验证，2026-10-16

本人确认规则并明确要求「开始吧」：持续采集，按一次开始重点、再按一次结束重点；原音全部保留，普通记忆可归并，重点不得精简或因重复吞并。授权与独立 Contract 见[提案](../architecture/wearable-priority-capture-2026-10-16.md)。本轮完成源码及本地验证，未发布 Backend、未覆盖安装本人手机，未用真人原音测试。

## 已实现

- 收到设备真实录音状态后，先取设备列表，再自动订阅官方实时音频；约每 60 秒封存实际连续音频并进入现有上传／后台整理队列，不等整次录音结束。丢包保留前后实际片段，不填造静音；暂停／停止的缓存尾包保存，但不把界面重新显示为录音中。恢复和新录音不会被旧封存任务切断。
- SDK 标记按毫秒去重、按开／关配对；奇数末标保护到录音末尾，跨上传分段仍保留交集。App 提供「开始重点／结束重点」。同一音频游标的重复操作明确拒绝；缺失完整标记、丢包或 ASR 时间不能可靠映射时保护整段。
- 裸 OPUS 原包保留，系统解码器生成可播放 WAV。完整文件同步逐区间比较原包，补齐尚未接收内容；相同音频出现在不同时间不会误去重。显式删除清理手机原包归档、WAV 与传输副本；内容校验回执防重新导入，无法验证的子片重放等待完整来源。硬件原文件不删除。
- Backend 校验重点边界，按真实 ASR 时间定位到完整句子；程序化独立保存完整重点原话与来源。同时保留重点中的偏好、价值等结构化理解，继续支持七域模型，不能替代原话。独立重点及其理解不参与普通去重；普通完全相同且上下文一致的条目可合并全部证据。
- 声纹、账号／人物空间、用途撤回和来源删除继续生效。Twin 只使用当前有效的本人范围，未知、亲友、重叠发言仍待核对。成功整理后清理重复机器稿和可安全移除的诊断正文；canonical 原文仍用于来源校验，实际状态为 `evidence_required`，不声称已清除全部逐字稿。
- 发出绑定指令只显示待确认；`onDeviceBindConfirm` 才显示已绑定。按 SDK 说明提示放入充电盒、闪灯时按充电盒按钮。首次连接说明转写／声音识别用途、包含已有录音，以及关闭自动同步后逐条选择。

## 实际运行

| 检查 | 最终结果 |
| --- | --- |
| Backend 扩展回归 | **212 passed**，2 条现有依赖弃用警告，290.99 秒 |
| AI Core 全量 | **323 passed**；wheel 与打包／HTTP smoke 通过 |
| Contract `npm test` | **62 passed**，包含旧版本兼容 |
| iOS 相关单元测试 | **50 passed**：设备导入 7、本机录音 29、裸音频 3、SDK 回调 4、重点／持续封存 7 |
| iOS 设备页界面 | **1 passed**，54.014 秒；入口、真实未连接状态及未登录提示 |
| 含官方 SDK 的 Simulator 构建／签名 | 通过；Swift 6、iOS 17 部署目标、iOS 27 arm64 Simulator 实跑 |
| 测试快照与本任务源码 | 13 个 iOS 源码／测试文件 SHA256 一致；服务与 Contract 摘要另存 |
| `git diff --check` | 通过 |

Backend 最终命令：

```sh
cd services/backend
.venv/bin/pytest tests/test_wearable_priority.py tests/test_wearable_memory.py tests/test_voiceprint_person_model.py tests/test_person_model.py tests/test_worker.py tests/test_episodes_api.py tests/test_agent_workbench.py tests/test_portrait_current_sources.py tests/test_recording_deletion.py tests/test_integration_materials.py tests/test_profile_material_version.py tests/test_twin_voice.py tests/test_contract_shapes.py -o addopts='' -q
```

AI Core：`uv run --locked pytest -q`；`uv build --wheel && uv run --locked python scripts/check_wheel.py`。Contract：`cd packages/contracts && npm test`。

iOS 使用独立冻结源码生成 `project.hardware.yml` 工程，未覆盖当前工程或本人数据。`xcodebuild test` 选择 `WearablePriorityTests`、`DeviceRecordingTests`、`SoundcoreAudioTests`、`SoundcoreCallbackTests`、`LocalRecordingTests` 及 `SimpleFlowUITests/testRecordingHomePlacesBluetoothBesideMyRecordingsAndShowsRealDeviceStatus`；关闭测试并行和额外诊断，使用独立模拟器、adhoc 签名。最终 `/tmp/remember-wearable-priority-delivery-20261016.xcresult`：**51 passed、0 failed、0 skipped**。结束后关闭该模拟器。

源码摘要、iOS 结果 JSON 和日志保存在 ignored `build/wearable-priority-20261016/`。最终日志 `/tmp/remember-wearable-priority-backend-20261016.log` 与 `/tmp/remember-wearable-priority-delivery-20261016.log`。

中间失败如实保留：首轮共享模拟器测试宿主未启动，观察到同设备另一次安装和指向另一构建目录的库加载失败，换独立模拟器后测试恢复。新增删除重放测试发现目录 URL 的目录标志影响相等比较，导致临时副本未清理；改为标准化路径比较，补全删除后子片／完整重放测试，最终 51 项通过。

## 尚未验收

公开 D3200 V1.3.01 SDK 没有佩戴检测、从 idle 开录或重映射实体按键的接口；本人回复「还未实机确认」。当前自动的是**已开始录音后的接收与整理**；不能声称已实现佩戴即开录、物理单按必然切换重点或强制结束 App 后继续同步。真实按键、绑定、后台蓝牙、长时锁屏和多人识别仍待设备验收。

合成正弦探针在 iOS 27 模拟器确认：原生 OPUS 解码固定裁去前 40 个 16 kHz 帧（2.5 ms）；不同长度仍为固定值，并用本机参考解码逐样本核对方向。原编码包不变，偏移明确保存，时钟不按比例缩放；系统输出时长不符合已验证关系时明确失败。该结果不替代本人手机系统的音频验收。

包含亲友的完整重点可以保持待核对，可能暂时阻止同段部分本人材料进入 Twin，这是保守隔离。原音、完整重点和已核验的本人结构化理解仍保留；本轮没有扩大第三方来源范围。

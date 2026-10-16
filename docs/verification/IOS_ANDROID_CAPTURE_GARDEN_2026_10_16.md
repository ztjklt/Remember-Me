# iOS 采集与 Android 记忆花园重构

2026-10-16。依据本聊天的直接授权和[实施提案](../architecture/ios-android-capture-garden-parity-2026-10-16.md)。参考 Android `ce586ec` / 0.16.0；在现有 iOS 工作区增量实现。源码版本为 **1.17.0 / 2026101614**。本轮没有部署后端、安装实体手机、覆盖原音或提交其他聊天的未提交改动。

## 已实现

- 新手机录音结束后返回首页，串行自动上传并读取机器稿／校对稿；持久重试意图、幂等键和草稿。旧录音缺少自动处理标记时不因升级上传。录音／实时通话开始前暂停可选上传。
- 首页编辑核对文字和独立补充说明，一次保存后后台提取记忆，再累计整理人物观察。上传失败、重启、晚到响应及账号／空间切换保留原音并隔离结果；人物观察仍待本人核对。
- 机器原稿、本机原始识别、自动校对稿和本人编辑分别保留；可恢复原稿／校对稿、查看每项修改原因。姓名、数字、否定、条件等疑点不自动确认。校对失败回退机器稿，不重新跑 ASR。
- MODEL 成功与累计分析排队同事务；合并待办、为运行中的任务保留后继；撤权／来源变化阻止过期结果发布。自动任务为实时语音让路，并有总预算、批次限制、重试、云实例租约回收和迟到结果隔离。
- 花园采用原生花田／列表／时间线、六景选择、按录音归组、每组五片花瓣及完整阅读器。提供八个内容侧面、四个人物视图、已确认理解／反例、精确与相关内容查找、继续提问。
- 花园详情保留全部依据、单一原音播放器、来源切换、进度与迷你播放器；支持手动创建、编辑、调整来源、确认、撤回、拆分、历史与恢复旧版。来源逐条校验，来源撤销、身份变化或音频切换阻断旧内容和迟到播放。

沿用 iOS 已获批的重点区间、本人／游客权限、原音保留和实时活动；未移植 Android 专有前台服务或替换现有实时语音。Android 档案顶层的独立亲友补记／专属信模块不属于本次花园迁移。原生纵向阅读及六个明确场景替代 Android 的部分横向分页／AUTO 外观设置；已有 aliases／same_event 分组字段在编辑时保留，本轮不额外暴露开关。

## Contract 与部署边界

独立 `capture-review-v1.schema.json` 记录兼容增量。核对 GET 返回 `machine_transcript`、`automatic_correction`；PATCH 沿用 `transcript`、`supplement`，按当前能力和有效 CLOUD_TWIN 授权可选增加 `cloud_analysis_consent_id`。Episode 列表增加 `waiting_for_review` 和 `cumulative_analysis`，不会新增 Episode 状态枚举。

真实后端等待核对时仍为 `transcribing`；客户端既支持显式标志，也为旧后端有界查询核对接口。旧服务省略新字段时仍可保存文字和补充，不发送不支持的累计分析字段。WORK_3200 保留声纹／重点的精确字位与已授权持续采集路径。

CloudBase 现有定时器会序列调用 processing-tick／profile-tick；本地测试已验证真实 MODEL 排队后私有 profile-tick 完成任务。线上每次定时推进有限阶段，不保证立即完成。新服务代码尚未发布，因此当前线上账号尚不能使用全部新能力。

## 最终检查

| 范围 | 实际结果 |
| --- | --- |
| iOS 逻辑 | 242 通过；1 项实体设备 Data Protection 属性检查在模拟器跳过 |
| iOS 界面 | 5 通过：两条采集、三条花园流程，包含最大字号和景色切换 |
| Backend | 最终合并定向回归 337 通过，0 失败；2 项现有 TestClient 弃用警告 |
| AI Core | 67 通过，0 失败；2 项现有 TestClient 弃用警告 |
| Contract | 72 通过，0 失败／跳过；包含 10 项新增采集契约检查 |

最终 iOS `final.xcresult` 汇总为 247 通过、0 失败、1 跳过。随后依据截图补上可见的核对／补充输入标签并缩短可选说明输入框；这次复验暴露连续输入的光标跳动，见保留的 `capture-labels.xcresult`。采集输入改用保留选择区与输入法组合文字的原生 UITextView，仅在文字确实变化且未组合输入时同步，补上原生收起键盘入口。原有连续英文输入测试没有改成单字符或换键盘来规避问题；最终 `capture-input-final.xcresult` 的 11 项采集逻辑、2 项普通／极大字号界面测试全部通过。输入禁用状态另以最终模拟器构建验证。

本地证据位于 `build/ios-android-refactor-20261016/`：`final.log`、`final.xcresult`、`native-summary.json`、`capture-input-final.log`、`capture-input-final.xcresult`、`backend-final.log`、`ai-final.log`、截图附件。早期编译的 MainActor 局部函数问题、测试桩后台闭包的 actor 检查崩溃及大字号景色选择失败均已保留在早期日志，并在最终运行前修正；不将早期失败计为通过。失败后的可选 simctl 诊断收集曾长时间挂起，仅终止该诊断子进程以完成失败报告；后续采集复验使用 Xcode 的 `-collect-test-diagnostics never`，仍正常运行测试与保存附件。

后端命令（在 `services/backend`，沿用现有虚拟环境，无额外环境变量）：

```sh
.venv/bin/python -m pytest tests/test_episodes_api.py tests/test_worker.py \
  tests/test_profile_material_version.py tests/test_profile_relations.py \
  tests/test_profile_updates.py tests/test_narrative.py tests/test_wearable_priority.py \
  tests/test_wearable_memory.py tests/test_voiceprint_person_model.py \
  tests/test_guest_access.py tests/test_guest_entrustments.py \
  tests/test_realtime_dynamic_priority.py tests/test_transcript_correction.py \
  tests/test_automatic_capture_analysis.py tests/test_profile_batches.py \
  tests/test_cloudbase_deployment.py -o addopts='' -q
```

AI 命令（在 `services/ai-core`）：

```sh
.venv/bin/python -m pytest tests/test_transcript_correction.py tests/test_api.py \
  tests/test_runtime.py tests/test_nuwa_profile.py tests/test_wearable_capture.py -q
```

Contract：`cd packages/contracts && npm test`。

iOS 使用 `xcodegen generate --spec project.yml` 生成项目，再执行 `xcodebuild test`；模拟器为 `10BAAA0D-3912-4F01-9CD6-92897F1A1695`，保留 ad-hoc 签名：`CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM=`。定向选择 `AutomaticCaptureTests`、`MemoryGardenTests`、`PersonReviewTests`、`LocalRecordingTests`、`RecordingLifecycleTests`、`GuestAccessTests`、`DeviceRecordingTests`、`WearablePriorityTests`、`TwinVoiceCallTests`、`ECSConnectionTests` 和两套新 UI 测试；完整命令所用参数见本目录相应构建日志。

后端测试使用临时 SQLite、内存存储和替代模型；未设置 `REMEMBER_TEST_POSTGRES_URL`。模拟器界面、播放与供应商返回均为隔离虚构数据或测试替身，不能代替生产数据库、真实供应商、长时蓝牙／录音、实体 iPhone 后台与真人原音体验。

## 预览

- [原生记忆花园](../feature-assets/ios-android-refactor-20261016/记忆花园.png)
- [转写草稿与一次保存](../feature-assets/ios-android-refactor-20261016/转写草稿.png)
- [人物侧面的大字号阅读](../feature-assets/ios-android-refactor-20261016/人物侧面大字号.png)

均使用虚构示例资料，已人工查看截图。

# Agent / 记忆核心交接

本分支从 `develop@4dc3d5a` 整理此前实验分支的核心能力。范围是 `data/agent`、对应测试，以及 `RecordingWorkflow` 的来源适配；UI、导航、主题、供应商设置页、提醒通知、APK 版本和共享 Backend 不在此交付中。旧 `feature/ai-agent-core` 与已安装的独立模式 APK 保留。

## 处理与数据

一个 `AgentMemoryEngine` 管理一个 subject 的日志并用 Mutex 顺序执行。核对文字先持久保存，再依次提取八维观察、合并原子理解、生成情境化心理候选；各阶段检查点可以重启后继续，最后才发布新 revision。原文、观察、理解和问答历史分别保存，模型回答不会反写为本人证据。

八维观察沿用实验版定义：事件、情绪、心理、叙事滤镜、本人自述状态、本人自述环境、身份 IP、表达。缺少依据时不补齐；文本不能代替音频状态或背景音测量。引用是连续原文，位置按 Unicode 码点计算。四个数据投影通过 `engine.portrait().views()` 返回事件、心情、决策价值和表达样本，不包含绘图组件。

理解使用 ADD / SUPPORT / CORRECT / CHANGE / CONFLICT。同义属性沿用 ID；姓名纠错只替代有关事实；短暂情绪和重复转写不会自动升级为稳定人格。问答召回原文及其校正依赖，人数问题不会只取固定 top-k；材料超过容量时明确失败，不截断或压缩。

`ask(question, consent)` 返回保存的锁定回答与 calibration ID。同问题、同 revision、同材料版本会复用锁定记录。`correct(id, human, expectedRevision, consent)` 同时检查锁定 revision 和材料版本。`history()` 恢复已保存问答；撤除会级联失效依赖，删除还会清除日志中的原文、机器转写和相关派生内容，保留标识与失效状态。`deleteEpisode` 只处理核心日志，原音文件和 sidecar 由录音模块负责删除。

`AndroidAgentJournalStore` 使用按 subject 隔离的 `noBackupFilesDir/agent-memory`。写入同步临时文件并原子替换已发布日志；不兼容版本或损坏内容明确失败，禁止自动重置。现有录音 sidecar 和 `agent_state.json` 不迁移；旧实验 APK 的 SQLite 日志也不自动导入。日志不包含密钥。

## Android 接入口

提供 `StructuredAgentModel` 和一个 subject 的引擎后，把 `ReviewedAgentProcessor(engine)` 注入当前 `MobileViewModel` 的 `processor` 参数。当前录音页仍走：本机转写 → 用户核对 → 明确同意 → `RecordingWorkflow.organize`。本 PR 不修改 `MainActivity` 的默认装配，所以默认 APK 仍显示整理服务未连接。

```kotlin
val engine = AgentMemoryEngine(subjectId, AndroidAgentJournalStore(context, subjectId), modelAdapter)
val processor = ReviewedAgentProcessor(engine)
val model = MobileViewModel(audioCapture, localAsr, processor)
```

`ReviewedMemoryProcessor` 增加有默认实现的录音来源重载，原有 `organize(text)` 适配器继续可用。新适配器要求核对时间、来源和同意，保留机器转写，只发送核对文字和相关已授权材料。修改核对文字产生新的来源版本，旧来源退出召回，依赖旧来源的回答失效。整理结果映射为既有 `ExtractedMemory`，摘要标记为 `AI_INFERENCE`，原文引用单独保留，因此现有档案页面可以读取，无需改 Compose。

模型调用由外层提供，核心接口没有 URL、Key、供应商 SDK 或工具执行。团队默认架构仍经共享 Backend；已有 BYOK 实验的凭证装配需要单独处理，不在此 PR 预置或启用。不会私自添加一个用来执行这些私有 worker 的服务器端点。

## 与其他 PR 的关系

- [#86](https://github.com/ztjklt/Remember-Me/pull/86) 提供共享 Backend / AI Core 的增量理解、facets、校准与采集规划。本 PR 不复制它的 Python 实现，不更改 iOS / Backend，也不把本地 JSON 当成公开 API。
- [#85](https://github.com/ztjklt/Remember-Me/pull/85) 是 UI 候选。本 PR 保留当前页面，只在录音数据流程增加可兼容的适配入口。
- `packages/contracts` 没有改动；本地形状仍标记 `agent-loop-v0.2-experimental`，不是 v0.4 共享 Contract。不要混用两者的校准请求和返回值。

## 验证与回滚

逐个逻辑提交执行 JVM 单元测试和 lint。最终还执行 debug/release 单元测试、debug APK / instrumentation APK 构建，并验证现有 `RecordingWorkflow` 的转写、核对、同意、错误重试和原有文本适配器兼容性。具体最终结果在 PR 的 Quick check 中记录。

Backend 全量 244 项、AI Core 全量 133 项通过。忽略目录中的本地 `.env` 属于旧实验环境；测试使用临时环境覆盖，不改动这些配置。Backend 测试数据库放在临时 RAM 目录以避开本机磁盘 journal 等待，未改变被测代码。

真机、设备旋转、通知及真实麦克风路径未执行。本 PR 不是新的可直接启用模型的 APK 发布；UI owner 还需装配获准的模型适配器、连接画像/问答展示并做所选真机演示。

回滚删除新增核心及适配，恢复 `RecordingWorkflow` 的原文本调用即可；默认页面行为不变。新日志留在私有目录，不覆盖现有 sidecar，也不要求数据库迁移。

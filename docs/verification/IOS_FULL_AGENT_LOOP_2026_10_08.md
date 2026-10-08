# iOS 完整软件闭环 — 2026-10-08

用户明确要求完成 `Capture → Extract → Model → Simulate → Compare → Correct → Capture`，并排除真机工作。本次以完整的可恢复软件循环为交付单位；不把一次抽取或一次 Twin 回答当作闭环完成。

## 行为

1. 自由或引导录音先保存；失败重试在等待本人核对时停止轮询，允许从服务端恢复同一 Episode，即使本地草稿已不在；其他待处理录音不会被覆盖。真实 STT 后本人核对文字，之后才提取和更新画像。后台按阶段持久化与租约提交；结构化反思失败可重试同一 Episode。
2. 同一主模型完成提取和画像反思。反思 worker 只从新原话生成记忆侧面，并在服务端传入的当前 Subject 画像中选择目标。`ADD / SUPPORT / CONFLICT / CHANGE` 是内部提议，不增加公开状态枚举。不同语境不能被合并；未解释的冲突保留；本人明确变化可退休旧理解及其同语境反例。
3. 画像重建按历史有效 Memory 重放，保留稳定 ID、支持/反例和有效时间。支持积累只按独立 Episode 提升内部启发式置信度，同一录音的多个片段不重复加分。删除或纠正使过期的合并快照失效；纠正不继承旧情绪或环境标签。
4. 七领域画像、八类记忆视图、四个图谱入口读取当前资料。滤镜记忆按用户定义表示回忆的主观视角、情感色彩和前后变化。情绪、心理变化、环境和状态标签必须附可定位原话；缺失时保持空。状态另外支持本机 PCM 响度、低响度片段比例和削波观测，最多分析前 30 秒，失败独立降级。这些信号不是精神状态诊断或声源分类。
5. 四个图谱分别呈现事件时间线、情绪/叙述视角、决策与价值证据、表达记录；表达记录包含当前有效原文片段的句长和连接词计数。关系视图使用实际 Memory 与 Trait 的共同证据连线，粗细表示证据条数。它是证据关联投影，不把共现冒充人际关系或因果事实。
6. Twin 使用当前可检索原文、画像与事实；当前问题排除被替代的历史偏好，明确历史问题仍能检索历史。第三方原话和其 AI 转述不能进入本人画像或 Twin 证据。模型回答期间若源模型版本改变，旧回答拒绝提交。
7. Twin 在本人回答前锁定。本人回答作为独立 Episode 先更新画像；五维比较结果是诊断，不直接写成 Memory 或 Trait。比较完成后把真人和锁定源的快照纳入失效检查；本人材料在比较期间改变则拒绝提交。失败保留原运行，并发和重放保留第一个已提交结果。
8. Planner 在画像提交、纠正/删除、校准完成后重算。优先处理冲突，其次校准偏差，再补领域缺口和弱证据/模式例外；每轮最多三项，复用仍有效的问题 ID，去重同一冲突，保留回答历史。回答所依赖的唯一资料被删除后，领域缺口可以重新出现。iOS 校准完成会读取下一轮问题；问题服务故障不会回滚已完成比较。

## 实际验证

| 检查 | 结果 | 边界 |
| --- | --- | --- |
| AI Core pytest | 146 passed | 包含反思目标/语境/来源、虚构引用拒绝、服务故障及第三方归属 |
| Backend pytest | 257 passed | 真实数据库迁移；多轮支持/冲突/变化、重建、恢复、删除级联、校准到下轮采集、源数据并发纠正 |
| AI Core wheel | build + smoke passed | 打包后的 fixture、提取与 HTTP 边界 |
| iOS 单元测试 | 11 passed | 实际隔离 URLSession，证据关联、标签故障清除、完成比较后规划故障、恢复和授权 |
| iOS UI 测试 | 3 passed | 五入口、录音/配对/档案导航、四个独立图谱入口；无真人麦克风输入 |
| iOS 最终模拟器构建 | BUILD SUCCEEDED | Xcode 27.0；最后补入的表达统计也已编译 |
| 真实服务循环 | 18 / 18 passed | Mac 合成中文音频 → 本机 Whisper → 核对 fixture 文字 → DeepSeek → 本机 BGE 检索 → Twin → 五维校准 → 下一轮采集 → 新 Twin |

真实服务使用四轮明确标注的**合成测试人物和录音**，不是用户自己的资料、真实本人回答或真机验收。STT 使用 `whisper-ggml-base-60ed5bc3dd14`，检索使用固定 revision 的 `BAAI/bge-small-zh-v1.5`，模型标识按实际 API 响应记录。详细结果见 [合成验收报告](fixtures/FULL_AGENT_LOOP_SYNTHETIC_2026_10_08.json)。无手机、麦克风采集或个人声音克隆。

可复现命令（仓库根目录；先在服务端配置私有 DeepSeek key，本次未复制或提交 key）：

```sh
uv run --project services/ai-core pytest services/ai-core/tests -q
uv sync --project services/backend --extra retrieval --python 3.13
services/backend/.venv/bin/python -m pytest services/backend/tests -q
services/backend/.venv/bin/python scripts/verify_full_agent_loop.py verify \
  --env-file /absolute/path/to/private-ai.env \
  --output build/full-agent-loop-acceptance
```

实时验证脚本仅监听回环端口，读取指定的私有 AI 配置，使用临时测试数据库，退出时停止测试 AI 服务。需要本机 `say` 的 Tingting、ffmpeg、whisper-cli 和多语种 Whisper 模型，以及 retrieval extra。它会调用配置的真实供应商，输出只包含合成材料。原生测试使用 iPhone 17 Pro Max / iOS 26.5 模拟器；日志与 xcresult 在忽略的 `build/ios-full-core-*`。

验收暴露并修复了本机 HTTP 请求意外走环境代理、M4A 从不可寻址输入解码返回空信号的问题。最后一次报告以上述修复后的运行结果为准。模型侧面标签可缺失，状态也可来自真实信号观测；验收不要求模型在缺少明示状态时编造心理标签。

## 接口与兼容性

公开 endpoints、JSON Schema、MemoryType、PersonTrait 状态、数据库列与迁移均未改变。使用现有开放的 `subject_context`、Memory `metadata` 和已有 `graph_facts` 字段。新约定保持可选：旧客户端忽略，新 iOS 在缺失或失败时保留核心画像；无 subject snapshot 的旧调用保持提取行为；旧供应商可无反思能力。

这些字段的内部约定见 [实现约定提案](../proposals/FULL_AGENT_LOOP_METADATA_2026_10_08.md)，本次没有把它冻结为新的跨模块 Contract。若后续需要在共享 Contract 中注册新的必需字段、枚举或能力协议，仍需 Product / Integration Owner 审核。

Android 未改动，客户端没有供应商 key。未合并实验分支的另一套引擎或其不同迁移链。

## 质量边界

本次完成并验证了工程循环；一次合成材料验收不证明长期 Twin 拟真度。规划评分与置信度是内部启发式，不是经标定的信息增益、心理量表或人格完成百分比。长期材料召回、跨场景理解和真实用户表达仍需持续评测。完整 Voice Clone 训练/声源识别、硬件、第三方训练、Handover 和 Legacy 不属于此次无真机的 AI 闭环范围，供应商能力继续保留适配与降级。

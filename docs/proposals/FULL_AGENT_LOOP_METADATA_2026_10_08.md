# 完整循环的可选内部实现约定

状态：feature 分支实现约定，非新冻结 Contract。用户已明确要求完整软件循环；本次不增加 endpoints、必需字段或公开枚举，不要求 Android 采用这一约定。

现有 `aiCoreInput.subject_context` 是开放对象。Backend 构造 `subject_id`、当前有效 `current_traits`（ID、领域、结论、语境、状态、Memory IDs、Evidence IDs）及可选 `calibration_question`。客户端不提供或修改画像基线。AI Core 按当前 Subject 校验并在反思 worker 中使用；旧调用省略它时仍可提取。

现有 `memoryItem.metadata` 是开放对象。可选字段：

| 字段 | 内容 | 失效与降级 |
| --- | --- | --- |
| `domain` | 已有七领域之一 | 缺失时沿用原有类型映射 |
| `reflection` | 版本、原 Memory 结论、ADD/SUPPORT/CONFLICT/CHANGE、语境、服务端目标快照 | 新提议必须有新本人证据；重放时目标内容/证据/语境不匹配则不再合并；不能凭它覆盖其他 Subject |
| `facets` | 类别、标签、精确 quote、证据 IDs、AI 来源与模型标识 | 必须引用对应 Memory 的有效本人原话；纠正清除；iOS 再做当前证据关联校验 |
| `audio_observation` | available/unavailable、观测器版本、分析秒数、rms_dbfs、silence_fraction、clipped_fraction 或失败原因 | 本地文件信号观测，不诊断心理状态；不能由上传元数据冒充，服务端重算 |

类别 `filter` 按用户确认定义为主观回忆视角。这里的八类是呈现侧面，不把现有六种 MemoryType 改成八种。人际事实继续使用已有 GraphFact；证据关系图只投影现有 Memory/Trait 关联。

`captureQuestion.reason` 已是非空字符串。Planner 使用 contradiction、calibration_gap、missing_domain、weak_evidence、deepen_pattern；状态仍是 pending/answered/skipped。iOS 对未知 reason 提供普通引导文案，旧客户端不需要改变。

校准比较 notes、summary、suggested_question 不成为本人事实。本人核对的 Episode 提供画像修正来源；比较只决定下一轮核对的优先级。比较在原运行中保留锁定回答，不因新增材料重写它。

公开 Contract 没有升级，内部字段也未作为新必需跨模块协议冻结。将上述约定纳入共享 Contract 或新增能力接口前，按照 AGENTS.md 的“Do not change a cross-module contract without an Issue or proposal and Product and Integration Owner approval”取得所需审核。

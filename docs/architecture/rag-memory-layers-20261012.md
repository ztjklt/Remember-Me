# RAG 引用合同与三层记忆的对应关系

2026-10-12。本文描述独立适配模块及集成要求，不代表队友的 RAG 服务已经连通。

产品依据是 [PRD v3 摘要](../PRD/PRD_V3_SUMMARY.md) 与原始 PRD；本轮范围承接 [来源预算与 RAG 接入边界](profile-batching-and-rag-boundary.md)。实现位于 `services/backend/app/rag_contract.py`。当前没有队友 endpoint、鉴权、索引同步或删除传播协议，没有 HTTP 实现、外部请求、整库上传或新 provider key。

## 三层记忆并不是三个重复事实库

| PRD 层 | 本地现有实体与职责 | 已有边界和未完成部分 |
|---|---|---|
| Layer 1：Life Episodes，生活片段 | `Episode` 保存录音对象、原始/展示转写、核对状态、时间和采集上下文；`Evidence` 定位来源、说话归属和片段；`MemoryItem` 是带引用的提取项。`effective_materials` 解析当前可用项，并补回未被提取覆盖的有效原文。 | 录音、一次讲述、一个生活事件不是同一计数单位。被删除、替代或未核对的内容不能靠检索再出现。纠正与补充形成新记录和历史，不能把旧原文改写成当时已经说过新话。 |
| Layer 2：Temporal Memory Graph，带时间和来源的事实/故事关系 | `MemoryItem` 的类型、有效时间与 metadata；`GraphFact` 的事实、证据、有效区间；`MemoryRevision` 的 supplement/correction/change 及目标记忆；`NarrativeRecord` 的 story/person/observation 与 evidence_snapshot；`NarrativeHistory` 保留整理历史。 | 这些是关系数据库里的记录和关联。当前没有运行一个通用图数据库，也未实现全量实体解析、事件自动去重或完整时间图推理。`NarrativeRecord` 是经本人核对的来源组织，不能取代原文。 |
| Layer 3：Person Model，当前人物理解 | `PersonTrait`、`ModelRevision` 是已有派生人物模型；`ProfileCandidate` 保存候选/确认/冲突/过期状态、情境、支持与反例、模型和 prompt 版本、来源指纹；`ProfileUpdate` 记录 ADD/SUPPORT/变化/冲突等关系及本人决策。`visible_understandings`/`persona_understandings` 只放行当前可用的理解。 | 观察不自动等于稳定人格；确认不取消来源限制。旧 `PersonTrait` 与新的确认候选并存，不应宣称所有历史数据已经统一为完备的 Person Model。关系建议、模型审阅与本人确认是不同步骤。 |

PRD 的七个人物领域是 Identity、Episodic Memory、Relationships、Preferences、Values & Beliefs、Decision Patterns、Expression。它们没有被界面的“八个侧面”替换。

`narrative.py` 的八个侧面是来源组织的标签：经历与转折、人物与关系、身份与角色、偏好/习惯/做事方法、价值/信念/选择理由、感受与当时状态、愿望/计划/牵挂、原话/表达/寄语。四个视图是这些侧面的投影：

| 视图 | 侧面 |
|---|---|
| 人生足迹 | 经历与转折、身份与角色、感受与当时状态 |
| 重要的人 | 人物与关系 |
| 在意与选择 | 偏好/习惯/做事方法、价值/信念/选择理由、愿望/计划/牵挂 |
| 声音与表达 | 原话/表达/寄语 |

同一来源可以出现在多个视图；这种重复展示不构成额外证据或独立事件。八侧面、四视图不是两套新模型，也不是图数据库完成度的证明。

Twin 根据上述当前授权材料生成回答。`TwinAnswer`、`PersonaAnswerContext`、检索审计与语音资产是派生结果和调用依据，不是第四层事实库。Twin 自己的回答不能回灌成“本人说过”的新证据。校准应先锁定旧回答，再收集并核对新的本人 Episode，经比较与本人决策后更新理解，保留变化前后版本。

亲友补记的 `CompanionContribution`/`CompanionAudio` 与署名、分类、接受和双方 model-use 授权保持独立。即使允许进入一次问答，也必须保留“他人的观察/观点”，不能自动变成本人原话、Person Model 定论或声音素材。语音是单独授权的表达层，不增加事实权威。

## 可执行的检索合同

新模块把检索分成三步：服务端制作当前允许检索的引用集合；provider 排序并只返回引用；本地重新取文和补齐上下文。外部 provider 没有最终权限裁决权。

```python
AuthorizedSource(subject_id: str, source: Mapping[str, str | int | None])
ContextGroup(kind: Literal["story", "correction", "understanding"],
             evidence_ids: tuple[str, ...])
AuthorizedSnapshot(subject_id: str, source_basis: str,
                   sources: tuple[AuthorizedSource, ...],
                   groups: tuple[ContextGroup, ...] = ())

class RagProvider(Protocol):
    def retrieve(self, request: RagRequest) -> RagResult: ...

build_rag_provider(session, encoder, *, episode_ids: set[str], reader: bool,
                   sources: Mapping[str, dict] | None = None,
                   external_enabled: bool = False) -> RagProvider
retrieve_context(query: str, load_snapshot: Callable[[], AuthorizedSnapshot],
                 provider: RagProvider, *, budget: RagBudget | None = None
                 ) -> RagSelection
```

`AuthorizedSource` 和 `AuthorizedSnapshot` 仅用于本地；其构造函数本身不是鉴权器。loader 必须依据数据库里 Episode 的真实 subject、当前 Actor、有效云端许可和故事授权取来源，不能把客户端声明的 subject 或 reader 标志当证明。`source` 接 `contextual_sources` 的规范单项，指纹复用 `narrative.fingerprint`；定位/录音时间等传输字段可以在最终选取后由 `contextual_evidence` 补上。

序列化 request 只包含：

```json
{
  "query": "台灯坏了会先修吗？",
  "subject_id": "subject-example",
  "authorized_evidence": [
    {"evidence_id": "evidence-example", "fingerprint": "<64位SHA256>"}
  ],
  "budget": {
    "max_hits": 8,
    "max_evidence": 256,
    "max_characters": 24000,
    "max_authorized_evidence": 8192
  }
}
```

这段 JSON 是格式示例，不是实际请求或可用来源；`<64位SHA256>` 是占位符。协议没有全文、邻文、人物模型、补记或 token 字段。query、ID 与指纹仍然是敏感元数据，不能把“无原文”理解为匿名或不需要云端授权。

response 只允许 `hits: [{evidence_id, fingerprint, score}]` 与 `retriever_version`。不接受外部 excerpt、summary 或位置作为本地原文；本轮也没有实现可选位置协议。重复 ID、未知/未授权/跨人物 ID、过期指纹、NaN/Infinity/bool 分数、空检索器版本或过多命中全部拒绝。Pydantic 的不经校验构造也不能绕过入口复检。

此前预算文档说非法命中可以“丢弃”；本轮具体实现采取更严格的**整批拒绝**，避免混入一条坏命中后悄悄产出不完整的正常答案。合法的空命中与检索故障保持可区分。

`RagSelection` 返回本地 `sources` 字典（以 evidence_id 为键）、`selected_evidence_ids`、`hit_ids`、`expanded_ids`、`source_basis`、`retriever_version` 和 `character_count`。字典按规范本地来源顺序返回；排序分数是检索相关性，不是证据真实性或人物判断的置信度。

## 补齐规则与预算

1. 每个命中必须存在于调用前的授权引用集合，且指纹完全相同。
2. provider 返回后再次执行 loader。人物、来源/授权版本、任一来源指纹、来源集合或安全组成员发生变化，返回 `SOURCE_CHANGED`。即使 provider 返回空命中，也执行这次复检。检索期间撤权造成第二次 loader 无权读取，也转换为 `SOURCE_CHANGED`；初次鉴权失败保留原错误。
3. 从命中开始，加入同 Episode 的**全部当前有效来源**。这包含未被 MemoryItem 完整覆盖的原文，不从 raw transcript 自行拼接邻句，不能恢复已屏蔽的词句。
4. 补齐命中的已确认故事/纠正/理解组，反复执行直到成员不再变化。理解组必须同时包含完整支持与反例；新加入的另一 Episode 也必须整组补齐，不能只保留命中前半句。
5. 检查完整结果的证据数和字符预算。超限返回 `CONTEXT_TOO_LARGE`，不切句尾，不 `[:256]` 丢反例，也不降级成 UNKNOWN。

`max_hits=8` 是检索起点数量，允许局部排序选前几项；它不是最终来源数量。最终上限为 256 个来源、24,000 个证据字符。字符按 evidence ID 分别累计 `excerpt + temporal_context`，即使两段原文相同也不抵消。授权引用全集另有 8,192 项上限，超限在 provider 调用前明确失败。所有上限可向下调，不能通过请求提高到无限上下文。

安全组必须由本地已授权、已确认、仍有效的关系生成。组含有不可读的成员就报 `RAG_CONTEXT_INCOMPLETE`；不能只把反例过滤掉后保留其余成员。对于已被正式纠正而屏蔽的旧原话，不应把它当必需组成员再恢复；通过 `MemoryRevision` / `previous_memory_id` 关联当前有效替代来源及仍有效的历史上下文。某个理解因反例不可读而不再有效时，应在本地理解解析阶段整项排除，不可把它缩成缺反例的“有效理解”。

模块校验调用方给出的组是否完整可用，不能推断调用方遗漏了某条未提供的关系。集成层必须完整读取确认的故事、纠正和理解关系，不能只查已命中的 evidence ID 后再构造组。

这只是来源预算；候选 statement、理解/整理文本、表达范例、亲友补记和整个 AI 请求仍由各自既有预算控制。把 evidence 选取缩小后，不应继续附带全集理解和反例以绕过预算；也不能把 persona 所需的完整条件悄悄截掉。

## 本地适配器与 Twin 集成

默认工厂返回 `LocalRetrievalAdapter`，复用 `retrieval.retrieve` 的本地 MemoryItem 索引和已有 encoder，并传入 subject、授权 episode_ids 与 reader 范围。索引返回的文字只是排序提示；最终内容始终来自重取的有效来源。调用方传 `sources=snapshot.source_map` 时，还使用本地原文的词面匹配作为检索起点，覆盖没有 MemoryItem 的原文空隙。这是有限的词面补充，不等于所有未提取原文都已有语义向量索引或召回率保证。

传入 sources 后，适配器在访问索引前检查其绑定的引用全集/指纹与当次 request 完全一致，并验证 Episode 范围。构造适配器与加载 request 之间如果新增、撤回或改动了来源，直接 `SOURCE_CHANGED`，不能沿用旧范围而少召回新来源。

已有本地 encoder 需要可用的模型和依赖。其加载器没有被本模块改写成离线下载器；真实运行应由运行方事先准备好模型。独立验收使用注入的 fake encoder/provider，不下载模型。索引异常返回 `RAG_UNAVAILABLE`，不会改称“本人没有留下相关内容”，也不会静默转成只有词面匹配的成功结果。工厂收到 `external_enabled=True` 直接返回 `RAG_EXTERNAL_DISABLED`；本轮没有隐式外部 fallback。

Twin 集成由主协调负责，本模块不新增客户端 API。约定保持小样本 `full` 有效全文默认；`local` 是后端可选路径，不需要给用户增加一个工程开关。建议调用顺序：

1. 短事务中执行 `publication_lock`、`require_cloud`、`visible_episodes(cloud=True)` 和读者的 `altered_story_ids` 过滤。
2. `effective_materials(..., enforce_budget=False)` 与 `contextual_sources` 构造授权候选全集；校验每个 Episode 的 subject，读取完整可用的关系组和理解。先生成有效来源再计算 source_basis（解析器可能创建稳定的原文 Evidence）。提交/释放事务。
3. 用以上数据构造本地 provider；调用 `retrieve_context`，其 loader 重复相同鉴权与来源解析，并保证每次返回前释放事务。不能跨 provider 调用持有数据库写锁。已有检索器可能刷新向量缓存；loader 应按现有事务约定处理这部分派生缓存。
4. 用 `selection.sources` 重新限制候选以及关联的理解/整理，保留每个已选理解的全部支持与反例，再调用现有 `contextual_evidence` 补齐可信时间/位置元数据。记录检索器版本、命中和补齐后的引用以便审计。
5. 发送 AI 请求前与发布回答前仍分别复检当前云端/故事许可和 source_basis。本模块返回的是一个当时有效的选择结果，不是发布许可。回答读取、声音合成和缓存读取仍使用现有有效性检查。

外部服务未来要接入，至少还需 endpoint、鉴权方式、超时/响应体预算、检索器版本规则、索引来源与更新接口、撤权/删除传播及日志保留约定。在这些未明确前，只有可注入的 typed protocol 可以用于离线合同测试，不能宣称已完成第三方 RAG 联调。

## 尚未完成的能力

- 不是完整的事件去重。`event_support` 只把本人确认且来源仍有效的 `same_event` 故事分组作为事件关联；不同录音、不同 evidence ID 或相同文本都不自动证明独立事件。
- `independent_episodes` 仍有旧协议兼容用途，不能用它报告独立印证次数或稳定人格置信度。
- 人物归纳已按完整 Episode 分批（每批 24,000 字符、最多 12 批），但没有完成跨批全局寻找所有支持、反例和时间变化。RAG 上下文补齐只保护已经存在且有效的关系，不创造遗漏关系。
- 当前 `profile_source_basis` 仍覆盖人物范围的多类材料状态。新增一段与某理解无关的录音，仍可能使旧确认理解过期；本模块没有实现精确的受影响节点增量失效和恢复。
- 同样，source_basis 的保守全局变化可能使已保存 Twin 回答过期。检索挑选少数来源不意味着已改成只按所引用的材料失效。
- 封存、校准、亲友补记、表达范例和 Voice 各有独立生命周期与许可，本合同不替代这些边界，也不承诺 Legacy 场景已经完整实现。
- 尚未进行同模型、同资料版本、同权限的有效全文/现有本地检索/第三方 RAG 三路真实对比；不填召回率、相似度、成本改善或效果数字。

## 本模块验证记录

仅执行 `tests/test_rag_contract.py`，不触碰运行库、不启停服务、不做联网/语音调用。首次红灯为新模块不存在；追加回归实际复现本地来源过期被误归为 503、检索中撤权第二次解析透传 404，以及适配器构造后来源全集/范围变化仍访问旧索引这三类缺陷。修复后 **42 项通过**。

覆盖无原文的 wire contract、未知/跨人物/过期和重复来源、非法分数、未经校验的模型实例、provider 错误脱敏、合法空命中、同 Episode/纠正/支持反例的传递补齐、补齐后的字数和数量预算、撤权与新增原文/关系变化、本地原文空隙起点、索引失败、外部禁用。这里是模块合同和注入 provider 测试；Twin HTTP 鉴权与最终发布的集成测试由接线路径另行记录，不能将本组通过等同于真实外部检索验收。

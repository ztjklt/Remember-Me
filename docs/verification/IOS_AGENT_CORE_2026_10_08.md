> 本文记录当天较早的一批连续性修复。用户随后明确要求完整循环并排除真机；当前交付与验证以 [完整软件闭环记录](IOS_FULL_AGENT_LOOP_2026_10_08.md) 为准，下面的剩余项不再代表当前状态。

# iOS Agent Core：画像连续性与校准恢复

2026-10-08。继续在 `feature/ios-android-parity` 的 iOS 原型上完善现有闭环。基线为 develop `4dc3d5a`，界面复刻为 `e3186a7`。未整体合并已经分叉的 `feature/ai-agent-core`，也未引入另一套手机直连供应商的引擎。

## 本批行为

- **连续画像：** PersonModelRepository 从持久化 Memory 维护结论和图事实的稳定 ID；已有记录的旧 ID 在新 Episode 和本人纠正后保留。新记录的 ID 从本地 Memory 生成，避免模型重复提议 ID 导致数据库冲突。无关结论保留，删除后相应结论和图事实移除。
- **证据与来源：** iOS 七领域画像、分类卡片和 Graphs 的真实结论都能打开依据页。展示支持原文、反例、来源类型、有效时间和处理模型，并能进入原音/纠正流程。依据页按 ID 查找当前结论，更新后不继续展示旧的导航快照。
- **纠正、删除同步：** 服务端操作成功后立即清除手机中的画像、旧 Twin/校准结果和检索缓存，再获取当前模型；刷新失败也不会继续呈现已失效的理解。刷新核心数据时，所有必需请求成功后才发布这批响应，避免失败一半的界面更新。这不是跨 API 的数据库快照隔离承诺。
- **校准恢复：** iOS 可以选择服务端最近 20 条校准记录，继续已有本人录音、重试处理或从同一个 ready Episode 再次比较。选中的校准不会被刷新强制改成最新一条。新校准不会覆盖另一段待处理录音。比较失败保留锁定回答与本人 Episode；已完成提交重放不再调用比较模型，并发完成保留首先提交的结果。
- **追问连续性：** 同一待回答问题复用 ID；回答当前缺口问题后先转向其他未覆盖、未回答的领域。冲突仍优先等待本人澄清，不因回答或跳过自动抹平。这仍是有限启发式规划，不是完整 Information Gain/疲劳模型。
- **降级与授权：** 个人声音服务或校准记录暂时无法读取时，各自显示恢复信息，核心画像仍可更新。撤销 Cloud Twin 后清除本机回答和校准快照，停止派生播放。异步更新检查当前配对身份；问答与校准返回时还核对当前云端授权。
- **结构化校验：** AI Core 拒绝重复 trait/fact ID、空白结论、同时作为支持和反例的同一证据，以及将转述或第三方来源冒充本人原话的 persona 提议。已有 DeepSeek/Qwen 的原文定位与七领域提取保留；通用 OpenAI-compatible 适配器仍维持 Phase 1 投影。

## 实际验证

| 检查 | 结果 | 证据边界 |
| --- | --- | --- |
| AI Core 全套 pytest | 137 passed | 包括 persona 来源、反例和重复 ID 拒绝；使用离线样例/HTTP 模拟 |
| Backend 全套 pytest | 247 项全部通过 | 包括稳定旧 ID、保留无关事实、问题复用、校准失败恢复/并发/重放、删除与授权；测试数据库走真实迁移 |
| iOS 单元测试 | 最终 7 项通过，0 失败 | 用隔离 URLSession 和 UserDefaults 检查声音故障降级、核心刷新失败、删除失效、校准重试/选择、录音防覆盖和撤销授权 |
| iOS 原生 UI 测试 | 2 项通过，0 失败 | 五入口、录音/配对页、分类搜索、档案与 Twin 导航；未注入个人画像 |
| Contract 测试 | 15 项通过，0 失败 | 契约文件未修改 |

命令（仓库根目录）：

```sh
uv run --project services/ai-core pytest services/ai-core/tests -q
uv run --project services/backend pytest services/backend/tests -q
cd packages/contracts && npm ci --ignore-scripts && npm test
```

原生验证：Xcode 27.0，iPhone 17 Pro Max 模拟器 / iOS 26.5。

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,id=D2FE37B7-EC92-4C64-A7E0-CEC9F332E987' \
  -derivedDataPath build/ios-parity CODE_SIGNING_ALLOWED=NO test
```

先运行 5 项单元测试和 2 项 UI 测试，通过后新增防录音覆盖、撤销授权两项单元测试，并用 `-only-testing:RememberMeTests` 验证最终 7 项。测试日志与 xcresult 留在忽略的 `build/ios-core-*`；初次 iOS 模拟器构建也为 BUILD SUCCEEDED。测试没有真人麦克风输入，没有读取用户密钥或调用付费供应商。虚构转写与合成测试音频不计入真人 Golden Path 验收。

最终源码（含校准状态的中文文案）也用 `-destination 'generic/platform=iOS Simulator'` 构建，结果 BUILD SUCCEEDED。完整 UI 检查仍以本段记录的两项为准。

## 完成范围与剩余验证

本批补齐的是现有 iOS/Backend 闭环中的连续性、可检查性和恢复行为，不构成“全部 AI Agent Core 已完成”的声明。仍需在真实 iPhone 上跑录音 → STT → 本人核对 → Memory/Person Model → 新问题 → 锁定回答 → 本人回答 → 五维比较 → 再次提问，并记录具体模型版本与失败点。

真实供应商的中文语义质量、姓名纠正后的多种问法、时间/情境变化区分、长期材料检索、完整 Temporal Memory Graph 与完整 Capture Planner 仍需要有界评测或进一步实现。关系图设计示意、八类展示与现有七领域语义的映射，以及声音状态/环境/情绪趋势待接入状态继续保留。完整 Voice 管线、硬件、第三方训练、Handover/Legacy 未在本批实现。

## Contract 与数据影响

`packages/contracts` 未修改，继续消费 v0.2–v0.4；没有新增端点、响应字段、数据库列或迁移。服务端结论 ID 和问题 ID 的维护方式调整为稳定且可追踪，旧记录 ID 保留。iOS 新解析的是已存在的可选来源和有效时间字段。Android 原型与手机 BYOK 实验代码未修改，未把 provider secret 放入任一客户端。

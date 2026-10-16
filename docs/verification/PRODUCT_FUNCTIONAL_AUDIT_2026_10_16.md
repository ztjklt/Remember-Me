后续修复：Owner 已要求开始修改，首批五项已实现并验证，详见 [修复记录](VOICE_AUDIT_FIXES_2026_10_16.md)。随后 CloudBase052 已配套发布，默认声音及本人音色两轮合成链路通过；iOS 1.15.3 已覆盖安装并成功启动，原有 11 个录音路径和 metadata 一致，真人听感仍待验。详见 [接入修复及交付状态](VOLCENGINE_ASSISTANT_ACCESS_FIX_2026_10_16.md)。以下缺陷与完成度表是修正前的审计基线，不能当作当前未修复清单。

# Remember Me 功能完成度与缺陷审核

2026-10-16，Asia/Singapore。当前主要缺口集中在实时语音的可靠性、云端音色删除、复刻结果验收和个人训练候选接入。录音、记忆、人物理解与文字问答已有较完整实现；本次回归通过不能代替真人语音和硬件验收。

范围以当前 iOS 1.15.1／2026101606、共享 Backend 与 AI Core 为主，对照 PRD v3.0、双端修订及后续获批切片。Android 新语音适配、硬件标记和完整 Legacy 分别标注范围；没有将尚未授权的路线阶段列为本轮必须开发的 Bug。

审计代码基线：iOS 为主工作区当前文件；Backend 为 speaker-introductions 工作树 cb8967c 及文档后续提交，线上 CloudBase051。以下链接指向本次实际审阅文件。主目录里的 Backend／AI Core 与服务端维护工作树并不完全一致。

## 需要修复的问题

### P1 云端音色删除可能被前两个未知任务堵住

[删除循环](</Users/jitian/.codex/worktrees/speaker-introductions/Remember Me/services/backend/app/api/realtime.py:365>) 每次取两个 delete_pending profile。没有 provider_voice_id 的未知复刻结果若查询不到音色，就直接 continue，不更新重试时间或让出批次。前两项持续未知或失败时，后面的已知音色会长期没有删除机会。

隔离 SQLite 复现：放入两个未知任务和第三个已知音色，连续执行三次维护；发生 6 次 list_voice、0 次 delete_voice，第三项仍为 delete_pending。证明在当前实现下可以一直阻塞，不依赖真实供应商故障。撤权后 Backend 访问已关闭，问题是供应商侧资源删除迟迟不执行，不能把它描述为撤权后仍可继续合成。

建议给删除任务持久记录下次重试时间及尝试次数，分别处理已知音色与待对账的未知创建，保证后续任务获得执行机会。验收应包含“前两项永久未知，第三项仍被删除”及重启后的恢复。

### P2 RTC 自动重连被客户端立即终止

[连接状态回调](</Users/jitian/Documents/ChatGPT/Remember Me/apps/ios/RememberMe/VolcengineVoiceTransport.swift:374>) 把 disconnected、reconnecting、lost、failed 全部交给 onFailure；[通话模型](</Users/jitian/Documents/ChatGPT/Remember Me/apps/ios/RememberMe/TwinVoiceCall.swift:244>) 随即调用 end。SDK 的 reconnecting 和 reconnected 本来区分恢复过程与恢复成功，当前代码会在重连阶段放弃通话，即使 Backend 租约依然有效。异步失败回调也没有核对期间是否已经重连成功。

这是代码路径确认的可靠性问题，本轮没有用实体手机断网复现。建议在当前许可与有效租约内暂停输入和输出、显示重连状态，等待有界恢复；失败、过期、撤权仍立即结束。验收包括 RTC 单独断开而 API 仍通、恢复成功、持续失败和撤权期间重连。

### P2 资料不足时缺少可听见的回执

[CustomLLM 回调](</Users/jitian/.codex/worktrees/speaker-introductions/Remember Me/services/backend/app/api/volcengine_voice.py:414>) 对 UNKNOWN 发送空文本；[本人音色播放](</Users/jitian/Documents/ChatGPT/Remember Me/apps/ios/RememberMe/TwinVoiceCall.swift:548>) 也跳过 UNKNOWN。未知事实没有被不当朗读，这是正确的边界；但语音用户会听不到解释，容易把资料不足当成连接或播放故障。

建议为资料不足提供明确、安全的固定反馈，并结束这一轮等待状态；保留不朗读未核验内容的约束。现有测试只检查未知内容不会泄露，没有覆盖用户能否获得清晰回执。是否出现长时间“思考中”仍需状态事件组合测试确认。

### P2 复刻结果没有本人确认或拒绝的闭环

[音色就绪界面](</Users/jitian/Documents/ChatGPT/Remember Me/apps/ios/RememberMe/TwinVoiceCallView.swift:66>) 提供试听，缺少保存“像我／不像我”结果的入口；[进入页面和状态变化](</Users/jitian/Documents/ChatGPT/Remember Me/apps/ios/RememberMe/TwinVoiceCallView.swift:139>) 会自动选择就绪的本人音色。Backend 把供应商返回 OK 转为 ready，没有复刻结果的本人验收字段。

录制前确认“这是本人声音”解决样本真实性与授权，不能代替复刻后音色满意度验收。PRD FR-008 的试听已经具备，确认／拒绝与不满意后的低成本重试仍不完整。建议记录验收结果，并保留默认声音选择及重做入口。

### P2 当前版本难以从 Git 单独复现

主目录的 TwinVoiceCall.swift、VolcengineVoiceTransport.swift、PersonalModelView.swift、DeviceConnections.swift 等关键文件仍未纳入 Git。当前可构建版本依赖本机文件，单独检出当前分支不能完整还原已安装版本。

AI Core 的两个工作树也存在 5 个同名文件差异，服务端维护工作树另有 12 个主目录没有的 Python 文件，包含 grounded_twin、expression、profile_proposals 和供应商适配。它们各自测试通过，不等于两份代码已经合并。后续从旧目录制作镜像有退回旧能力的风险。

建议先保存明确的完整 iOS 源码快照，整理一次可复现的服务端与客户端发布基线，并为当前已安装包记录源码版本、依赖与产物摘要。不得把私有配置、凭据或 Vendor 二进制混入普通提交。

## 功能完成度

| 功能 | 当前状态 | 需要补齐的部分 |
| --- | --- | --- |
| 账号、独立许可、人物空间隔离 | 已实现，相关回归通过 | 普通用户自助找回和注销流程未形成完整入口 |
| 手机录音、本地保存、核对、异步上传与重试 | 已实现，相关回归通过 | 本次未追加新一轮真人录音验收 |
| 记忆、来源、纠正和删除 | 已实现，级联失效有测试 | 全量资料导出和账号级删除闭环未形成 |
| 七域人物理解及确认更新 | 已实现 | 模型忠实度仍需本人验证，资料覆盖不能解释为人格完成率 |
| 文字 Twin、旧聊天与来源检索 | 已实现，相关回归通过 | 真实复杂问题、矛盾和时间变化的质量仍需长期评估 |
| 默认声音与本人音色 RTC | 代码及服务已接入，完整链路待验 | 1000002 已修正；修正后浏览器注入没有取得答案，手机试听与持续通话尚未通过 |
| 声纹姓名、本人原话记忆、自然取样 | 已实现，有隔离合成验证 | 新 RTC 线路下真人、多说话人、噪声及长通话待验 |
| 声音复刻与试听 | 已接入原 CosyVoice | 删除队列、本人结果验收和失败重试体验需修正 |
| locked-answer 校准与五维比较 | 已实现，相关回归通过 | 仍需本人参与，不能视为无人值守的自动校准 |
| 个人模型训练 | 候选训练与任务管理已实现 | 候选还没有接入正式问答，也未接入候选专属盲测或部署 |
| 引导采集 | 规则版已实现 | 完整动态访谈、疲劳／时间／信息增益规划仍不完整 |
| 录音豆 | 官方 SDK 适配、文件导入、手机回退已接入 | 实体同步与持续佩戴待验；Marker 回调为空，标记未进入记忆资料 |
| 托付与 Legacy | 指定账号、密语、范围许可、人工核验切片已实现 | 完整产品验收和长期运行尚未完成；自动身后判定仍非当前范围 |
| Android 的新 RTC 路线 | 本次审阅未找到火山通话适配 | iOS 新通话能力不能算作双端已交付 |

个人训练缺口有明确代码依据：[Backend 返回 activation_allowed=false](</Users/jitian/.codex/worktrees/speaker-introductions/Remember Me/services/backend/app/api/personal_learning.py:62>)，iOS 也说明候选尚未切换。现用 Twin 仍能根据记忆和人物资料回答；这和候选参数已经用于推理是两件不同的事。

[引导问题生成](</Users/jitian/.codex/worktrees/speaker-introductions/Remember Me/services/backend/app/repositories/person_model.py:147>) 优先取一条未解决冲突，否则取第一个未覆盖领域的固定问题，尚不是 PRD 中完整的动态 Capture Planner。[硬件标记回调](</Users/jitian/Documents/ChatGPT/Remember Me/apps/ios/RememberMe/SoundcoreWorkAdapter.swift:44>) 目前为空。当前已有画像文字分享，缺少的是原音、原始来源、人物版本等完整资料包的用户导出闭环。

## 本次验证

| 检查 | 实际结果 |
| --- | --- |
| 服务端维护工作树 Backend 全量 | 814 项，808 通过，6 跳过；跳过为需独立 PostgreSQL 测试库的探针 |
| 服务端维护工作树 AI Core 全量 | 296 通过 |
| 主目录旧 AI Core 全量 | 133 通过，作为目录差异对照，不与 296 重复合计 |
| 当前 iOS 全部单元测试 | 164 项，163 通过，1 跳过；跳过为缺少短时硬件 QA receipt 的 SDK 检查 |
| 契约 | 48 通过 |
| 删除队列定向复现 | 已复现，三次维护没有处理第三个已知音色 |
| 实体通话和硬件 | 本人暂时无法通话；本轮不宣称新增真机通过 |

日志保留于各工作树 ignored build：product-audit-backend-tests-20261016.log、product-audit-deployed-ai-core-tests-20261016.log、product-audit-ai-core-tests-20261016.log、product-audit-contracts-20261016.log、volc-research/product-audit-ios-tests-20261016.log；删除复现证据为 product-audit-voice-deletion-queue-20261016.json。复现只使用临时本地数据库和假供应商，没有调用或删除真实用户音色。

## 修复顺序

先保证删除任务可以持续完成、RTC 有界恢复和资料不足时的清晰回执，再完善音色验收与重做流程。同时保存可复现的发布源码。随后安排一次可用时段验证本人音色、姓名、插话、静音、两分钟连续问答及挂断清理。个人候选接入、完整动态访谈、资料导出和硬件 Marker 作为明确的后续功能项推进，保持现有授权与阶段边界。

本轮审核没有修改上述新增问题的业务实现。先前本人模式初始化修正与测试记录另见 VOLCENGINE_PERSONAL_STARTUP_FIX_2026_10_16.md。

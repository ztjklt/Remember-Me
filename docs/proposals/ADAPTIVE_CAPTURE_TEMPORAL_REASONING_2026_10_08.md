# 自适应采集与时序归因实现约定

用户在 2026-10-08 明确要求信息增益、疲劳控制、长期自适应及完整时序因果推理，继续排除真机工作。本文件记录该授权范围内的 feature 实现，延续 FULL_AGENT_LOOP_METADATA 的可选内部约定，不冻结新跨模块 Contract。

公开 endpoint、必需字段、MemoryType、GraphFact kind、Question status 和 packages/contracts 均保持原定义。现有开放 subject_context 可选携带服务端生成的 current_memories；现有 Memory.metadata 可选承载 temporal_causal 与读取时重新计算的 temporal_causal_view。现有 graph_facts 字符串列表向私有 Twin worker 提供归因路径提示。旧客户端和省略新字段的旧提取调用仍可用。新的正式 Contract 字段/接口仍按 AGENTS 要求走 Product / Integration 审核。

Backend 私有迁移 0008_capture_policy 为 capture_questions 增加可空 JSON policy_snapshot，旧行可空、可降级、支持 downgrade；不增加公开数据库接口。snapshot 保存评分组成、负担估计、版本、证据基线 IDs 和结论散列，不复制结论原文。回答效果由有效本人材料重算，删除基线/回答材料撤回相应统计。

因果结构保留精确原话、原 Memory 结论快照、证据、源/目标引用、时间文本、语境及模型版本。持久化时新 memory_index 替换为 Backend 生成的 Memory ID。读取时再验证当前源；纠正、删除、跨 Subject 引用和第三方依据均不能保留推理链。派生展示不写回原文或新本人事实。

不增加云服务、不改 Android 原型、不修改 Voice grant、不给客户端放 Provider 凭据。iOS 的主动休息偏好按 Subject 存在本机，后台不因刷新次数推断疲劳。任何新跨设备偏好接口仍需正式 Contract 提案。

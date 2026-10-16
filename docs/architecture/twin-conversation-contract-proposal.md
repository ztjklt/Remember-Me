# 孪生连续会话与本人文字记忆

2026-10-13，Product / Integration / iOS Owner 直接要求“把孪生的多轮上下文接上，要能像普通 LLM 那样连续聊，记住前面说了什么，同时越来越像用户”。本提案记录该请求批准的 iOS-first 兼容扩展；Android 原请求与 ECS 部署保持现状。

## 接口与存储

Twin 请求可选增加 conversation_mode、previous_answer_id、request_id；未启用会话的旧请求仍走原有证据问答。服务端只读取同 Actor、Subject 的已保存答案链，不接受客户端伪造的 assistant 或 system 消息。新会话没有 parent；续聊指定已保存 parent。request_id 在同账号与空间中幂等，内容或 parent 不同的复用拒绝。

响应可增加 conversation_id、parent_answer_id、context_turn_count、context_truncated。新 CONVERSATION 标签用于对话记忆、澄清、普通交流；与 ORIGINAL / SIMULATION / UNKNOWN 分开，不能当作人格证据。读取仍重新检查权限与来源；已经失效的模型回答不再发送作事实。旧用户问题保留为明确的会话材料。保留最近 20 轮、最多 24000 字的完整交换，溢出显式说明，不暗示无限记忆。

只把问题、有效历史消息与当前已授权来源发送给既有服务端主模型。检索问题附加近期主题，生成与语义核对看到实际会话。先前 assistant 内容只说明“前面说过什么”，不能成为本人事实；本人在聊天中的描述可以在本会话参考，但未经明确保存不会进入长期人物证据。

## 越来越像本人

新增 POST /twin/answers/{id}/remember，仅本人所有者可在明确用途确认后保存自己实际发送的那句话。后端读取不可变的 question，拒绝写入 assistant 内容；须有有效 CLOUD_TWIN 及 RECORDING 采集授权。保存成 IOS_TEXT 文字 Episode 与现有 owner_supplement 记忆，来源是本人确认的书面说明，标明来自哪个聊天问题，不伪造原音或转写。文字 Episode 的原音引用为空；音频端点明确无原音。此路径沿用已授权人物候选整理与本人确认，不自动接受模型的性格归纳。

新的文字可以参与记忆检索；人物候选仍要本人核对、表达范例仍须本人确认并启用。校准只接受 ORIGINAL / SIMULATION 的有效证据答案，普通聊天回应不能锁定为人格预测。会话量和复述成功不能作为相似度指标；本人的新问题评审、条件变化和反例仍是质量验收。

共享 Schema 新增 v0.5，保留 v0.1–v0.4。迁移增加 Twin 链与幂等字段、CONVERSATION 类型、IOS_TEXT 来源及无原音字段；不删除既有录音、记忆、审核记录或提供商配置。CloudBase 后端部署与 iOS 构建属于原会话已授权工作；手机安装继续遵守本人暂缓安装的偏好。

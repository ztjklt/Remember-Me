# 数字托付、密语与专属对话提案

状态：待 Product / Integration Owner 批准。会议 §2.3，Phase 4 条件能力。本文件完整保留未来指定亲友持续对话的目标，不将现有即时分享称为身后托付。

## 复用基线与差距

既有 `ShareInvitation` 支持 created → claimed → approved，以及 rejected/cancelled/expired/revoked；邀请领取后仍由 owner 批准。`StoryGrant` 按 Episode／reader 授权，cloud_processing_allowed 分开，撤销邀请只撤销该邀请新建授权，既有其他授权保留。`sharing.py` 提醒实际开放完整原音和文字。

这些是即时分享的基础，不含保护区域、密语或可信身后状态。`api/twin.py:ask` 的非会话路径通过 require_cloud 支持已授权 reader 的范围文本问答，但 conversation_mode 明确要求 owner。当前 `api/realtime.py` capabilities/calls 调用 require_subject，其内部同样要求 owner，CLOUD_TWIN／VOICE 也绑定通话 Actor。不能把主人公许可、音色和旧 ticket 交给亲友复用。`recipient_label` 只是 narrative 展示文字，不是访问对象标识。

## 目标流程

本人选择记忆 → 查看完整实际开放范围 → 指定亲友账号 → 选择即时或未来条件、是否密语 → 保存草案 → 接收者领取邀请 → 本人确认对象和范围 → 接收者验证身份及当前授权 → 满足条件后解锁 → 在该范围内持续问答。许可撤销后停止本次专属输出。

第一建议切片先做本人设置、即时指定对象和资源保护／解锁；未来条件始终关闭。第二切片在可靠验证流程批准并实现后才启用 Legacy。专属实时语音需追加明确的 Recipient Voice 范围与 Call 权限版本，不能借用当前 owner 接口。

## 状态与权限

| 对象 | 状态／不变量 |
| --- | --- |
| EntrustmentPlan | draft / confirmed / suspended / revoked；版本化范围，不是人格所有权转移 |
| RecipientBinding | 已验证 Actor＋具体资源，显示名字／密语不替代绑定 |
| ActivationCondition | immediate 或 after_verified_transition；未知、pending、disputed 均拒绝 future-only 内容 |
| LegacyActivation | inactive → pending_verification → verified → active；驳回／争议进入 suspended；状态证据与谁有权限审核须另行批准 |
| ScopedConversation | actor、subject、resource_scope、plan_revision、grant_revision、unlock_id、baseline_revision；只承接同一有效范围的答案链 |

授权谓词为：有效身份 AND 指定对象绑定 AND 当前资源授权 AND 激活条件满足 AND（如设置）有效解锁 AND 操作所需独立许可。任一为未知或过期即拒绝。语音密语的 ASR 只用于取得待核对文本，误识别不开放资源；第一版建议本人输入或核对后提交，避免直接由识别触发权限变化。

密码／密语不以明文保存或写入日志。验证失败不提示内容是否存在，速率限制和重置由 owner 管理；重置使旧解锁会话失效。本人可设置多个区域和不同亲友，B1 的解锁不增加 B2 的范围。

## 候选接口（尚不存在）

| 路径／操作 | 输入／输出要点 |
| --- | --- |
| POST /subjects/{subject}/entrustments/preview | record／Episode 选择、对象、条件；返回展开范围、原音／文字提示、当前 protection 和 source 版本 |
| PUT /subjects/{subject}/entrustments/{id} | expected_revision＋preview_revision＋对象配置；新版本及 enabled=false 的条件能力，整批原子保存 |
| POST /entrustments/{id}/confirm 或 /revoke | owner 核对，记录审计；撤权使当前输出不可用 |
| POST /entrustments/{id}/unlock | 已登录指定对象及密语／核对文字；短期不透明句柄 |
| POST /entrustments/{id}/conversations | 服务端计算资源范围；返回限定会话标识／当前版本，不发送全部 owner 画像 |
| POST /entrustments/{id}/conversations/{cid}/questions | question＋parent_answer_id＋request_id；parent 必须同 Actor、同范围、同版本且有效 |
| POST /subjects/{subject}/legacy/verification | 受批准角色提交状态证据；只进入 pending，不由 LLM 或密语自行激活 |
| POST /subjects/{subject}/legacy/activate | 受批准权限及已核验条件；原子冻结 baseline 与授权快照 |

这些跨模块字段和状态需要新版本 Contract／迁移；版本号由批准时确定，不预先占用当前 v0.8。普通 owner／旧 reader 调用保持现有协议，但服务端保护必须对旧路径同样生效。新的专属语音 request 需要单独提案，不能在缺字段时默认授予亲友本人声音。

## 检索、人格和撤权

所有索引、故事、原音、表达、聊天摘要、旧回答和缓存复用 [保护范围规则](protected-garden-proposal-2026-10-14.md)。受保护的一个摘录不能通过整段授权泄漏：第一切片继承 Episode 粒度限制，预览真实展开范围；需要部分原音开放时先实现可验证的裁切资产及授权，不能隐藏界面后继续分享完整原音。

Recipient 对话不创建 Subject 人格事实或自动确认，第三方讲述是隔离上下文／待审核贡献。Legacy 激活冻结 Personality Baseline；后续世界信息另作带来源的情境信息，不改变历史人物。引用本人原话、推测、交流与 UNKNOWN 标识保留，未知不使用本人音色朗读。数字人物不能生成新的意愿或访问授权。

撤权、条件争议、来源删除、解锁到期、登录退出或范围变化使生成和播放停止；重试创建新受限会话，不继承另一对象／另一范围的前文。停止访问先持久化，远端房间和音频资产按有界任务清理。已经传到他人设备的材料不能声称可远程完全收回。

## 验收用例（待实现后运行）

| ID | 场景 | 预期 |
| --- | --- | --- |
| EM01 | 正确密语但没有身份／指定对象授权 | 无内容、元数据、音色或会话 ticket |
| EM02 | 两亲友分别访问 X、Y，交叉追问 | 对应范围分别有效；图、摘要和前文不会跨范围泄漏 |
| EM03 | 邀请领取但 owner 未确认／已过期 | 不开放资源；旧即时分享权限不会扩大托付范围 |
| EM04 | future-only 条件 unknown/pending/disputed | 不开放；LLM、声音相似度和密语不能改变状态 |
| EM05 | 实际已验证激活 | 记录审核证据、冻结 baseline；后续 Recipient 聊天不改其版本 |
| EM06 | 生成／合成／播放时撤权或到期 | 输出停止；晚到答案、旧 ticket、历史问答都不可复用 |
| EM07 | 选故事实际涉及整段含其他秘密的录音 | 预览明确扩大范围；不能用只分享摘要文案掩盖完整原音 |
| EM08 | 原始来源删除或基线变化后旧 parent | 拒绝并创建新上下文，不默默承接已失效资料 |
| EM09 | Recipient 请求本人声音、没有新 Voice 范围 | 拒绝，当前 owner VOICE 不被复制 |
| EM10 | 状态误激活／争议处理 | 暂停全部 future-only 访问和输出；按批准恢复流程处理，有可审计历史 |

批准点：资源粒度和指定对象、即时切片范围、密语期限、Recipient Voice 许可、可信状态验证角色／证据／争议流程及冻结策略。后四项未批准前不启用身后开放。iOS 由张天霁推进，Android 由刘修贤独立推进；只在具体共享接口冻结时协同。

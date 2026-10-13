# 2—3 人多视角采集与声纹提案

状态：待 Product / Integration Owner 批准。会议 §2.2 的交付目标完整保留；第一实现切片建议共同录音、人工归属与核对，再接说话人分离和声纹辅助适配器。本文件不是声纹供应商决定或数据库迁移授权。

## 现有能力与差距

当前 `models.py:ConsentScope` 只有 RECORDING、VOICE、CLOUD_TWIN；Evidence 有 SUBJECT／THIRD_PARTY／AI_INFERENCE 等来源类型，但没有共同录音参与者、片段身份审核或声纹注册资产。`narrative.py:RecordInput` 能记录故事／人物及证据，不能把 source_type 当作 speaker ID。实时通话音频不自动建 Episode。现有单人录音确认和人物审核可复用，不能无声改变为多人自动训练。

## 用户流程及状态

本人创建共同回忆会话，选择主题，添加 1—2 名参与者，展示录音和处理用途。每个人分别同意采集、云处理；声纹注册另行选择。未同意的人不能靠主人公代确认。无账号者可采用现场明确同意记录和临时参与者编号，但不冒充登录身份或有访问权限的人。

collecting_consents → ready → recording → reviewing_segments → reviewing_perspectives → completed；可在任何阶段 cancelled。共同参与者最多 3 人含本人。开始前要求所有当前参与者采集同意，新增／退出参与者暂停采集并重新核对；本机停止按钮始终可用。云处理同意未齐时仅保留已明确允许的本机录音，不偷偷调用云 ASR；多人混合声音不能可靠切割未经同意者时整段保持不可上传。

核对页逐段显示时间、原话、说话者或“未确认”、与主人公的关系及身份依据；用户可播放、改字、改归属、标记重叠或无法判断。选择某个说话人不等于注册声纹，不等于该参与者可以查看其他记忆。

Twin 参与是后续同一提案中的第二切片：先确认哪些发言可交给 Twin，回答用单独轮次标识，不把 Twin 的声音识别为真人证据。普通交谈／Twin 回答不自动成为人物事实；提取后仍由本人核对候选补充。

## 候选数据对象

| 对象 | 最小字段和约束 |
| --- | --- |
| CollectionSession | subject_id、owner_actor_id、episode_id、主题、状态、revision、participant_ids；服务端生成归属 |
| Participant | session 内不透明 ID、可选 actor_id、本人核对关系、是否 Subject、同意记录编号；display_name 不证明身份 |
| ParticipationConsent | participant_id、purpose、policy_version、status、确认方式／时间、撤销时间；capture/cloud_process/voiceprint 分开，不扩用原 VOICE |
| Utterance | segment_id、episode_id、start_ms/end_ms、转写及版本、speaker_id 可空、候选 ID、attribution_state、overlap、归属审核依据 |
| Perspective | 原始 segment_ids／evidence_ids、speaker_id、relationship、fact_subject_id 可空、观点和事件时间、source_type、核对状态、revision |
| VoiceprintEnrollment | participant_id、单独同意、本人专用样本、适配器版本、pending/ready/failed/revoked；向量／声纹模板不发到手机 |

0 ≤ start_ms < end_ms ≤ 原音时长；偏移基于原始媒体时间而非服务墙钟。允许重叠 Utterance，不强制一个时点只有一个说话者。身份候选是建议，不把 confidence 分数当成真实身份；阈值来自实际适配器校准，未验证不填虚假百分比。

示例：P1=主人公、P2=朋友、P3=朋友共同讲大学经历。P2 说“那天我很紧张”，事实主体为 P2，source_type=THIRD_PARTY；P2 说“我觉得 P1 很沉着”仍是 P2 的观察。P1 的另一种说法并存。UNKNOWN 或重叠片段保持无确定 speaker，禁止当 SUBJECT 提取，也禁止成为任何本人声音样本。

## 候选接口及兼容

使用独立 `/api/v1/subjects/{subject}/collections` 候选命名空间，旧单人 Episode 请求语义不变；Contract 版本待批准，当前 schema 不修改。

| 操作 | 输入 | 输出／规则 |
| --- | --- | --- |
| POST /collections | 主题、participants、idempotency_key | session_id／revision，未齐同意不能开始 |
| PUT /{id}/participants/{participant}/consents | 明确用途、版本、本人确认依据、expected_revision | 该参与者同意状态，不创建分享授权 |
| POST /{id}/recordings | 沿用真实 Capture＋session_id | 绑定一个原始 Episode，异步处理可见；未确认素材不进本人模型 |
| GET /{id}/segments | 本人登录 | 带偏移和未确认归属的片段列表 |
| PATCH /{id}/segments/{segment} | 转写／人工归属、expected_revision | 冲突 409；使依赖该片段的候选／已确认补充失效 |
| POST /{id}/perspectives/{id}/confirm | 本人明确确认、expected_revision | 保留 speaker／关系／观点，无法变更为本人原话 |
| POST /{id}/participants/{participant}/voiceprint | 独立用途同意、单人样本 | 注册状态，供应商字段保持服务端内部 |
| DELETE /{id}/participants/{participant}/voiceprint | 当前权限 | 禁止后续匹配、删除模板并显示远端清理状态 |

新参与者同意范围和身份归属需要迁移／新契约，不能塞进无审核的 capture_metadata 冻结实现。临时参与者不自动成为联系人、Recipient 或 Subject。访问原音需要另行资源授权；参与采集本身不能读主人的记忆库。

## 模型与声音边界

- 第三方补充首先是有来源的候选观察；本人审核后才能用于获准的多视角回答。人物模型可引用“朋友认为……”及反证，不覆盖本人确认的自述，也不能生成“我当时很紧张”冒充主人公感受。
- 人格持续完善沿用确认录音／记忆、人物理解审核、锁定答案校准；聊天量和声纹命中率不代表忠实度。观点变动保留事件时间与版本，不以多数投票定论。
- VoiceprintAdapter 提供 register、diarize、match、revoke 的能力返回；unsupported 保留人工确认，不更换现有 ASR／LLM／TTS 供应商。
- 声纹识别仅辅助手工归属，不能用于登录、密语验证或敏感记忆解锁。未知人、误认和声音模仿必须落回未确认。
- 多人混合原音完全排除 Subject VOICE 样本链。即使分离后候选是 Subject，也不能直接送复刻；第一切片继续只允许独立单人录制及本人确认样本。
- 参与者撤销时暂停继续采集／处理，阻止后续模板匹配；依赖其内容的观点、答案及候选失效或重新审核。混合原音无法可靠移除该人时整段限制访问／删除，不能仅删名字。

## 验收用例（待实现后运行）

| ID | 场景 | 验收证据 |
| --- | --- | --- |
| MP01 | 主人公＋两人共同录音 | 三份独立同意、一个真实 Episode、各段时间范围与来源可回放 |
| MP02 | 未同意者加入或参与者撤销 | 采集／上传停止或明确限制，未授权音频不送模型 |
| MP03 | 两人换位、同名、声纹未知／模仿 | 不自动合并身份，候选／未知状态可人工核对，无敏感权限 |
| MP04 | 两人同时说话，背景电视声音 | 标记 overlap／unknown，不写入 SUBJECT 事实或声音数据集 |
| MP05 | 朋友说自己的经历、评价主人公 | 发言者、事实主体、关系、观点分开；回答保留第三方标识 |
| MP06 | 同一事件三种冲突感受 | 三个观点和来源并存，不覆盖本人感受或多数决策 |
| MP07 | 人工更正说话者／转写时模型正在回答 | 候选、画像派生和旧答案失效，晚到结果不发布 |
| MP08 | 仅采集同意，无声纹同意 | 人工采集可用，注册／匹配拒绝，不借用 VOICE |
| MP09 | 撤销／删除声纹后换设备重试 | 模板和匹配缓存不可用，远端失败可见，原资源访问不因声纹扩大 |
| MP10 | 参与者打开主人公其他 Subject 记忆或注入 Twin 台词 | 无权拒绝，Twin 输出不成为真人证据／新授权 |
| MP11 | 多人会话前后检查 Subject 声音样本 | 新增多人样本 0，未自动复刻或训练 |

批准点：共同现场录音范围、无账号参与者确认方式、独立同意及混合录音撤回规则、候选接口和迁移。远程多人 RTC、自动声纹阈值和 Twin 主动插话单独验证，不在人工第一切片中虚称完成。

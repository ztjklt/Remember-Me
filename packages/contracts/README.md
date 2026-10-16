2026-10-16：Product / Integration Owner 已明确要求启动并修复[游客暗号托付修订](../../docs/architecture/guest-entrustment-contract-2026-10-16.md)。独立 [guest-entrustment-v1](schemas/guest-entrustment-v1.schema.json) 定义无接收者账号的完整来源托付，兼容增加 `secret_confirmation_required` 与本人恢复检测索引的 `secretIndex` 请求；[guest-access-v1](schemas/guest-access-v1.schema.json) 增加可选 scope_version、entrustment 与 entrustment_attempt。游客说出完整暗号后进入对应亲友的专属范围；专用暗号输入失败也脱敏，不进入普通 Twin 问答。旧账号托付不会自动扩大权限。

2026-10-16：Product / Integration Owner 明确批准[主用户与亲友／游客双模式](../../docs/architecture/guest-access-contract-2026-10-16.md)。独立 [guest-access-v1](schemas/guest-access-v1.schema.json) 定义完整来源预览／发布、本机受限入口、临时游客会话及原账号密码复验；已有协议保持不变。游客仅可查看开放花园、回听对应整段原音、进行范围内文字和语音问答。游客凭据不能通过本人身份校验，不采集本人资料或训练；退出清理会话，修改来源／撤销使旧访问失效。原音与语音响应均禁止缓存。

2026-10-15：新增已授权 [后台录音豆切片](../../docs/architecture/background-wearable-capture-2026-10-15.md)。Owner 作用域 `GET /api/v1/subjects/{id}/recording-device/capabilities` 与 `POST .../session`（`installation_id` 为 20–64 位字母／数字／连字符）提供 SDK 临时会话，响应见 `schemas/recording-device-v1.schema.json`，`Cache-Control: no-store`。不向移动端提供厂商长期 app_key。`WORK_3200` 录音复用既有 Capture，自动记忆必须有当前有效的本人声纹匹配；未知／亲友段保留为待核对内容。旧客户端形状不变。

2026-10-16：Owner 已确认并要求实施[持续采集与重点区间](../../docs/architecture/wearable-priority-capture-2026-10-16.md)。独立 [wearable-priority-v1](schemas/wearable-priority-v1.schema.json) 定义 WORK_3200 可选 metadata 与既有 `subject_context.wearable_capture`。标记按开启／关闭配对，重点跨切片仍完整保护，普通完全相同条目可合并全部证据；原音保留，未知／亲友仍待核对。缺失标记或可靠时间映射时保护整段。机器稿仅在不破坏证据的前提下清理，实际保留状态必须如实返回。此授权不创造 SDK 未提供的佩戴开录或实体按键重映射能力，旧客户端协议不变。

# Integration Contract v0.12

2026-10-15 Product / Integration Owner 授权：真正的 Subject 内声纹模板与跨段匹配，普通／多人录音与同一手机多人 Twin 对话；仅匹配本人声音自动更新记忆；指定账号＋语音辅助确认＋密语的专属范围托付；独立人物模型资料覆盖图。v0.11 定义完整保留，新形状在 v0.12。见 [批准修订](../../docs/architecture/voiceprint-personal-model-contract-v0.12.md)。声纹不代替账号、密码或授权，声音无法确认时继续交流。交接由事先指定照护人记录核验，不能由声音或 LLM 自动触发。

# Integration Contract v0.11

2026-10-15 本人修订：点击开始确认本次用途，无重复勾选／固定同意句；姓名自然关联、听不清保留编号和文字。普通语音对话可自动留作待核对资料，并复用清晰单人片段后台准备音色。v0.10 定义保持不变，独立授权仍在服务端记录和校验。见 [获批修订](../../docs/architecture/natural-capture-contract-v0.11.md)。

# Integration Contract v0.10

2026-10-15：获用户授权的本段多人识别，通过语音自我介绍自动关联姓名，无手动确认步骤。新增独立 SPEAKER_IDENTIFICATION 许可、上传／处理／报告与能力形状；v0.9 定义完整保留。见 [获批提案](../../docs/architecture/speaker-introductions-contract-v0.10.md)。本段姓名仅是自述标签，不创建跨录音声纹档案；多人原音不进入本人模型或复刻训练。

# Integration Contract v0.9

2026-10-14：个人训练与复刻验证新增独立 MODEL_TRAINING 许可、本人训练开关与真实候选状态；固定情境题先封存预测，再收本人回答和五维评审，资料不足时评分为空。当前验证对象为现用 Twin，个人候选尚未接入推理或专属验证。暂停训练仍可查找、撤销已有有效许可，不会自动重新启用训练。见 [获批提案](../../docs/architecture/twin-personal-learning-proposal.md)。端点按对应 `$defs` 校验；通用包使用 `anyOf` 兼容无 discriminator 的相同请求形状，v0.1–v0.8 保持不变。

# Integration Contract v0.8

默认声音通话获 Product / Integration Owner 明确批准，见 [提案](../../docs/architecture/twin-default-voice-proposal.md)。新增可选 default_voice_available 与 voice_mode；旧请求省略模式仍使用本人音色。默认模式无需复刻样本，仍需声音与云端问答独立许可。v0.1–v0.7 保持不变。

# Integration Contract v0.7

2026-10-13：获授权的旧聊天长期记忆，见 [提案](../../docs/architecture/twin-chat-memory-proposal.md)。近期20轮之外可检索同 Actor / Subject 的历史原消息，模型摘要保留原消息编号，不成为人格证据。v0.7 增加 recalled_turn_count、history_summary_status、recalled_answer_ids 及本人聊天记忆查看／开关／清除形状；旧客户端请求仍有效。清除会删除派生索引／摘要并设置时间界限，原聊天记录和独立保存的 IOS_TEXT 不随此操作删除。

# Integration Contract v0.6

Version `0.6.0` adds separately consented real-time Twin voice profiles, capabilities, call requests and short-lived LiveKit room tickets. The [approved realtime proposal](../../docs/architecture/realtime-twin-voice-contract-proposal.md) records the owner’s LiveKit Cloud / CosyVoice direction and authorization boundaries. Provider credentials stay server-side.

Version 0.5 adds owner-scoped multi-turn Twin context and explicitly confirmed chat text capture. The Product / Integration Owner request and approved boundaries are recorded in [the conversation proposal](../../docs/architecture/twin-conversation-contract-proposal.md). Requests opt in with `conversation_mode`; `previous_answer_id` references a server-owned prior turn and `request_id` supports stable retries. `CONVERSATION` is separate from evidence prediction and cannot enter locked-answer calibration. Confirmed original user text is an `IOS_TEXT` Episode without audio, using owner-supplement provenance and the existing pending profile review loop. No assistant text automatically becomes personal evidence. Older Android calls and v0.1–v0.4 schemas are preserved.


Version `0.4.0` adds a locked Twin calibration start, a completion request after a confirmed human Episode, and a typed result with five comparison dimensions. `calibration_id` is optional capture metadata for iOS recordings; old Android and iOS request shapes remain valid. The [calibration proposal](../../docs/architecture/calibration-contract-proposal.md) records the Product Owner direction and provenance boundary. See `schemas/integration-contract-v0.4.schema.json`.

Version `0.3.0` adds the approved iOS-first Twin query/answer, evidence provenance, `UNKNOWN` routing, and local Voice profile/speech status in `schemas/integration-contract-v0.3.schema.json`. It is additive: v0.1 and v0.2 schemas remain available for Android and earlier iOS consumers. The [cross-module proposal](../../docs/architecture/twin-voice-contract-proposal.md) records Product Owner authorization and the sensitive-data boundary.

Version `0.2.0` adds the iOS voice-to-Person-Model closure authorized in [Issue #75](https://github.com/ztjklt/Remember-Me/issues/75). The prior v0.1 schema is retained for existing Android fixtures. The v0.2 schema adds `IOS_MIC`, typed graph facts and person traits, a seven-domain model snapshot, and a capture question. Existing Android capture fields and values remain valid.

The Backend and AI Core use v0.2 for newly extracted memories; a memory keeps the schema version that produced it. Only evidence that resolves to an original transcript span enters AI Core output. Backend correction evidence is separately attributed to a calibration audit record.

This package is the source of truth for cross-module payloads. Version `0.1.2` remains frozen for Phase 1 consumers; versions `0.2.0`–`0.6.0` add the approved iOS capabilities without changing that older file.

The current machine-readable schema is `schemas/integration-contract-v0.12.schema.json`; v0.1–v0.10 remain for existing consumers. Validate payloads at module boundaries. Additive optional fields may be proposed in a Pull Request; removals, renames, type changes, required-field changes, enum changes, or semantic changes require an Issue plus Product and Integration Owner approval.

## Contract status by phase

Phase status describes when a contract is expected to be implemented. It does not change any field definition — the schema is unchanged by this table. Contracts marked Planned are **not** frozen, and their details must not be invented by a single member.

| Contract | Phase status | Input | Output |
| --- | --- | --- | --- |
| Capture / Create Episode | P1 COMMITTED | audio + subject/actor + recording consent + idempotency + source + time + metadata | `episode_id` + `upload_status` |
| Processing Status | P1 COMMITTED | `episode_id` | status + progress + error |
| AI Process | P1/P2 approved slice | `episode_id` + transcript + `existing_model_version` + optional trace | typed `memory_items[]`, `graph_updates[]`, `persona_updates[]`, `evidence[]`, and `model_version` |
| Person Model Snapshot | P2 approved slice | `subject_id` | seven domains with evidence-linked traits and optional graph facts |
| Capture Question | P2 approved slice | current model gaps or contradictions | target domain, reason, evidence, and status |
| Episode Result | P1 COMMITTED | `episode_id` | ready state + typed `memory_items[]` + `model_version` |
| Twin Query | iOS-first approved slice, v0.3 | `subject_id` + reviewed query + `CLOUD_TWIN` consent | answer ID + Original/Simulation/Unknown + evidence + model/revision |
| Calibration | iOS-first approved slice, v0.4 | saved locked Twin answer ID, then a linked confirmed human Episode | five typed dimension diffs, human excerpts, suggested next question; Episode modeling updates traits |
| Voice Synthesis | local iOS-first approved slice, v0.3 | saved Twin answer ID + active `VOICE` profile/consent | private audio asset ID + status + model version |

## Shared rules

- IDs are opaque non-empty strings. Timestamps are RFC 3339 UTC date-time strings.
- `subject_id` identifies the modeled person and is required at sensitive boundaries.
- Real Phase 1 Capture implementations must send `actor_id`, `recording_consent_id`, and `idempotency_key`. They remain optional in the v0.1 envelope only so existing fixtures and prototypes stay readable; absence at a real upload boundary is an application-level validation error.
- Processing states are `uploaded`, `transcribing`, `extracting`, `modeling`, `ready`, or `failed`.
- `trace_id` is an optional infrastructure correlation identifier on Processing Status. Backend generates and propagates it, AI Core preserves it in execution context and logs, and Android must not depend on it as a product identifier.
- `episode_id` remains the durable product-domain identifier. `job_id` is deliberately not exposed in Contract v0.1.1.
- Evidence includes a source reference, source type, and optional excerpt and confidence.
- Evidence source types distinguish `SUBJECT`, `THIRD_PARTY`, `AI_INFERENCE`, `OBJECTIVE`, and `CALIBRATION` material. Optional span offsets locate transcript evidence; a correction instead points to its audit record.
- Each Memory item carries its kind, content, source type, one or more evidence identifiers, confidence, and model/prompt/schema versions. In v0.2 graph and persona proposals are typed and evidence-linked.
- In v0.3, Twin `response_type` is `ORIGINAL` only for a verified SUBJECT transcript span, `SIMULATION` for labeled inference with evidence, and `UNKNOWN` when evidence is insufficient or contradictory. v0.2's shallow two-value shape remains for old consumers.
- Voice requests require an explicit granted voice-consent reference. Recording consent alone is insufficient.

## Approved v0.1.1 clarification

Issue #16 approved one minimum additive change: Processing Status may include an optional non-empty `trace_id`. Existing payloads remain valid, no data migration is required, and `trace_id` must not be overloaded as an Episode or Job identifier. Backend owns generation at the request boundary and propagation across workers; AI Core must not generate or mutate `episode_id`; Android may ignore `trace_id`.

## Approved v0.1.2 Phase 1 boundary correction

Issue #36 corrected the boundary before module implementations existed. It adds the missing objective evidence type, typed Memory items, optional Capture actor/consent/idempotency fields, AI trace propagation, and an Android-readable Episode Result. The new envelope fields are additive; the Memory item definition deliberately becomes strict so Backend and AI Core cannot freeze incompatible private shapes.

## Known open contract gaps

These are recorded rather than silently resolved. None may be changed without an Issue and Product and Integration Owner approval, because the schema sets `additionalProperties: false` and every one of these is a breaking change.

- **`job_id` visibility.** A Processing Job is distinct from an Episode and from an execution trace, but Phase 1 does not require Android to inspect job identity or retry history. Keep it internal to Backend until a concrete cross-module consumer requires a versioned proposal.
- **Twin and Calibration shapes are shallow.** The v0.2 graph and person-trait proposals are typed. Twin, `dimension_diffs`, `model_updates`, and `followup_questions` remain later-phase work and require a versioned proposal.
- **Voice Synthesis provider metadata is open-ended.** `provider_metadata` intentionally allows any properties so no provider is presumed; treat its contents as non-normative.

## Realtime Voice v0.6 (2026-10-13)

The [approved LiveKit/CosyVoice proposal](../../docs/architecture/realtime-twin-voice-contract-proposal.md) adds separately consented real-time profile, capabilities, call request and short-lived room ticket shapes in `schemas/integration-contract-v0.6.schema.json`. v0.1–v0.5 remain unchanged. Provider credentials/voice IDs are never mobile payloads. A ticket is ephemeral session data, not a saved login. Existing v0.5 multi-turn conversations remain the source of question/answer provenance; call audio does not automatically become evidence.

## Personal learning v0.9 (2026-10-14)

The direct Product / Integration Owner request is recorded in [the personal-learning proposal](../../docs/architecture/twin-personal-learning-proposal.md). MODEL_TRAINING is a separate owner grant. v0.9 adds strict preference, verified human reference/rating and real training-result shapes; all v0.1–v0.8 shapes remain unchanged. Training remains a candidate until independent held-out human validation. Model loss, recording counts and LLM diagnoses never become personality-completion percentages.

## Recording deletion (2026-10-15)

Owner-authorized right-swipe deletion adds `DELETE /api/v1/episodes/{episode_id}` with [strict receipt](schemas/recording-deletion-v1.schema.json). Existing integration shapes stay unchanged. See [scope and semantics](../../docs/architecture/recording-swipe-deletion-2026-10-15.md).

## Owner conversation archive and deletion (2026-10-16)

The Product / Integration Owner directly requested voice and text conversation history in 我的录音, individual left-swipe deletion, and no saved guest conversations. Owner-only `GET /api/v1/subjects/{subject_id}/twin/answer-history` takes active `cloud_consent_id`, optional opaque `cursor` and `limit` (default 50, maximum 100), returning the [strict archive page](schemas/twin-answer-history-v1.schema.json). Turns sort by descending creation time and answer ID; the cursor is the last returned answer ID, scoped to the same owner and subject. Archive visibility is independent of the chat-memory retrieval switch and clear cutoff. Stale assistant content stays unavailable.

Owner-only `DELETE /api/v1/subjects/{subject_id}/twin/answers/{answer_id}` reuses the [recording deletion receipt](schemas/recording-deletion-v1.schema.json) without requiring a still-active cloud grant. It erases the selected original question and answer, derived summaries/indexes, dependent assistant snapshots and generated speech; separately saved recording/material sources remain independently manageable. Missing or foreign IDs return 404. An inaccessible content-free tombstone preserves idempotency; completed tombstones leave the archive, while storage cleanup failure exposes only a fixed retry label with optional `deletion_pending: true`. Repeating DELETE retries private cleanup. Existing contract versions remain unchanged; no database migration is needed.

## Realtime speaker display (2026-10-15)

The owner-requested green speaker name display adds optional `speaker_names` to per-turn `speaker` events, using only currently valid acoustic matches. Unknown or unavailable results carry an empty list; older events without names remain readable. No vectors or new grants are sent. See [scope](../../docs/architecture/realtime-speaker-display-2026-10-15.md) and [additive event schema](schemas/realtime-speaker-v1.schema.json).

## 国内模块化 RTC（2026-10-16）

Owner 已批准火山 RTC＋ASR／现有 Twin／TTS 重构。新 [独立 schema](schemas/volcengine-voice-v1.schema.json) 与 [授权提案](../../docs/architecture/volcengine-modular-voice-2026-10-16.md) 定义国内票据、能力、心跳和轮次打断，旧版本保留。首批默认声音；本人音色、声纹姓名与自然采集尚未迁移，对应能力为 false。

## 火山通话功能恢复 v2（2026-10-16）

Owner 追加明确要求恢复全部既有语音功能，见[批准范围](../../docs/architecture/volcengine-feature-parity-2026-10-16.md)。[独立 v2 schema](schemas/volcengine-voice-v2.schema.json) 在 `features=2` 下声明共享本人音色、声纹与自然采集；v1 保持原样。新增轻量 `POST .../calls/{id}/lease`、独立 `GET .../status`、本人音色 `/profile` 与 `/profile/preview` 别名，以及授权 call 下的 `/utterances/{turn}`、`/samples/{sample}`、`/speech/{turn}/{answer}`。音频上传为有界 16k mono WAV，个人播放为 24k mono PCM 流；只有当前有效保存答案可合成，没有任意文本入口。长期音色 ID、声纹向量不进入客户端。票据可含 `capture_enabled`，请求仍须分别提供录音、声纹、声音及云端问答许可。

## 本人音色验收与重做（2026-10-16）

Owner 在整体审核后授权修复，见[修订范围](../../docs/architecture/voice-audit-remediation-2026-10-16.md)。独立 [voice-review-v1](schemas/voice-review-v1.schema.json) 为当前 profile 增加 review 读取／确认与 retry 端点；原 JSON 形状保持不变。供应商就绪后须本人试听并接受，才可开始本人音色新通话；拒绝结束对应通话。重做只停用指定音色和复刻样本，不撤销 VOICE 许可或删除录音、记忆。UNKNOWN 语音仅使用固定服务反馈，绝不朗读未核验内容。

## 采集核对与自动累计分析（2026-10-16）

依据[本聊天的 Owner 授权](../../docs/architecture/ios-android-capture-garden-parity-2026-10-16.md)，独立 [capture-review-v1](schemas/capture-review-v1.schema.json) 的 `$defs` 定义转写核对 GET／PATCH、机器原稿与自动校对报告、可选 `cloud_analysis_consent_id`、录音／故事的 `cumulative_analysis` 及能力增量；旧 schemas 保持不变。录音列表兼容增加 `waiting_for_review: boolean`：转写任务等待本人核对时，该值为 true，既有 Episode `status` 仍可为 `transcribing`，不新增处理状态枚举；旧服务省略该字段仍可使用转写核对端点。`supplement` 沿用已有书面补充语义，不能冒充录音原话。分析须当前本人／Subject 的独立 CLOUD_TWIN 许可，结果仍是待核对候选；能力版本为 1 才请求自动分析，校对须显式回传当前 policy。无 policy／失败时保留机器稿，来源 hash、编辑区间／原文匹配、区间不重叠及自动编辑重建一致性仍由服务端补充校验，JSON Schema 不代替授权或文本溯源检查。episode／story／capability 定义是兼容字段投影，须与各端点既有字段一起校验；服务端私有回执不属于客户端上传权限。

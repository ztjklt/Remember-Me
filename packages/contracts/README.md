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

The current machine-readable schema is `schemas/integration-contract-v0.11.schema.json`; v0.1–v0.10 remain for existing consumers. Validate payloads at module boundaries. Additive optional fields may be proposed in a Pull Request; removals, renames, type changes, required-field changes, enum changes, or semantic changes require an Issue plus Product and Integration Owner approval.

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

# ASR 后自动纠错：本轮增量接口与实施边界

2026-10-15，用户明确要求增加一次 LLM API 检查，主动纠正转写错词、减少逐字核对。此文记录跨 AI Core、后端、Android 的兼容扩展；不表示 ECS 已发布。

## 流程

完整原音 → 真实 ASR → 原始机器稿（保留）→ LLM 上下文纠错 → 自动修订稿 → 最后确认 → 记忆提取／人物候选。

纠错是独立的文本处理任务，复用已配置的微信 Deepseek-v4-flash，不依赖新增供应商或训练。不是再次听音、不是记忆摘要，也不将 Twin 回答当作校对资料。模型只收到本段 ASR，不发送创作稿、测试答案或其他私人档案。

## 最小接口

- 内部 `POST /transcripts/correct`：`{transcript}` → `{draft,input_sha256,model_version,prompt_version,edits}`。模型输出局部 `before/after/category/action/reason`，服务端定位原文、重建修订稿；禁止重叠、无法定位、任意整篇重写。
- `GET /api/v1/workbench/capabilities` 增加可空 `transcript_correction_policy`。
- 上传已有 metadata 可携带该 policy。后端校验配置与来源，签发绑定账号和录音的 receipt；丢弃客户端伪造 receipt、纠错结果。Android 上传时现有确认改为“同意云端转文字，并用文字模型修正错词”。旧客户端不传该字段，继续原有流程。
- `GET /api/v1/episodes/{id}/transcript-review` 增加 `machine_transcript` 和 `automatic_correction`，只向录音所属账号、待核对阶段提供。现有 transcript 为修订草稿，旧字段语义兼容。
- `automatic_correction.status` 为 completed／failed／unavailable／too_long；completed 附 edits、依据指纹、模型／提示词版本。状态和耗时保存在 episode metadata，无数据库迁移。
- Android 将修改折叠显示，支持恢复机器稿或自动修订稿；保留一次最终“确认文字并整理”，不增加每个错词的必点审核。

## 自动修改与疑点

局部近音错词、明确断句可自动修改。姓名、数字、含义变化由模型标成疑点；程序还检查数字、否定、不确定、时序和代词的变化，触发则只保留建议。规则只拦截部分明显危险修改，不能证明所有语义正确。保留模型分类出错、漏检和不必要疑点的评测记录。

这轮仅覆盖服务器负责 ASR 的本人录音／导入／录音豆离线导入。亲友独立补记、客户端已转写上传、实时通话字幕不自动获得这一能力。实时聊天不额外串行插入纠错调用。

## 开关、失败与发布

`REMEMBER_TRANSCRIPT_CORRECTION_ENABLED=true` 且 `REMEMBER_AI_BACKEND=http` 才启用能力；默认关闭。后端和 worker 使用同一配置，先部署 AI Core 再启用。单条输入上限 12,000 字符，过长不截断、不外发此步骤，状态 too_long，保留原稿。分段长录音处理另列，不宣称已经解决。

单次纠错等待由 `REMEMBER_TRANSCRIPT_CORRECTION_TIMEOUT_SECONDS` 控制，默认 50 秒；模型端既有 45 秒预算。单次调用，不隐藏重试；失败仍进入原稿核对，不重复 ASR、不丢音频、不提前提取。工作进程原有租约续期和提交比较继续生效。原音早已持久化；若进程在 ASR 阶段崩溃，阶段重跑仍可能重新调用 ASR，这不是新增的逐子步骤持久化队列。

调用前后重新检查当前录音权限。撤权则不采用迟到修订。保留原始 ASR、自动修订版本、最终核对文字，三者不得互相冒充。旧记忆不会因开启开关自动重写；历史资料更正须走既有修订和派生失效流程。

## 验收

规则测试检查局部修改、完整保留其他内容、数字／否定／归属保护、伪造引用拒绝、模型失败、本人确认门槛、越权、撤权与旧客户端兼容。固定真实调用为十段既有 ASR 加六条正确对照文本；创作稿只用于结果分析，不进入模型。所有调用记录保留，失败不剔除。Android 编译与真实设备操作分别报告。

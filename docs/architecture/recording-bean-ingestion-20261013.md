# 录音豆 WORK_3200 接入共享核对流程

日期：2026-10-13。范围：用户本次明确授权录音豆接入；本提案记录该接入所需的最小跨模块兼容变更。既有 [Android 硬件边界](../team/01_LIUXIUXIAN_ANDROID_HARDWARE.md) 和 [共享合同](../../packages/contracts/README.md) 继续适用。

## 问题与批准范围

`WORK_3200` 已存在于 CaptureSource 以及 v0.1–v0.4 的 capture source 枚举中。本次不新增或改名枚举，不改请求/响应结构，不新增数据库字段。变更是让这个已有来源加入现有的共享转写核对能力：其转写不能跳过本人核对后直接整理记忆。

Android 上传保留 `source=WORK_3200`，不伪装成手机麦克风或普通文件导入。手机录音、文件导入与 iOS 原路径继续工作。硬件不可用时仍能用手机录音；本提案不据此宣称厂商 SDK 已完成真机下载、音频解码或标记功能验收。

## 状态与证据

1. 普通身份使用现有 `subject_id`、有效的本人 `recording_consent_id`、稳定的 `idempotency_key` 上传真实音频。云端 ASR 继续要求与当前策略匹配的明确外发确认，客户端不能伪造服务器回执。
2. 服务端转写完成后，保留原机器稿与原音；作业停在 `extract / waiting`。外部 processing 状态仍为已有的 `transcribing`；核对接口返回 `reviewing`，不增加合同状态枚举。
3. 未核对时不能执行 EXTRACT 或生成 Memory。仅当前具有权限的本人可核对，提交后保留 `transcript_reviewed_at/by`，再进入现有提取与建模流程。
4. 客户端转写仍通过既有独立接口，校验音频哈希、模型/供应商声明、外发确认并标记 `client_reported`。加入 WORK_3200 不会把客户端稿提升为已核对或已验证的原音证据。
5. 修订继续要求在核对前关联新录音，待新材料处理完成后单独确认；旧记忆不会因上传而自动被替换。校准继续先锁 Twin 回答，再绑定同 Actor/Subject 的后录制回答；本人核对且 Episode ready 后才允许比较。来源变化和授权撤回的既有失效规则不变。

## 音频格式边界

厂商回调的原始 Opus 包不能仅改扩展名、MIME 或补一个 WAV 头后作为 WAV 上传。适配器必须完成真实解码，并根据实际采样率、声道、PCM 字节数及持续时间生成标准音频容器；解码器不可用或失败时保留本机原音并报告不可上传。

本次后端对 `source=WORK_3200` 的 `audio/opus`（含 MIME 参数）明确返回 `AUDIO_INVALID`，不创建 Episode 或排队，也不在服务器自动猜测 SDK 分包格式。既有标准音频容器走原 ASR 路径。该 MIME 防线不能证明任意标称 WAV 已被真实解码；硬件适配器仍须在上传前验证实际产物，不能通过重新标注 MIME 绕过它。

## 不变的边界与验证

身份、Subject 隔离、录音/云模型/声音的独立 consent、原音保留、审核与证据归属不因硬件来源改变。没有新增 provider secret、自动授权、自动确认或第三方替本人建模的路径，也不扩展 `RECORDING_DEVICE` 的行为。

验证覆盖 WORK_3200 服务端转写等待、未核对无提取、核对提交、客户端稿、修订确认、锁定校准、其他身份/撤销 consent 拒绝与 raw Opus 拒绝；旧 ANDROID_MIC / IMPORT / IOS_MIC 用例保留。Android 用真实本地 HTTP 测试检查来源、录音 consent、云端策略、重试键及音频字节传输。模型与 SDK 测试替身不作为真实设备或真实模型验收。

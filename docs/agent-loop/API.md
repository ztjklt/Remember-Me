# 本地工作台接口 v0.5

本次用户已批准的接口提案见 `docs/architecture/agent-loop-v5-proposal.md`。
这是独立分支的新增接口；旧 v0.1–v0.4 schema 不改写。部署中的实际机器可读
请求定义从 Backend `/openapi.json` 获取；本分支尚未接入原生移动客户端。

全部接口使用服务端验证的 Bearer 身份；任何 body 中的角色声明均不能授予权限。
`/api/v1/workbench/spaces` 返回当前 Actor、可进入的 Subject 及 owner/reader 角色。
以下 `S` 表示 `/api/v1/workbench/subjects/{subject_id}`。

| 方法与资源 | 请求 | 主要响应与行为 |
| --- | --- | --- |
| GET S/stories | 无 | items：episode_id、状态、核对状态、原/确认转写、记忆及来源；读者仅获授权故事 |
| GET S/stories/{id}/audio | 无 | 每次鉴权后的实际音频；private,no-store；不存在公开文件 URL |
| POST S/grants | episode_id、reader_actor_id、include_audio_confirmed=true、cloud_processing_allowed | grant_id、episode_id、reader_actor_id、cloud_processing_allowed、created_at、revoked_at；仅所有者 |
| GET S/grants | 无 | 所有者看自身空间授权；读者只看给自己的授权 |
| DELETE S/grants/{id} | 无 | revoked=true；废止相关回答缓存 |
| POST S/revisions | target_memory_id、episode_id、kind、可选 time_text | revision_id、subject_id、目标、新录音、kind、status、时间文本、创建/确认时间 |
| POST S/revisions/{id}/confirm | 无 | 相同修订记录；重复确认不重复生成记忆，不重复推进版本 |
| GET S/revisions | 无 | 仅所有者可读修订历史 |
| POST S/requests | text | request_id、subject_id、actor_id、text、status、answer_episode_id、created_at |
| PATCH S/requests/{id} | status、可选 answer_episode_id | 仅所有者处理；answered 必须关联已确认且 ready 的本人空间录音；不授予阅读权 |
| GET S/requests | 无 | 所有者看收件箱；读者只看自己提交的问题，隐藏未授权回答的录音 ID |
| PATCH S/questions/{id} | status=snoozed/declined/pending | 引导问题状态；真正回答通过录音 metadata.question_id 关联 |
| GET S/portrait | 无 | views 四个证据视图、资料版本、范围与说明；不复用私人完整画像 |

修订 kind：`supplement/correction/change`。status：`pending/confirmed`。
新录音需为尚未核对的 IMPORT/IOS_MIC；关联后其提取结果先为 pending，
本人确认后才 active。correction 使目标 superseded；change 保留旧记忆，
并保留由本人提供的时间文字，不能推断精确时间。

原有 `/api/v1/episodes` 使用 multipart 的 `metadata` 字段传 JSON；
工作台 source=IMPORT。IMPORT/IOS_MIC 都在本地 STT 后等待
`PATCH /episodes/{id}/transcript-review` 的 `{transcript}`，随后才排队提取。
旧状态枚举保留；故事响应的 `waiting_for_review` 表明当前等待核对。

原有 `/api/v1/subjects/{id}/twin/answers` 请求保留 question/cloud_consent_id：
所有者用自己的 CLOUD_TWIN consent；读者用已允许云端处理的 story grant ID。
读者需要在 UI 单独确认发送问题，且检索范围只含本人已允许云端处理的故事。
原有 `/memory-search` 对读者按故事权限过滤。两个接口均在昂贵工作完成后
回查来源与权限；发生变化返回 HTTP 409 / SOURCE_CHANGED，客户端明确重试。

重要兼容变化：Consent API 禁止非所有者自授权；Episode 历史接口也按
Subject 的明确所有者过滤。旧数据库先执行所有者映射，不能靠旧 grant 认领。
读者不具备原有 person-model、校准、Voice 或修改记忆接口的所有者权限。

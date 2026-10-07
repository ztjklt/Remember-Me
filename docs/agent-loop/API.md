# 本地工作台接口 v0.5

本次用户已批准的接口提案见 `docs/architecture/agent-loop-v5-proposal.md`。
这是独立分支的新增接口；旧 v0.1–v0.4 schema 不改写。部署中的实际机器可读
请求定义从 Backend `/openapi.json` 获取；本分支正在接入原生 Android，设备验收另列。

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
新录音需为尚未核对的 IMPORT/IOS_MIC/ANDROID_MIC；关联后其提取结果先为 pending，
本人确认后才 active。correction 使目标 superseded；change 保留旧记忆，
并保留由本人提供的时间文字，不能推断精确时间。

原有 `/api/v1/episodes` 使用 multipart 的 `metadata` 字段传 JSON；
工作台 source=IMPORT。IMPORT/IOS_MIC/ANDROID_MIC 都在本地 STT 后等待
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


## 本轮融合提案 v0.6（本地分支，未修改冻结 v0.1 schema）

- 增量迁移 0009_profile_candidates / 0010_answer_source_version：人物候选与后台任务队列；从0008升级，不导入同学旧编号迁移。已在现有数据库副本验证 integrity_check=ok，再升级本机库。
- GET S/profile-candidates：owner only。items含candidate_id/domain/kind/statement/context/evidence_ids/counter_evidence_ids/evidence/source_version/scope/status/independent_episodes；jobs含任务状态与安全错误。status=pending/confirmed/rejected/stale。
- POST S/profile-candidates/refresh {cloud_consent_id}：202，持久排队；运行任务幂等，不自动反复调用云端。任务期间来源变化记为失败 SOURCE_CHANGED。
- POST S/profile-candidates/{id}/confirm 或 /reject：由所有者明确决定；依据过期返回409。仅有效confirmed进入所有者问答；读者不使用这些私人归纳。
- Android真实来源保留ANDROID_MIC。旧客户端必须读取transcript-review.state=reviewing并提交核对，否则会一直等待，不再绕过核对。
- 问答改用全部有效记忆和核对原文片段，原文不被提取摘要代替。原文片段生成稳定src_证据ID，memory_item_id可能为episode:<id>；这类引用通过episode_id回到原音，不伪装为提取记忆。
- 24000字符硬限：Backend按ready且已核对的录音全文总长检查；AI Core对唯一证据文字总长再校验。超限报错，不截断。现有8个候选上限扩至正文预算允许的数量；最终回答仍最多8个引用、微信路径200个Unicode码点。
- 部分已删除/被纠正/手动改写的共享故事：读者故事unavailable=true，transcript=null，memories=[]，完整原音404。所有者仍保留原音历史。没有自动把私人修订授权给旧读者。
- Source CAS覆盖来源、授权、修订、人物候选，云端调用期间不持有写锁。新候选不自动成为人格事实；重复的完整讲述按规范化原文去重，仅作保守观察计数，不代表语义独立验证。
- 私有AI Core增加POST /profile-proposals；正文只含materials[{evidence_id,episode_id,excerpt}]，输出候选必须通过结构及引用校验。该内部接口不直接对客户端公开。

iOS字段未移除，UI资源已引入；本轮Windows无法编译验收iOS。Android接口兼容性以实际构建及设备记录为准。

问答持久记录source_version，读取旧答案也重新核验；无法追溯版本的旧回答显示过期。人物四视图source_version只由实际返回的可见材料计算。

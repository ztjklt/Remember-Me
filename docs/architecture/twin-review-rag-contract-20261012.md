# Twin 本轮兼容接口变更

范围：本地 A01；不代表 ECS 已升级。已有 answer、response_type、来源、权限与音色规则不变。

## 回答覆盖状态

`POST /api/v1/subjects/{subject_id}/twin/answers` 与读取已保存答案增加可空字段：

- `coverage`: `complete | partial | null`。表示本次是否处理了问题各部分，不是真实性认证。正确说明未知也可算已处理该部分。
- `omitted_points`: `0..4 | null`。本次审核实际剔除的草稿要点数；不是遗漏问题数量。可能有 `partial + 0`。

历史答案或旧 AI 服务没有这些字段时返回 null，不倒填 complete。失效答案返回 stale 并清除新字段。部分答案保留独立且有据内容，正文只附一次“部分问题尚未回答。”，客户端避免重复添加；自由审阅理由不进入产品页面。

本地增量迁移 `0021_twin_review_summary` 在 `persona_answer_contexts` 加 JSON `{}`；旧答案和来源不改写。已保存模式仍是 evidence/persona。UNKNOWN 不得携带剔除点、人物或贡献依据；失败不能变成 UNKNOWN。

## 可选本地检索

同一问答请求兼容增加 `retrieval_mode: full | local`，默认 full。Android 不增加工程设置；本轮小数据继续默认有效全文。

local 在权限过滤后调用已有中文向量与词面检索，将结果按已确认故事、人物整理、支持/反例与修订关系补齐。检索前后、模型前后均复核版本。真实解析器仅读取当前有效来源，不能恢复删除或替代的原话。

无命中与服务故障不同：有效空命中可以返回 UNKNOWN；依赖缺失/索引故障返回 RAG_UNAVAILABLE。人格已启用但本题无命中，不再误报需要开启人格功能。亲友署名补记独立按权限进入上下文，不因本人材料未命中被直接吞掉。

新增错误：RAG_RESULT_INVALID / SOURCE_CHANGED / RAG_CONTEXT_INCOMPLETE / CONTEXT_TOO_LARGE / RAG_UNAVAILABLE。未实现外部 HTTP provider；不能声称填写队友 URL 即已联通。具体字段与未解决项见 [RAG 分层合同](rag-memory-layers-20261012.md)。

## 本机依赖

本轮发现 A01 Python 环境没有安装项目现有 retrieval extra，实际 local 请求失败。补装 `sentence-transformers>=3,<6` 与 `torch>=2,<3`；使用既有 BAAI/bge-small-zh-v1.5 固定 revision 的缓存。A01 启动器只在自己的子进程设 HF_HUB_OFFLINE=1 与 OMP_NUM_THREADS=1，避免模型加载隐式联网及占满 CPU。不修改 ECS 的环境，不将“安装成功”当作真实检索通过。

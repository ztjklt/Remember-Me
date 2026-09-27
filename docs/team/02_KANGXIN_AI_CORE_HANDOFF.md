# AI Core Phase 1 交接方案

> 2026-09-26 执行规则：本文的固定 Owner、旧队列和验收交接安排是历史记录，已由[两条客户端主线与按需小 Issue 的交付模式](00_TEAM_OWNERSHIP.md)取代。张天霁主推 iOS，刘修贤主推 Android；康欣和王昊宇仅承接新建且明确指派的小 Issue，不继续执行关闭的 #56 全阶段队列。已有实现、音频素材与 PR #69 保留供两条主线按需复用；保留不等于自动合并或重新激活旧任务。CI/他人审查不是强制合并门槛，共享 Contract 和真实产品验收边界仍需遵守。

> 2026-09-25 阶段更新：新增[中文合成音频→原始 ASR→AI Core fixture 的评估包](../../services/ai-core/evaluations/zh-life-review-v1/README.md)，用于 #56 的真实输入准备。12 段音频已跑本地识别，原始文本进入 `/process`；真实 Provider、获授权真人录音和真机 Golden Path **仍未验收**。本更新不改下面的 Phase 1 责任边界，也不启动 Phase 2–4。

> Owner: 康欣（`centraler`）
> Scope: Phase 1 Golden Path，覆盖 Issue #4、#2、#5 的 AI Core 最小闭环。
> Branch: `feature/ai-core-phase1`；主题提交：`3c93231`、`096dbe4`、`bd6424c`、`4935b37`、`de971f1`、`7e168a3`
> 2026-09-22 更新：本地 AI Core `0.2.0`；详见 [第二轮审查与优化记录](02_KANGXIN_AI_CORE_V2_REVIEW.md)。上面的提交是第一版历史基线。

## 1. 这部分负责什么

AI Core 负责把 Backend 传入的 Episode transcript 转成可持久化、可追溯的
Memory 输出：

```text
Episode / Transcript
        ↓
MemoryExtractor
        ↓
Provider（Fixture 或 OpenAI-compatible HTTP）
        ↓
Pydantic Contract 解析
        ↓
Evidence / Provenance 校验
        ↓
结构化 AICoreOutput
```

AI Core 不负责：

- 用户登录、Actor/Subject 权限和 Consent；
- Episode、Job、数据库、Object Store 的持久化；
- Worker 租约、重试和处理状态；
- Android 页面和音频上传；
- Phase 2 的 Graph、Persona、Twin；
- Phase 3 的 Voice、Calibration；
- 把 Jev 直接当成 Transcript → Memory 的生成模型。

Backend 仍然是 Episode、Job、重试和用户可见失败状态的唯一负责人。

## 2. 当前已经完成的内容

### Contract 和 Fixtures

- `services/ai-core/app/contracts.py`：严格的 `AICoreInput`、`AICoreOutput`、
  `MemoryItem`、`Evidence` Pydantic 镜像。
- 所有 Contract Model 都拒绝未知字段。
- `services/ai-core/fixtures/`：happy、messy、adversarial 三个固定输入。
- Fixtures 不包含 API Key，也不包含预设模型输出。

### Provenance 校验

- Evidence ID 必须唯一。
- Memory 引用的每个 `evidence_id` 必须真实存在。
- transcript span 必须在原文范围内。
- Phase 1 的所有 Evidence 都必须给出 span、excerpt 和当前 Episode 引用；没有 span 不能跳过核验。
- `excerpt` 必须等于 `transcript[start:end]`。
- 当前 Episode 的 transcript 证据使用：
  `episode:<episode_id>#span:<start>-<end>`。
- Phase 1 的 `graph_updates` 和 `persona_updates` 必须为空数组。
- 每个 Memory 必须包含 `source_type`、`evidence_ids`、`confidence`、
  `model_version`、`prompt_version`、`schema_version`。
- 推断/改写使用 `AI_INFERENCE`；直接来源标签要求逐字引用且与 Evidence 标签一致。该检查不证明说话人身份或推断内容正确。
- model/prompt/schema 版本由服务写入，不接受模型自报版本；日期需带时区并输出为 UTC。

### Provider 和 Extractor

- `FixtureProvider`：仅供 development/test，确定性、无网络、保守处理不确定文本。
- `OpenAICompatibleProvider`：只负责 HTTP 请求和响应 JSON 读取，不把供应商名称写进领域层。
- `MemoryExtractor`：Provider 输出必须先通过 Pydantic 和 provenance 校验，才能返回给 Backend。
- Provider 超时、连接失败、坏 JSON 和错误结构都有稳定内部错误码。

### HTTP 接口

- `GET /health`：只表示服务进程存活，不代表外部模型可用。
- `POST /process`：`AICoreInput → AICoreOutput`。
- AI Core 不修改或生成 `episode_id`，不返回 `job_id`，不写数据库。

## 3. 本地运行和验证

在 `services/ai-core` 目录执行：

```powershell
uv run pytest -q
```

第二轮本地结果：113 个 AI Core 测试通过，共享 Contract 7 个测试通过；独立 wheel 布局检查通过。测试客户端依赖产生 2 条上游弃用警告。远端 CI 未运行。

启动确定性本地服务：

```powershell
$env:REMEMBER_ENVIRONMENT = "development"
$env:AI_PROVIDER = "fixture"
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8100 --log-config app/logging.json
```

另开一个 PowerShell 请求：

```powershell
$body = @{
  episode_id = "episode-local-1"
  subject_id = "subject-local-1"
  transcript = "我喜欢周末去爬山。"
  existing_model_version = "model-v0"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8100/process `
  -ContentType "application/json" `
  -Body $body
```

真实 OpenAI-compatible Provider 需要通过进程环境变量配置：

```text
AI_PROVIDER=openai_compatible
AI_BASE_URL=<provider-base-url>
AI_MODEL=<provider-model>
AI_API_KEY=<secret>
AI_TIMEOUT_SECONDS=30
AI_MODEL_VERSION=<model-version>
AI_PROMPT_VERSION=memory-extractor-v2
AI_SCHEMA_VERSION=integration-contract-v0.1.2
AI_MAX_CONCURRENT_REQUESTS=4
AI_MAX_REQUEST_BYTES=1048576
AI_MAX_RESPONSE_BYTES=1048576
```

API Key 只能存在 AI Core 运行环境，不得写入 Android、Fixtures、日志、README 或 Git。

## 4. 接口约定

### 请求

```json
{
  "episode_id": "episode-123",
  "subject_id": "subject-123",
  "transcript": "我喜欢周末去爬山。",
  "existing_model_version": "model-v0",
  "trace_id": "trace-123"
}
```

### 成功响应

```json
{
  "memory_items": [
    {
      "memory_type": "PREFERENCE",
      "content": "我喜欢周末去爬山。",
      "source_type": "AI_INFERENCE",
      "evidence_ids": ["episode-123:evidence:0"],
      "confidence": 0.85,
      "model_version": "fixture-ai-v2",
      "prompt_version": "memory-extractor-v2",
      "schema_version": "integration-contract-v0.1.2"
    }
  ],
  "graph_updates": [],
  "persona_updates": [],
  "evidence": [
    {
      "evidence_id": "episode-123:evidence:0",
      "source_type": "SUBJECT",
      "source_ref": "episode:episode-123#span:0-9",
      "excerpt": "我喜欢周末去爬山。",
      "span_start": 0,
      "span_end": 9,
      "confidence": 0.95
    }
  ],
  "model_version": "fixture-ai-v2"
}
```

`memory_items[].source_type` 表示模型对内容的归类；原始说话内容的证据仍然是
`evidence[].source_type = SUBJECT`，不能把模型推断伪装成 Subject 原话。

## 5. 错误处理

| HTTP 状态 | `error_code` | 含义 | Backend 建议 |
| --- | --- | --- | --- |
| 413 | 安全的 `detail` | 请求 JSON 超过配置字节上限 | 不原样重试，协调录音长度/容量 |
| 422 | 脱敏的 validation detail | 输入缺字段或格式不符合 Contract；不回显输入 | 不重试，修正请求 |
| 503 | `AI_UNAVAILABLE` | Provider 连接失败、429/5xx 或本服务并发满额 | Backend 有界退避重试 |
| 504 | `AI_TIMEOUT` | 网络超时或 Provider 408/504 | 可按 Backend 策略重试 |
| 502 | `AI_SCHEMA_INVALID` | Provider 返回坏 JSON/坏结构 | 通常不重试，记录失败 |
| 502 | `EVIDENCE_INVALID` | Evidence 与 transcript 对不上 | 不重试，记录失败 |

错误响应只返回稳定错误码和安全消息，不返回 API Key、完整 Provider 响应或内部异常堆栈。

## 6. Backend 接入清单

Backend #39–#42 已合并到 `develop`。当前分支已同步该版本；联调时由 Backend 负责人核对：

1. 使用 `POST http://127.0.0.1:8100/process`，路径和地址通过配置覆盖。
2. 发送 `episode_id`、`subject_id`、`transcript`、`existing_model_version`，并透传 `trace_id`。
3. 在调用 AI Core 前先持久化 Episode；AI Core 失败不能删除原始 Episode。
4. Backend 自己负责 Job 状态、重试、幂等和最终结果持久化。
5. 不把 `episode_id`、`job_id` 或数据库写入逻辑塞进 AI Core。
6. 为 413、422、502、503、504 增加跨模块错误映射测试，明确哪些错误可重试。当前 `services/backend/app/ai_core.py` 把 AI Core 的所有 HTTP 4xx/5xx 都映射成不可重试的 `AI_FAILED`，因此 AI Core 的暂时性 503/504 会直接耗尽本次处理机会；需由 Backend 负责人将暂时性错误映射到可重试分类并验证任务状态。AI Core 自身不自动重试，避免重复付费。
7. 用真实 STT 文本和真实 Provider 再跑一次；Fixture 只能证明链路和 Contract，不满足 Phase 1 发布验收。
8. 服务仅放在 Backend 可访问的内部网络。Actor/Subject/Consent 必须在 Backend 调用前核验；本接口没有用户身份鉴权或独立服务鉴权。
9. span 是 Unicode 码点索引、右端不含；涉及 emoji 时不要直接当作 Kotlin/JavaScript 的 UTF-16 下标。
10. 本轮 `subject_context`、`subject_id`、`trace_id` 不发送给模型；trace 仅用于本地结构化日志，context 暂无可验证证据解析器。

## 7. 当前未完成项和风险

- 当前分支已合并包含 Backend #39–#42 的 `develop`；AI Core 提交只修改本模块、对应文档和 CI。Backend 的 HTTP 错误映射仍需其负责人修正。
- 真实 Provider 还没有在本地验收，OpenAI-compatible Adapter 只完成了协议级测试。
- FixtureProvider 是离线验证器，不是生产语义模型。
- 原文逐字匹配只证明“引用存在”，不证明推断成立或说话人身份准确；真实中文质量、提示注入和多说话人归属需单独评测。
- 并发上限按进程计算；HTTP 超时是网络操作超时。全局配额、慢客户端防护、任务总期限由部署层/Backend 负责。
- Graph、Persona、Twin、Voice、Calibration 仍然是后续阶段，不能借此交接文档提前冻结。
- Jev 如果只提供 Noul/Choice/Score 决策接口，不能直接替代当前的结构化 Transcript → Memory 生成器；它最多作为后续路由、筛选或评分组件，需另行验证。

## 8. 交接完成标准

接手人应能完成以下事项：

- 在 `services/ai-core` 执行 `uv run pytest -q`；
- 用 fixture 模式启动 `/health` 和 `/process`；
- 看到输出中每个 Memory 都能通过 `evidence_ids` 找到原文证据；
- 知道 AI Core 不负责数据库和 Episode 状态；
- 补跑 Backend 到 AI Core 的跨服务联调和真实 Provider 验收；
- 不把 Phase 2–4 的 Graph、Twin、Voice、Legacy 代码提前放进 Phase 1。

# 康欣 AI Core 0.2.0：第二轮审查与优化记录

日期：2026-09-22。审查基线：本地 `feature/ai-core-phase1` 的 `efcb200`。
范围：`services/ai-core`、相应测试/交接文档和 AI Core CI。
本轮没有修改 Backend、Android 或 `packages/contracts`，没有合并、推送或发布。

## 这轮为什么值得做

第一版的 44 个测试通过，但没有覆盖“模型不给原文位置”“慢请求拖住服务”
“供应商限流”“校验错误回显私人转写”等边界。本轮先用失败用例复现，再修复。
新增检查既针对漏洞，也覆盖实际 HTTP adapter 和可交付安装包。

## 发现与处理

| 优先级 | 第一版问题 | 0.2.0 行为 | 验证位置 |
| --- | --- | --- | --- |
| P1 | Evidence 省略两个 span 时直接跳过校验，可接受其他 Episode 或编造网址 | 本阶段仅解析当前 transcript；强制核对 span、excerpt、source_ref | `test_validation.py`、`test_http_integration.py` |
| P1 | 模型改写内容可以挂上 SUBJECT 标签，第三方 Evidence 也能被改标为主体原话 | 直接来源 Memory 必须逐字引用、来源一致；改写使用 AI_INFERENCE | `test_validation.py` |
| P1 | `async` 路由直接执行同步 HTTP 请求，慢模型阻塞事件循环 | 同步路由交给线程池，独立健康检查；每进程限额，满额返回503 | `test_runtime.py` 的真实并发场景 |
| P1 | FastAPI 缺字段错误默认带上完整请求 input | 422 只返回安全字段位置和错误类型，隐藏值和未知键名 | `test_runtime.py` |
| P2 | Provider 严格 JSON Schema 中存在非 required 字段和开放 object | 供应商层投影成 required/nullable + closed objects；共享 Contract 不变 | `test_providers.py` |
| P2 | 429 当作坏模型输出；截断/拒绝响应可能被接收 | 限流503、超时504；非 stop completion、refusal、坏结构拒绝 | `test_providers.py` |
| P2 | 无请求/上游响应大小限制、无执行并发限制 | 默认请求/解码响应各1MiB、4个执行槽；真实分块计数，不只信 Content-Length | `test_runtime.py`、流式响应测试 |
| P2 | 版本全由模型自报；真实模型可继承 fixture 版本 | 服务写入部署版本；真实配置必须显式指定模型和版本；拒绝不匹配的 prompt/schema 标签 | `test_extractor.py`、`test_config.py` |
| P2 | 布尔值/数字字符串被强制转换成置信度；日期可无时区/用 Unix 数值 | JSON 数字类型、RFC3339 带时区日期；统一 UTC | `test_contract_shapes.py` |
| P2 | 全部 subject_context、主体标识、trace 发给供应商 | 当前只传 episode_id 和 transcript；其余留在本地 | `test_providers.py` |
| P2 | API Key 在 Settings 的 repr/JSON 中明文出现；连接池无退出清理 | SecretStr 隐藏 Key；服务关闭自己创建的 Client | `test_config.py`、`test_http_integration.py` |
| P2 | wheel 只装 app，遗漏 fixtures | fixtures 随 wheel 打包，脱离源码目录运行烟测 | `scripts/check_wheel.py` |
| 改进 | Fixture 只取第一句，整段出现“可能”就全部丢掉 | 按句保留明确内容、跳过不确定句、精确重复去重、保留否定词 | `test_extractor.py` |
| 改进 | 空白也调用模型；缺少可关联的执行日志 | 空白直接空结果；记录 trace/outcome/duration，不记录转写 | `test_extractor.py`、`test_runtime.py` |

这里的“来源一致”仅是数据一致性；模型对说话人、来源类型的判断仍需真实评估。
自动化测试不等同于真实模型语义准确率或安全认证。

## 功能效果示例（实际本地 HTTP 结果）

输入：

> 我不喜欢咖啡。也许明天会下雨。我喜欢周末爬山。我不喜欢咖啡。

第一版 Fixture：整段含“也许”，没有 Memory。
第二版 Fixture：

1. `我不喜欢咖啡。`，有对应原文 Evidence；否定词保留。
2. `我喜欢周末爬山。`，有对应原文 Evidence。

不确定句未提取，重复句只出现一次。该演示是规则型测试模拟器的行为，
不能据此宣称真实 LLM 已达到相同准确率。

## 运行与测试证据

工作目录：`services/ai-core`。

```powershell
uv run --locked pytest -q
# 113 passed, 2 warnings

uv build --wheel --offline
uv run --locked python scripts/check_wheel.py
# Wheel smoke passed: packaged fixtures, extraction and HTTP boundary

uvx ruff check --isolated --select E4,E7,E9,F app tests scripts
# All checks passed!
```

仓库根目录：`npm test --prefix packages/contracts` → 7 passed。
`packages/contracts` 没有改动，完整 HTTP 成功输出还用共享 JSON Schema 校验。

真实进程：Uvicorn `127.0.0.1:18101`，`/health` 200、`/process` 200。
热身一次后对上面示例做20次顺序调用（Windows PowerShell客户端、Fixture Provider）：
按 nearest-rank 口径，p50 2.87ms、p95 4.27ms。这个小样本只检验本机链路，
不代表真实模型延迟、并发吞吐或生产性能，且没有旧版同条件基准，不能计算提升倍数。
验证后已停止临时服务。

两条警告来自上游测试客户端：Starlette 的 httpx 兼容层、AnyIO BlockingPortal 别名弃用。
没有把关闭警告当成修复。CI 定义已加入，GitHub 上还未运行。

## 接手时需要注意的行为变化

- 服务版本0.2.0；默认 Fixture 标签 `fixture-ai-v2`；实际提示词 `memory-extractor-v2`。
- 共享 Contract 保持0.1.2，字段/枚举没有变化，没有数据库迁移。
- Phase 1 的 grounding 规则更严格：无法在当前原文中核验的 Evidence 会失败。
- 旧 `.env` 若设置了 `AI_PROMPT_VERSION=memory-extractor-v1`，需移除覆盖或更新为 v2。
- 模型版本由服务配置负责。运维需使用真实部署修订标识，不能把虚构版本填进配置。
- HTTP413是新增容量响应；422保留 detail 但去掉输入值；503增加本地满额和上游429场景。
- 没有自动重试，没有偷偷降级为 Fixture。Backend 应对503/504做有界退避，保留原始 Episode。
- 启用 `--log-config app/logging.json` 才会按示例输出 INFO 级 trace日志。
- 1MiB是JSON字节上限，不是token上限。不同模型上下文窗口仍需真实适配验证。

## 仍需要完成的生产验收

1. **Backend 权限与内部服务隔离**：AI Core 请求没有 Actor/Consent 字段，不具备用户级鉴权；必须只允许已核验权限的 Backend 访问。公开暴露端口仍是风险，服务鉴权/部署策略需与昊宇协调。
2. **真实供应商测试**：未提供真实模型 Key，因此尚未测试供应商对 strict schema、中文提取、延迟和限流的真实表现。HTTP Mock 只证明协议处理正确。
3. **语义和提示注入评估**：原文存在不代表推断成立。需要加入“说反话、过去与现在变化、第三方发言、引用指令、emoji、多次相同引文”的人工标注样例。Fixture 的关键词过滤不构成真实防注入保证。
4. **真正端到端链路**：真实录音 → STT → 本模块 → Backend持久化 → Android显示，由各 Owner 联调。当前不能关闭整个 Phase 1 发布门槛。
5. **容量策略**：并发限额按进程；HTTPX超时按网络操作。任务总期限、全局配额、慢客户端防护和跨Worker幂等仍属于Backend/部署层。

## 下一步开发顺序

先请 Backend 使用这份接口和错误表完成联调，再用一个已授权真实 Provider 跑中文标注集；
记录可用率、字段/证据校验通过率、人工语义准确率、p50/p95及费用。
有了这些数据后，再决定是否需要处理长转写分段或增加供应商兼容模式。
Graph、Person Model、Twin 和 Voice 继续遵守后续阶段安排。

本轮协议修正参照：[Structured Outputs 的 required/nullable 和 closed object 规则](https://developers.openai.com/api/docs/guides/structured-outputs)，
[FastAPI 同步路由与线程池执行说明](https://fastapi.tiangolo.com/async/)。

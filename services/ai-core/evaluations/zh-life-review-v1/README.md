# 中文十年口述样例：合成音频到 AI Core 的阶段性证据（2026-09-25）

状态：**供 #56 的 Phase 1 质量评估准备使用；未通过真实 Provider、真实录音或 Phase 1 Gate 验收。**本目录不是冻结的 `fixtures/phase1-v1`，不应被当作金标准或默认进入生产回归集。

## 输入来源与目录

12 段虚构人物“林岚”的单人口述，由 `mimo-v2.5-tts` 中文女声“茉莉”合成，合计 921.12 秒（15 分 21 秒）。音频文件未提交 Git；`audio_manifest.json` 记录各段生成时间、故事时间、模型、脚本与 WAV SHA-256，`audio_technical_qa.json` 只证明格式/时长/电平检查，不证明听读质量。

- `transcripts/asr_local/E01.txt`—`E12.txt`：直接从音频识别的**原始、未校对**文本；错字、繁简混用和标点均保留，不是创作原稿的副本。同名 JSON 保留识别分段与时间。
- `asr_local_manifest.json`：识别模型、修订、参数、音频校验值、逐段耗时与原始文本路径。模型为 `Systran/faster-whisper-small`、CPU/int8、中文、beam 5、VAD 开启；提示词只含人名/场景词，不含全文脚本。路径相对于本目录。
- `annotations.json`：按段记录“应提取 / 不得推断 / 候选证据原句”。候选原句来自**创作原稿**，不能直接当作 ASR 文本的证据 span。
- `fixture_process_summary.json`：将每段原始 ASR 文本 `strip()` 后送入实际 AI Core `POST /process`、`AI_PROVIDER=fixture` 的逐段结果摘要。完整 AI Core JSON 输出仅留在本地评审包，未纳入本 PR；识别分段时间在本目录同名 JSON 中。

所有人物、内容、ID 均为虚构；没有 API Key、真人语音或个人隐私数据。音频二进制目前只在本地，需通过团队认可的渠道另行交付；不应因本评估包而把 WAV 或压缩音频直接加入 Git。

## 已实际完成的验证

| 环节 | 观察结果 | 不能据此宣称 |
| --- | --- | --- |
| 本地 STT | 12/12 WAV 产生原始中文 ASR 文本；纯推理合计 135.81 秒 | 不等于 Backend #64 的已认证 HTTP STT 端点；未人工听读签收 |
| AI Core fixture HTTP | 12/12 `POST /process` 为 200；144 Memory、144 Evidence | `fixture-ai-v2` 不是真实 LLM；毫秒级本地延迟不能代表真实模型 |
| Evidence 位置 | 144/144 的 `excerpt == 实际提交文本[span_start:span_end]`，`source_ref` 指向对应本地 Episode ID | 文本位置正确不证明提取内容或说话人归属正确 |
| 类型分布 | 138 EVENT、6 PREFERENCE，PERSON / RELATIONSHIP / VALUE / EMOTION 均为 0 | 不能声称人物模型或关系/情绪提取已完成 |

本地试跑使用 AI Core 提交 `6ef7d559cac42cf97ed8c585ecaf65a7da5c1ea2`；输出版本为 `fixture-ai-v2`、`memory-extractor-v2`、`integration-contract-v0.1.2`。本评估分支从已合并 #51 的 `develop` 建立；没有改变 AI Core 实现或共享 Contract。原始试跑完整记录见本 PR 描述及 #56 状态更新。

### 在本目录复核 fixture HTTP 边界

在 `services/ai-core` 启动开发服务（单独一个 PowerShell 窗口）：

```powershell
$env:REMEMBER_ENVIRONMENT = 'development'
$env:AI_PROVIDER = 'fixture'
uv run --locked --offline uvicorn app.main:app --host 127.0.0.1 --port 8100
```

再从同一目录发送一段原始 ASR 文本；每次运行的响应 ID 和毫秒级耗时可变，不要把这个命令的成功解释为真实模型验收：

```powershell
$transcript = (Get-Content -LiteralPath 'evaluations/zh-life-review-v1/transcripts/asr_local/E03.txt' -Raw -Encoding utf8).Trim()
$body = @{ episode_id = 'demo-E03-local-asr'; subject_id = 'fictional-linlan-001'; transcript = $transcript; existing_model_version = 'synthetic-eval-v0' } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8100/process' -ContentType 'application/json' -Body $body
$result | Select-Object model_version, memory_items, evidence
```

基础测试命令：`cd services/ai-core && uv run --locked --offline pytest -q`；共享契约：`cd packages/contracts && npm test`。本次在 `develop` 基线分别得到 **119 passed（2 条上游弃用警告）**、**7 passed**；这些仍是离线/契约测试。

## 质量缺陷与下一轮评估

- E01 出现“小雨→小宇”“阅览室→越岚市”；E11/E12 出现“阿琴→阿晴/阿秦”。若直接提取，会形成错误人物实体或关系。
- `annotations.json` 的 24 条候选原稿证据，只有 10 条在原始 ASR 里逐字命中；这不是字错误率。标点、繁简、数字写法及识别错误都会影响逐字匹配。**任何证据位置均须以最终实际传给 AI Core 的文本重新计算。**
- 优先听读 E03（母亲的话）、E04（阿琴与林岚的不同喜好）、E09（未核实的旅行日期）、E11（第三方评价）、E12（不应推断的未来安排）。E02/E08 的跨 Episode 变化是后续 Person Model 评估，不因本 PR 被视为 Phase 1 已实现。
- 人工校订时保留本目录的原始 ASR 不变，另存带版本的最终输入和修订理由；团队应逐段听音频核对姓名、年份、否定、引述和漏读，而不是只拿原稿覆盖识别结果。

## 交接边界与阻塞

1. **AI Core Owner `@centraler`**：完成转录听读/版本记录；待 #66 交付可用真实 Provider 配置及脱敏运行证据后，使用现有 adapter 测 #2/#5 的六类 Memory、错误拒绝、Episode/span、`source_type`、confidence、model/prompt/schema 版本，并把失败案例写入独立 PR。AI Core 不负责 Backend 重试。
2. **Integration Owner `@ztjklt`**：#66 认证真实 OpenAI-compatible `/process` 路径所需模型端点；#64 认证符合 Backend raw-audio POST 协议的真实 STT 服务。#4 已有合并的 #45/#51 与契约测试证据，仍需 Product/Integration Owner 确认后关闭。2026-09-25 的本地 Ollama 完整 `/process` 尝试返回 504，见 #56 评论；它不是可用 Provider 的证明。
3. **Backend/Android**：#47/#48 与 #7 各自 Owner 联调同一个正式 Episode ID、持久化结果、失败映射和真机展示。合成音频可帮助开发联调，但 #21 的 Phase 1 Gate 仍要求真实设备、获授权录音、真实 STT、真实模型和最终 Android Memory。

Contract 影响：无。迁移：无。隐私：虚构合成数据、无密钥；音频未进 Git。回滚：移除本评估目录及交接文档中的对应链接即可，不影响服务行为。

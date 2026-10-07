# 手机独立运行 Agent：Memex 源码评审与迁移提案

日期：2026-10-06；实施授权更新：2026-10-07。
用户明确要求按本提案实施手机独立模式，但排除多 Agent 协作。该指令授权本文的 BYOK 本地存储边界例外；
以下评审保留原提案背景。实现采用一个 Agent 的有序操作，不增加子 Agent、委派或内容压缩。
共享 Backend 契约和既有服务端 Memory 保持原实现，客户端新模式通过内部适配器增量接入。

当前实现与验收进展见 [Android 本地验证](../verification/ANDROID_LOCAL_2026_10_07.md)。下文的“待批准”“当前 APK”均描述 2026-10-06 评审时点。

## 结论与边界

用户希望手机录音、直接调用自己配置的 ASR/LLM、完成理解/问答/校正，不依赖电脑常开。
技术上可行，但要把持久化、任务执行和 Agent 编排一起移到手机，单独添加 API Key 输入框不够。
手机负责业务编排，模型推理由供应商提供，仍需要网络；这不等于离线运行大模型。

当前 [AGENTS.md](../../AGENTS.md) 明确要求 “Android must ... hold no provider secrets”，
PRD summary 也规定密钥留在服务端。BYOK（用户自带 Key）本地模式会改变这个边界。
实施前需由 Product/Integration Owner 明确调整该约束和本地数据边界；本提案不默认为批准。
若维持原约束，最小改动路线是将既有 Backend/AI Core/worker 部署到常在线服务器。
对于用户提出的长期手机独立使用目标，建议选择本地模式；现有 Backend 可保留用于调试。

## 评审范围及源码版本

只读检查 [memex-lab/memex](https://github.com/memex-lab/memex) 的提交
`4401c41603dcbf603b8e215ba4d7370b7773c954`，未运行该项目或复制其实现。
下列链接固定到这次实际读取的版本；源码优先于 README 中的产品描述。
该仓库使用 GPL-3.0；本提案借鉴设计，不引入其 Dart 代码或依赖。

### 本地运行的基础是完整业务运行时

- [AppDatabase](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/db/app_database.dart)：Drift/SQLite 存放任务、索引和状态，原始资料及卡片还使用本地文件，不能概括为“只存 SQLite”。
- [UserStorage](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/utils/user_storage.dart)：保存配置，并按模型协议构造客户端。`buildLLMResources()` 的 Chat Completions 分支将用户填写的 Key/Base URL 交给客户端。
- [SpeechTranscriptionService](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/data/services/speech_transcription_service.dart)：可选择本地语音模型或云端音频调用。本次云端实现使用 chatAgent 的配置，不能因此假定任意文字模型都能识别音频。Remember Me 应继续区分 Qwen ASR 和文字 LLM 两套配置。

因此“本地优先”描述的是数据和业务所在位置，不代表远程推理时录音、原文或问题不会发给供应商。

### 多 Agent 通过明确任务和权限协作

- [SuperAgent](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/agent/super_agent/super_agent.dart)：主对话入口装配模型、技能、文件工具和上下文；Quick Query 使用只读工具白名单，排除写入记忆的技能。
- [委派工具](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/agent/super_agent/subagent/delegate_subagent_tool.dart)：子任务只能选择代码中注册的预设（如卡片、PKM、研究），权限和技能不是模型任意生成。多个工具调用可以并行，父 Agent 汇总结果。
- [子 Agent](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/agent/super_agent/subagent/super_agent_child.dart)：独立状态、有限上下文和输出结构；提示词还要求不递归委派、不写长期记忆。应区分代码权限限制与提示词约束，后者不能单独充当安全边界。
- [LocalTaskExecutor](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/data/services/local_task_executor.dart)：持久化任务、依赖、重试、按用户并发控制和过期任务恢复。这个执行层比 Agent 的数量更值得迁移。

**文档与代码存在版本差异。** `docs/core_agent_design.md` 描述输入事件依次触发 analyze_assets、
card_agent、pkm_agent 等旧流水线。当前 [MemexRouter](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/data/repositories/memex_router.dart)
注明 Capture 已进入 SuperAgent；事件订阅主要处理后续评论和角色任务，并注册
`super_agent_chat_turn_task`。不能按那份旧图直接复制固定多 Agent 架构。

### Memory 需要区分原文、长期属性与运行上下文

- [MemorySyncService](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/data/services/memory_sync_service.dart)：持久保存待处理 fact ID，默认累计 5 条再触发，当前批次从 `card.fact` 读取材料。该阈值适合后台整理，但不能照搬到我们要求“一段录音后立即理解”的交互。
- [MemoryAgent](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/agent/memory_agent/memory_agent.dart)：从记录中筛选持久属性，排除任务和短暂状态，再通过工具写入。不是每句输入都必须生成长期记忆。
- [MemoryManagement](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/agent/memory/memory_management.dart)：`memory.json` 使用 recent_buffer 和 archived_memory；缓冲超过默认 10 条后合并摘要。这属于长期属性整合，另有 Agent 会话上下文压缩器，两者不应混为一谈。

Remember Me 的原文是可追溯证据，用户校正也需独立来源、revision 和失效关系。
Memex 这条 appendMemories 路径主要保存文本、source_agent 和时间，不能直接替代我们的证据模型。
按用户前述范围，本轮不改 Memory，也不引入缓冲摘要或上下文压缩。

### 不应照搬的实现细节

`UserStorage.saveLLMConfigs()` 将配置 JSON 写入 SharedPreferences；
[`LLMConfig.toJson()`](https://github.com/memex-lab/memex/blob/4401c41603dcbf603b8e215ba4d7370b7773c954/lib/domain/models/llm_config.dart) 包含 `apiKey`。
这条路径没有将 Key 单独放入 KeyStore 的处理。我们的本地模式应采用 Android Keystore 管理加密密钥，
以加密形式保存用户输入的供应商 Key，并排除备份、日志和导出；APK 中不预置团队密钥。
文件写入、运行时 JS、任意工具扩展、伴侣角色和知识库卡片不是本轮最小循环的必要能力。

## Remember Me 的迁移设计

保留 Kotlin/Compose，逐步替换 Repository 后的执行方式，不迁移成 Flutter。
以下是待批准的内部设计，不是新的共享 API 契约：

```text
Compose：录音原文 / 当前理解 / 问答 / 校正
  └─ Repository
      ├─ 现有远程执行模式 → Backend
      └─ 本地执行模式
          ├─ 手机文件 + 本地数据库：原文、理解版本、问答、校正、任务
          ├─ 持久任务编排器：转写 → 理解；回答 → 保存回答 → 校正更新
          ├─ ASR Adapter → 用户配置的语音 API
          └─ LLM Adapter → 用户配置的文字 API
```

首版使用一个文字模型、三个职责明确的 schema worker：理解、回答、校正。
“多 worker”不要求多个模型或多个服务；仅在任务可独立完成时才增加子 Agent。
录音、转写和校正先保存，再发布成功状态；问答读取授权原文、当前理解和校正证据，保留现有回答依据校验。
外部模型无权直接改数据库，结构化结果由确定性代码校验后提交。

### 稳定版本拆分

1. **本地接入与持久化**：设置页分别配置 ASR/LLM 协议、Base URL、Model、Key 并测试连接；
   本地自动生成 Actor/Subject 等内部标识，用户只确认录音/云端处理同意。Room/SQLite 和应用私有文件
   保存原始录音、转写、同意记录及任务；现有电脑数据保持原样，导入作为明确的独立操作。
2. **手机完成同一循环**：将已有理解/问答/校正的语义和验证样例迁移到本地执行器。
   用户纠正“林晨”为“林宸”（合成样例）时新增校正证据和有效理解，保留原始转写；只替换错误姓名，
   不应丢失学校、年级或研究方向。回答和校正绑定同一 question/revision，失败允许重试且不重复写入。
3. **恢复与真机验收**：任务保存阶段、重试次数和错误；手机进程退出后恢复，避免同一个 Subject 并发写入。
   后台执行按 Android 生命周期处理，不能假定协程在锁屏或进程终止后继续存在。
   关掉电脑后验收真实录音、ASR、理解、队友人数/专业问答、姓名校正、重启读回及断网失败。

无压缩阶段若全部授权材料超出模型上下文，应明确报告容量限制，不能静默截断证据后假装完整回答。
首版完成标准是手机独立跑通并保留来源与失败状态；不是 Agent 数量、界面里多一个 Key 输入框，
也不是仅通过固定 fixture 测试。

## 本轮交付与后续决策

交付 [手机联调说明](../../apps/android/docs/PHONE_QUICKSTART.md)、补全的构建环境命令和本源码评审。
没有更改共享契约、引入依赖或复制参考项目代码。当前 APK 仍使用 Backend，Memory 算法保持原实现。
本地模式需要确认供应商 Key 的存储边界和跨模块职责后，按上面稳定版本拆分实现与验收。

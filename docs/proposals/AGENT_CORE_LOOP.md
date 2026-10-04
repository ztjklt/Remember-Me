# Agent 核心闭环实验方案

2026-10-03 用户明确授权：新开分支，以现有 Android 原型为壳，开发 Review 中的核心功能并尽量跑通一轮；可安装环境。范围是实验性的 `Capture → Memory → Persona snapshot → Twin → locked Calibration → correction → Capture planner`，不声明整项 Phase 2/3 或 Voice/Legacy 已完成。

沿用现有 Backend Job、AI Core Memory Extractor、HTTP Provider 与 Android Compose。新增 `/experimental/agent/v1` 接口和 `agent-loop-v0.2-experimental` schema；已有 integration-contract-v0.1.2 不修改。方案与代码在 feature/ai-agent-core-loop 上供 Product / Integration 审阅，新契约未作为共享团队的冻结版本发布。Backend 默认关闭 REMEMBER_AGENT_ENABLED。

一个主模型通过 JSON Schema 执行 Persona、Twin 和 Calibration Worker；代码负责证据范围、Original 摘录逐字一致、持久化、版本 CAS 和失败恢复。Fixture 只证明接线，结果始终携带 fixture 模型标识，不能作为真实人格理解验收。

实验授权单独保存（不扩展旧 Consent enum）：Actor 对指定 Subject 显式同意 Cloud Twin，并声明本人单人录音；必须同时持有自己的有效 RECORDING consent。Persona 与证据严格按 Actor + Subject 分区。声明不等于身份或说话人认证，不开放第三方、共享人格、Legacy 或 Voice。旧账号系统仍是开发用 token，不据此宣称生产权限完整。

Persona revision 独立于推理模型版本。Trait 保留 domain、context、时间、支持/反例、status；新结论是候选，不按记忆数量计算人格完成度。冲突和变化保留历史。没有合格证据时 Twin 返回 INSUFFICIENT，不能编造。ORIGINAL 需要 Worker 判定直接回答并返回证据原文，代码验证精确摘录与来源。

Calibration 先保存不可变 Twin answer、其 snapshot revision、证据和摘要，后接受本人答案；Worker 的锁定请求中不存在 human_answer。比较结果分五维，不显示未经评估的“忠实度百分比”。本人答案作为 CALIBRATION 来源保存；比较与模型更新同事务提交，失败仍可重试同一锁定记录。跨请求重复提交由幂等和 CAS 控制。

撤回实验授权拒绝后续读写；原 Episode 录音授权每次外部处理前重新检查。删除某 Episode 的 Agent 使用权按证据依赖失效，保留原始 Phase 1 记录并从 Persona 排除，旧 Calibration 记录不可再读取为有效依据。

最小验证：迁移 upgrade/downgrade；真实 Backend↔AI HTTP consumer schema；两个 Episode 的全局 Evidence ID；HTTP 503 重试；Subject/Actor 隔离；证据注入拒绝；未知问题；锁定后校准、revision 增长和重放；授权撤回；Android test/assembleDebug。真实设备/STT/LLM 验收取决于可用设备和供应商配置，记录实际执行边界。

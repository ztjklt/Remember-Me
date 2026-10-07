# PR 5 — 后端来源、失败隔离与校准一致性

## What / Why
混合自述/转述按句生成带原文偏移的材料，避免转述排除整段。Memory 类型映射过滤撤除/无效同意。
Phase 1 READY 提交后才在独立事务刷新 Agent；失败写入独立内部字段，通过既有 Snapshot.limitations 展示，Android 可重试。
校准提交同时校验锁定 revision；同问题/版本的 LOCKED 请求复用，确定性主键处理并发重复插入。

## How / Testing
Backend 与 AI Core 全量 pytest；新增混合陈述及引用偏移、persona 故障保留 READY、旧锁新版本拒绝、重复请求和污染类型过滤回归。
Android 全量检查覆盖读取既有 limitations 和重试入口；设备交互未执行。

2026-10-07 验证：Backend 全量 261 passed（1455.92s，4 个既有警告）；AI Core 全量 147 passed（1.12s，2 个既有警告）。
Android `test assembleDebug assembleDebugAndroidTest lintDebug` 成功（1m15s），Debug/Release 各 43 个 JVM 测试通过。
重复请求测试覆盖顺序重试；确定性主键的并发冲突分支未做并发压力测试。来源识别仍是中文句粒度启发式，不是完整的转述语义识别。

## Contract / Rollback / Review
未修改 packages/contracts，也未增加 API 字段或端点；experimental 版本不变。
新增内部迁移 0005_agent_refresh_error（可空错误码列）。旧代码可忽略新列；降级迁移仅删除错误状态，保留录音/记忆。
混合材料的细分证据 ID 会变化，旧全段引用不再作为有效自述；需刷新理解、重新提问，原转写与历史不会被改写。
Backend/AI/Android owner 及张天霁评审。PR 草稿未发布。

# PR 4 — 本地数据完整性与恢复

## What / Why
取消理解时固化已付费转写，后续理解幂等复用；容量失败可保留任务、删除旧录音后继续。
SQLite 升级先原样保留 payload；未来不兼容版本不覆盖数据，提供原文导出与升级提示。
本轮不做 trait 连续性和检索；本地隐藏状态标签，授权原文不压缩、不截断。

## How / Testing
Android 全量命令；新增取消后原文可问答且 ASR 仅一次、真实 60,000 字符边界删除后继续、不兼容 payload 保留测试。
新增 SQLite v1→v2 无损检查及导出字段白名单设备测试，仅编译；SAF/SQLite 真机检查未执行。

## Contract / Rollback / Review
共享 schema 和 experimental 版本不变。生产 SQLite 仍 v1，预备 v1→v2 的日志兼容迁移；其他版本拒绝写入并保留副本。
回退会丢失新恢复入口；日志仍保留。恢复文件不含模型配置且位于 no-backup 目录，删除会同步清理恢复副本。
刘修贤/康欣/张天霁评审。PR 草稿未发布。

结果：Android 全量命令 BUILD SUCCESSFUL（1m23s），Debug/Release 各 43 项 JVM 测试通过；设备测试仅编译。

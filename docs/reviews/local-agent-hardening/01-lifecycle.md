# PR 1 — 页面状态与生命周期

## What / Why
录音交接进入 Activity ViewModel，重建无录音时显示返回入口；设置草稿仅在 ViewModel 内存保留。
问题、校正和恢复 ID 使用 saved state，供应商 Key 不进入 Bundle。处理完成必须对应新 revision，失败可重试。

## How / Testing
运行工作单 Android 全量命令（环境路径见 `docs/verification/ANDROID_LOCAL_2026_10_07.md`）。
新增 Activity 重建的配置/录音交接 instrumentation 测试；设备尚未连接，旋转、Don't keep activities、dumpsys 检查未执行。

## Contract / Rollback / Review
未改共享契约。回退只恢复旧页面行为，不改数据库或凭证文件；可能重新出现旋转丢草稿。
基于现有 `feature/ai-agent-core` 增量修复，不重排旧提交。Android owner 刘修贤评审；本文件是 PR 草稿，未发布。

结果：完整 Android 检查 BUILD SUCCESSFUL（1m3s），Debug/Release 各 38 项 JVM 测试通过；设备测试仅编译。

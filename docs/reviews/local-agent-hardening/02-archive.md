# PR 2 — 本地归档与问答历史

## What / Why
LocalAgentEngine 实现既有 MemoryRepository，按录音时间投影真实原文，排除撤除材料；Home/归档使用模式对应的仓库。
过去的问答展示锁定版本、类型、校正/失效状态，恢复时显示本人校正。新请求失败保留上一次回答。
本地日志跨重启恢复历史；remote 仅列本次会话已知记录，继续使用已有按 ID 恢复端点，不新增远程列表端点。
删除未使用 UnderstandingScreen；Mock 与其 JVM 测试一同迁入 androidTest。虚构人物页面标记演示、限 Debug 快捷入口，录音页新增真实 Home 入口。

## How / Testing
执行工作单 Android 全量命令。新增回归覆盖两条归档、三次问答、失败保留回答、重启恢复校正与撤除失效。
设备未连接，Home/归档/历史的触摸验收未执行。机械删除旧页面、迁移测试单独计入 Git 范围。

## Contract / Rollback / Review
共享契约不变，内部 Gateway 可选历史能力不产生 HTTP 端点；本地日志格式兼容。
回退后历史仍在数据库但无列表入口；归档回到仅远程结果。刘修贤/康欣/张天霁评审。PR 草稿未发布。

结果：Android 全量命令 BUILD SUCCESSFUL（1m26s）；Debug/Release 各 38 项 JVM 测试通过（1 项 Mock 测试迁到设备源集，新增 1 项本地集成回归）。

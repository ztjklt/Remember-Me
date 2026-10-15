# 我的录音右滑删除 — 2026-10-15

iOS 1.12.1 / 2026101505 已覆盖安装并启动到 iPhone 15 Pro Max「黑幕」。CloudBase `remember-ios-api-043` / `2c1f602` 已上线，`/ready` 200；数据库迁移保持 `0024_voiceprint_entrust`，原环境参数和资源配置保留。期间发布凭据过期，已通过原设备的官方登录流程刷新。

「录音 → 我的录音」条目右滑露出删除，不允许整段滑动立即永久删除；轻点按钮后确认。本机原音／侧车删除；已同步来源先删除云端原音、转写和来源生成的记忆，重算图谱与人物模型，再删除手机副本。对话原话及多人录音复用各自接口。长按和 VoiceOver 同样有删除操作。

网络失败保留手机原音和条目，可重试；对象清理未完成时关闭云端读取并保留无内容的重试条目。取消处理租约，晚到结果无法重新发布。独立聊天历史不属于录音来源删除。

实际验证：
- iOS LocalRecordingTests 25 项通过；右滑、取消、只删除选中条目、重开列表的 UI 场景 1 项通过。包含账号隔离、忙碌状态、文件名边界、离线失败和清理重试回执。
- 最终 Backend 775 项通过、6 项跳过；新增 3 项覆盖来源级删除、清理失败重试与晚到 Worker CAS 回滚。
- 线上独立合成 QA：真实上传两个临时来源，跨账号删除 404、目标删除后原音和转写 404、刷新保留其他来源、幂等重试、不能重新处理通过；仅清理本次新建的两段，原 QA 来源集合保留。
- Release 构建、codesign 严格校验、覆盖安装与设备启动通过；未卸载或清空设备数据，也未在真人录音上试删。

证据（ignored build）：`recording-delete-ios-verified.xcresult`、`recording-delete-unit-final.xcresult`、`recording-delete-backend-final.xml`、`recording-delete-public-proof.json`、`recording-delete-deployment.json`、`recording-delete-install-final.log`、`recording-delete-launch.log`。

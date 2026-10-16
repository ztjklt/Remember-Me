# 多人录音自我介绍与说话人识别 — 2026-10-15

## 授权与交付范围

本人要求实现同段录音多人声纹／说话人识别，用语音自我介绍代替手动确认是谁。获批行为和新增共享契约见 [v0.10 提案](../architecture/speaker-introductions-contract-v0.10.md)。这是同段录音声学分组与自述姓名关联，未交付跨录音永久声纹档案、认证身份或分离音轨。

iOS 1.10.0 / 2026101502 已覆盖安装到「黑幕」并正常启动。入口「录音 → 我的录音 → 右上角多人录音」，支持 2/3 人提示。每人分别同意录音、云端转写和本段声音识别后，依次说“我是小王。我同意录音、云端转写和本次声音识别。”，结束后自动处理。原音／结果独立于本人 Episode、Person Model、Twin RAG 与音色训练。缺少介绍／同意、姓名冲突、无有效声学 ID 或服务返回的时间区间重叠时保留未识别。

## 实际验证

- Backend 完整回归：748 passed，6 skipped，4 warnings；包括迁移升级／降级、撤销与删除时的晚到结果、账号／人物隔离、幂等上传、用途校验和数据隔离。4 个警告是既有依赖弃用提醒。日志在后端工作树 `build/speaker-introductions/backend-verified.log`。
- Contract：34 passed，v0.9 所有定义保持一致，新增严格 v0.10 定义；日志 `build/speaker-introductions/contracts-final.log`。
- iOS：5 项单元、2 项新增 UI 加 1 项既有简明流程 UI，共 8 项通过；结果 `build/speaker-introductions/ios.xcresult`。已导出并查看自动姓名／未识别界面截图。UI 名字为隔离虚构 fixture，不作为真实 ASR 证据。
- Release 签名构建成功、codesign 严格验证通过，包与设备版本均 1.10.0 / 2026101502。设备正常启动，无测试参数。未卸载应用；安装前后 4 段既有 m4a 与其目录内共 9 个文件的大小和修改时间一致；未读取本人音频内容。元数据结果 `build/speaker-introductions/device-verification.json`。
- 真实 Paraformer 服务：33.08 秒合成双人音频，使用已接通服务的系统预设声音 longanyang / longxiaochun_v3，返回 6 段，小王／小李／小王／小李／小王／小李。后四段交替发言关联正确，无手动身份步骤。
- 失败样例保留：Mac Tingting／Meijia 两种接近的声音被合为一组，带 2 人提示也未可靠分开；冲突的两次介绍导致全部未识别。Eddy／Meijia 可分组，但特殊声音的同意句转写及切句存在损失。未将这些样例计作成功。
- 合成双人音频是工程联调；真人、嘈杂房间、同时说话、不同口音以及三人真实分组尚未实测。基于返回时间区间的重叠标记不能完整判断真实重叠说话。不能从测试数量推断人物识别准确率。

## 发布状态

后端从现用生产提交 7a44736 的专用工作树增量实现，分支 `codex/speaker-introductions-20261015`，运行时代码提交 58beb7f；源包带源码 SHA 和文件摘要，Zip 条目权限为 0644，沿用原账户、依赖适配器、机密、资源配额和已有数据。主工作区旧后端不能用于覆盖本次服务。

CloudBase036 / `ios-speaker-introductions-58beb7f` 已上线，发布任务完成；service-info、ready 200、database／object_store 与原环境配置保留均核对。CloudBase035 源码任务在镜像推送完成后仍停留创建阶段，核对镜像 tag／digest 后取消该暂存任务，按相同环境配置发布同一已构建镜像。

初次迁移核对发现默认 `serve` 启动不执行 `migrate`，迁移仍为 0021；没有将健康通过当作迁移成功。随后由 Alembic 0021→0022 生成 PostgreSQL SQL，通过 CLI 在原 schema 内事务执行并核对新 head；既有 Episode／Memory／Twin answer／Voice profile／Consent 数量一致。安全摘要在后端工作树 `build/speaker-migration.json`。

首轮公网 API 隔离合成检查通过：真实双人原音上传及幂等复用、按自我介绍自动关联六段发言、其他 owner 不可读、原音 SHA 一致、撤销清空报告并阻止原音访问、删除成功。摘要 `build/speaker-introductions/public-api-proof.json`。匿名拒绝和 RECORDING 许可不可代替声音识别许可另验；独立数据库核对确认合成空间 Episode／Memory／Person traits／Voice profile 均为零，全部测试许可撤销。随后发现重复撤销会把已删除记录改回 revoked；原音与报告已清除，但云端列表会重新显示已撤销条目。新增回归用例，修复终态优先级；最终上线后的复验补记如下。

本轮未替本人创建真实声纹或提交本人音色。应用删除清理的是手机和 Remember Me 的原音／报告；现用转写传输到供应商的临时副本沿用原 48 小时保留策略，不把应用访问关闭宣称为供应商立即抹除。

服务接口依据：[官方 Paraformer 文件转写与说话人分组 API](https://www.alibabacloud.com/help/en/model-studio/paraformer-recorded-speech-recognition-restful-api)。人数参数只是分组提示，不是保证；适配器未冻结为客户端直连服务。


## 修正版最终核对

CloudBase037 / `ios-speaker-introductions-4e78742` 已上线，发布任务完成，service-info 与 ready 200 再验，迁移 0022 和原环境参数再次核对。补丁在首次已验证镜像的固定 digest 上，仅覆盖 Backend app 源码，依赖、模型缓存、运行用户和启动命令保留；源包摘要、清单、0644 权限、运行时凭证扫描通过。该源包任务完成，无需再次取消或另发镜像。

首版 `58beb7f` 的后端完整回归为 748 passed；后续 `4e78742` 删除终态补丁的 Speaker／Consent **34 项定向测试通过**，没有声称完整后端测试又跑了一次。失败实证保留于 `build/speaker-introductions/deleted-state-failure.json`，定向日志 `deleted-tombstone-tests.log`。修正版公网复验同一失败记录：删除后重复撤销两次，状态仍 deleted，云端列表为空。原音 key 为空，报告为 JSON null；没有把 JSON null 当作仍含身份文字。匿名 401、普通 RECORDING 许可不能识别、Episode／Memory／Person traits／Voice profile 为零、活动授权为零全部核对通过；安全摘要 `public-cleanup-proof.json`。合成两人识别证据仍为首版公网真实服务结果，补丁仅改删除状态，不冒称又跑了真人或 RTC 测试。

后端源码已保存并推送 `codex/speaker-introductions-20261015` 分支；iOS 本轮源码、测试、签名包及设备验证在主 checkout，保留该 checkout 既有未提交工作。完整后端和 ASR 私有产物在 `/Users/jitian/.codex/worktrees/speaker-introductions/Remember Me/build/`，本次 iOS 产物在主 checkout 的 `build/speaker-introductions/`。原音、凭证和私人数据均未提交仓库。

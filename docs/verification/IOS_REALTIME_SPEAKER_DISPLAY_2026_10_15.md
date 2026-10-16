# iOS 通话声纹姓名显示：2026-10-15 保留记录

2026-10-16 用户明确要求部署，已完成后端／Worker 发布与 iOS 覆盖安装；新结果和未通过项见[统一部署记录](IOS_SPEAKER_DISPLAY_DEPLOYMENT_2026_10_16.md)。以下暂停要求及版本状态保留为当时历史。

2026-10-15 用户最新决定：“先保留这次更新，下次一起正式部署”。后续不要依据本记录自行发布、恢复登录或安装；等用户下次统一部署的要求。

## 已完成

- 通话主画面花朵下方和本轮对话详情显示绿色“声纹匹配：姓名”，适配深色模式。未知或仅自述登记显示灰色“暂未确认说话人”。识别以每轮发言后台结果为准，不宣称逐字即时识别。
- 新发言、打断、挂断和重拨清除旧姓名；识别事件必须对应当前 turn，旧事件不覆盖新一轮。换账号时清除显示。旧服务只有 message 时继续通话，不从提示文字猜姓名。
- 后端只转发当前 Subject、模板／识别许可有效且 `matched` 的姓名；不返回声纹向量。Worker 转发新增可选 `speaker_names`，空结果也发送。见 [批准增量](../architecture/realtime-speaker-display-2026-10-15.md)。没有数据库迁移或新授权用途。

## 源码和保留位置

- iOS：当前主工作区 `apps/ios/RememberMe/TwinVoiceAPI.swift`、`TwinVoiceCall.swift`、`TwinVoiceCallView.swift` 及对应测试，保留在现有未提交工作区；未把整批既有用户工作一并提交。
- Backend／Worker：`/Users/jitian/.codex/worktrees/speaker-introductions/Remember Me`，分支 `codex/voiceprint-personal-model-20261015`，实现提交 **88bd1cf**。
- 契约：独立 `packages/contracts/schemas/realtime-speaker-v1.schema.json`；既有 v0.1–v0.12 定义不变。
- 安装候选 **1.13.2 / 2026101508** 在 `build/voiceprint-device/Build/Products/Release-iphoneos/RememberMe.app`，Release 构建和 `codesign --verify --deep --strict` 通过。未安装到手机。下次和其他更新一起重新构建，避免安装过时包。
- 源码备份 `build/realtime-speaker-preserved-20261015.zip` 只含本次相关源码、契约、文档和哈希清单，不含登录信息或用户音频。

## 实际检查

- iOS `TwinVoiceCallTests` **19 passed**，包含当前／过期 turn、换人、空姓名、旧服务兼容、插话、打断、挂断和重拨。
- UI **2 passed**：匹配姓名／详情／挂断可达；极大字号未知状态。匹配用例在深色模式另跑一次通过；浅／深色姓名截图已目视检查。截图使用隔离的“小王”预览，不是真人识别。
- Backend `uv run pytest tests/test_voiceprint_person_model.py -q`：**12 passed**，2 个已有上游弃用提醒。首两次新增检查因 fixture 既有标签及未授权隐藏为404的断言预期错误失败，修正测试后全通过。
- Worker `uv run pytest tests/test_natural_capture.py -q`：**7 passed**。
- 共享 Contract `npm test`：**43 passed**。
- iOS 结果：`build/realtime-speaker-ui.xcresult`、`build/realtime-speaker-dark-ui.xcresult`；截图目录 `build/realtime-speaker-images` 和 `build/realtime-speaker-dark-images`。
- 未进行真人通话、声纹准确率或线上新姓名字段的端到端验收。

## 发布状态（按用户要求暂停）

- CloudBase 在准备阶段因 `AUTH_FAILED` 停止，没有调用更新服务；仍为原 `ios-wearable-capture-fcb7aa0` 基线。CLI 登录尝试已取消；下次部署需要恢复有效登录。
- Worker 在收到“下次一起部署”消息之前已发布为 `MWrqVD7cyBo7`；随后依照新要求成功回退到原 **twatnUv6ZbRt**。新版本的本地源码及提交保留，下次需与后端姓名字段一起部署。
- 手机“黑幕”查询为 unavailable；未安装、未卸载、未清空数据。仍使用原已安装版本。

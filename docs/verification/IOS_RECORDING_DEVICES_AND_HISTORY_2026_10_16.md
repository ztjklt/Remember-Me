# 录音页设备入口与主用户对话归档

本轮按本人直接要求实施，授权与接口范围见[方案记录](../architecture/recording-device-and-owner-history-2026-10-16.md)。改动保存在当前工作区，未发布 Backend、执行生产数据操作或覆盖安装本人手机。

## 实际行为

- 「录音」首页的「我的录音」「蓝牙连接」并排显示，设备入口从「我的」移出。
- 设备页沿用 Anker soundcore Work/D3200 实物图片；后续按本人配色反馈恢复黑色耳机，顶部只保留一个白色大背景，设备图片直接展示、无独立小框。显示真实录音豆状态、电量和当前耳机音频路线。首次耳机配对在 iPhone 系统蓝牙设置完成，页面通过系统选择器切换已配对耳机。
- 「我的录音」包含本机／云端录音、多人录音、保存的本人文字、对话原话，以及主用户的文字和语音 TwinAgent 问答。历史按时间分页读取，不依赖旧聊天检索开关。文字资料详情不显示原音播放。
- 条目左滑露出删除，轻点后确认。问答删除擦除原始问答、派生聊天缓存和合成声音，使依赖旧上下文的回答失效；独立保存的录音／资料分别管理。网络失败保留原条目；声音清理失败只显示无原文的待重试条目，重开后可继续清理。
- 游客文字、语音输入和回答不写对话数据库、历史索引、录音文件、本人记忆或训练资料。当前连续交流的上下文只保留在内存，退出／失效／服务重启后不能恢复。升级后清理旧版临时写入的游客问答。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| Backend 完整回归 `uv run pytest --tb=short --show-capture=no` | **891 passed, 6 skipped**，214.87 秒；日志 `/tmp/remember-recording-owner-archive-backend.log` |
| 最终游客不留存定向回归 | **55 passed**，14.67 秒；覆盖内存上下文、重启、旧资料清理、大于1 MB上传不落盘、识别检查点及内容日志绕过 |
| Contract `npm test` | **55 passed**；日志 `/tmp/remember-recording-bluetooth-contracts.log`；新增历史页严格 schema 另由真实 API 测试校验 |
| iOS LocalRecording / DeviceRecording / ECSConnection / GuestAccess / VolcengineVoice 单元检查 | **113 passed**；覆盖分页、特殊字符游标、删除与重试、账号／空间／模式隔离及本机索引清理 |
| 主用户录音界面检查 | **3 passed**，51.76 秒；包含并排入口、真实未连接状态、左滑取消与删除、保存文字无原音入口及旧问答详情；最终 **TEST SUCCEEDED** |
| 游客界面检查 | **2 passed**；只读花园、Twin 管理项不可见、返回主用户需密码；结果 `/tmp/remember-recording-owner-archive-verified.xcresult` |
| `git diff --check` | 通过 |

iOS 最终构建及单元／主用户 UI 命令采用 `xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe -destination 'platform=iOS Simulator,id=FB5B94AC-8CFA-41D7-B710-AD11597433FD' -derivedDataPath /tmp/remember-guest-ios -collect-test-diagnostics never CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM= ... test`，`-only-testing` 选择上表五个单元类及三个 `SimpleFlowUITests` 场景。日志 `/tmp/remember-recording-owner-archive-accepted.log`，结果 `/tmp/remember-recording-owner-archive-accepted.xcresult`。

最终截图已目视检查：[录音首页](../feature-assets/ios-recording-home-2026-10-16.png)、[安克录音豆与耳机](../feature-assets/ios-recording-bluetooth-2026-10-16.png)、[录音及主用户对话归档](../feature-assets/ios-recording-history-2026-10-16.png)。文字原话无播放器、问答详情及游客“不保存”说明也已检查，布局无截断。

同日追加配色反馈：设备区域改为固定白色大背景，移除两张图片各自的圆角小框，恢复原黑色透明耳机素材；白底区域的文字使用浅色模式配色，深色页面中也保持深色文字。定向设备 UI 检查 **1 passed / TEST SUCCEEDED**，结果 `/tmp/remember-devices-white-surface-20261016.xcresult`，日志 `/tmp/remember-devices-white-surface-20261016.log`。最新设备页截图已替换并目视确认白底、黑色设备及无独立边框。本次未改连接或归档逻辑，未重复后端回归，未安装真机。

中间构建暴露当前 SDK 声明 `ByteRTCMediaPlayer` 却未导出基类符号的问题；改为保留播放操作闭包，播放与推流继续使用 SDK 返回的局部播放器，避免链接具体类元数据。独立编译探针与最终构建验证此修正，未更换供应商。中间三个新增测试还触发了 URLProtocol 后台回调中的 Swift 6 MainActor 断言；查询解析移入 nonisolated 辅助方法后，最终48项 ECSConnectionTests 全部通过。初轮 Xcode 诊断收集停滞，测试完成后仅终止其 simctl diagnose 子进程，后续关闭额外诊断收集；测试检查本身未关闭。

## 交付边界

后端检查使用隔离资料和确定性供应商替身，不操作真人资料，不能代替安克实机绑定、耳机切换和游客麦克风自然录制。未进行生产部署或手机安装；完整历史和逐条删除需配套本轮新增接口。

游客上下文为单进程内存，多进程部署需要会话亲和性，进程切换或重启不恢复旧对话。需要供应商保留上传音频的异步 Paraformer 路径不向游客开放语音提问，可继续文字交流；同步供应商当次处理边界仍在用途说明中告知。未承诺外部供应商绝不保留请求。

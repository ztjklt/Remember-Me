# 主用户与亲友／游客双模式验证（2026-10-16）

同日追加「只有主用户记录对话，游客不做任何记录」后，游客文字／转写／回答已改为服务端进程内的有界临时上下文；不再创建 `TwinAnswer` 或聊天摘要／索引，启动清理同时删除旧版本遗留游客内容。游客会话授权元数据保留，不含问题或答案。iOS 语音提问改为内存 PCM／WAV，播放仍使用内存；初始化时继续清扫旧版本可能遗留的临时录音。

游客 multipart 上传在 RAM 中解析，避免 `UploadFile` 超过1 MB 后写临时文件。同步 relay／Groq 使用独立游客传输，跳过转写任务持久化检查点、音频压缩文件和音频摘要日志；Paraformer 异步上传会在供应商保留原音，因此游客模式暂不提供此适配器的语音提问，本人录音路径不变。服务重启后不恢复游客上下文；多进程部署需会话亲和性，旧父消息不可用时须开始新对话。

追加实现后的最终 Backend 定向检查：`cd services/backend && uv run pytest tests/test_guest_access.py --tb=short --show-capture=no`，**55 passed，14.67秒**（包含上传时释放 DB 锁、转写前重验授权的最终源码）。新增检查验证活跃期间零持久化对话／摘要／索引、重启丢失上下文、旧游客内容清理且保留本人历史、超过1 MB 的音频上传不创建 spool 文件、真实 relay／Groq adapter 绕过持久化与音频转换文件，以及保留音频的识别服务对游客关闭。使用实际 API／数据库与确定性供应商响应，不是供应商真实转写或麦克风听感验证；本段 iOS 变更由录音入口整体验证运行统一记录。

本轮由 Product / Integration Owner 明确要求实施[已确认方案](../architecture/guest-access-contract-2026-10-16.md)。实现针对当前 iOS 本人空间与共享 Backend；未修改 Android 产品流程，未发布服务、执行生产迁移或安装本人真机。

## 使用流程

1. 主用户按现有账号密码登录，可保留日常登录状态。
2. 从「记忆花园」右上角亲友图标，或「我的 → 访问模式 → 亲友开放范围」选择已核对来源。
3. 预览完整原音、全文及同段连带记忆，再确认开放。新来源默认不开放；一段包含私密、保护或未核对内容时，整段不能开放。本人音色是独立选择，仍需有效声音许可与已接受的音色。
4. 「我的 → 进入亲友／游客模式」切换；正在录音、通话或处理资料时不可切换。游客只有记忆花园与 TwinAgent，可回听开放原音、连续文字问答、录制临时语音问题及播放可用声音。
5. 访问菜单可结束本次访问或返回主用户；返回必须验证原账号密码。若旧登录已失效，重新输入原账号密码，并验证同一 Actor 与本人空间。重启保持游客模式，不恢复游客聊天。

## 已执行的验证

| 检查 | 实际结果 |
| --- | --- |
| `cd services/backend && uv run pytest --tb=short --show-capture=no` | **876 passed, 6 skipped**，123.39秒；日志 `/tmp/remember-me-guest-backend-tests.log` |
| 游客专用 API／数据库与生命周期测试 | **49 passed**；真实 HTTP 响应经 JSON Schema 与日期格式校验 |
| `cd packages/contracts && npm test` | **55 passed**；包括独立 guest-access-v1 和所有既有契约 |
| iOS `GuestAccessTests` | **10 passed**，包含花园响应晚到与后台权限回调回归 |
| iOS `ECSConnectionTests` | **39 passed**，既有连接／录音上传／聊天回归 |
| iOS `GuestAccessUITests` | **2 passed**，两入口、只读详情、孪生管理项不可见与密码返回入口 |
| iOS 模拟器签名构建及定向测试 | **TEST SUCCEEDED**，iOS 27、RM Design Small 模拟器；实际截图已视觉检查 |
| `git diff --check` | 通过 |

后端验证使用隔离数据库、实际迁移、实际 API 及确定性的 STT／Twin／声音替身，不调用真人模型或真实供应商。完整回归中的6个跳过不记作通过。

完整回归后补充了游客云端转写用途说明中的供应商域名、模型及临时副本说明；最终游客49项再跑通过（18.87秒，`/tmp/remember-me-guest-final-tests.log`）。

iOS 命令为 `xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe -destination 'platform=iOS Simulator,id=FB5B94AC-8CFA-41D7-B710-AD11597433FD' -derivedDataPath /tmp/remember-guest-ios CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM= -only-testing:RememberMeTests/GuestAccessTests -only-testing:RememberMeTests/ECSConnectionTests -only-testing:RememberMeUITests/GuestAccessUITests test`。日志 `/tmp/remember-guest-ios-verified-tests.log`；UI 为独立 DEBUG 虚构资料，不能替代本人账号与真实声音体验。

首轮测试曾遇到未签名 RTC framework 无法启动，以及测试 URLProtocol 将 body 转为 stream 后测试代码解包失败；签名配置和测试读取方式修正后，上述最终49项单元与2项UI测试通过。同工作区正在进行的孪生视觉改动已保留并纳入最终构建。

截图视觉复核后修正深色模式输入框提示文字对比度，再次构建并通过2项UI测试（27.30秒，`/tmp/remember-guest-ios-contrast-ui-tests.log`）。最终截图为 `/tmp/remember-guest-ios-contrast-review/0B9C0B8C-C2EC-4528-9C85-D9A72F0191FB.png`（花园）和 `/tmp/remember-guest-ios-contrast-review/4CC566C5-D6A8-4A2F-BADC-E32031C7738B.png`（Twin）；已目视检查布局、来源标签与输入提示可读性。

覆盖独立入口／游客／本人凭据、直接接口拒绝管理权限、完整来源预览、跨人物隔离、新来源默认私密、私密／保护／未核对拒绝、过期预览、来源修改／删除／撤权、模型生成与音频输出中的撤权竞态、连续会话隔离、访客不训练、密码复验、登出回收、原音丢失稳定失败、临时录音不落本人资料、默认／本人声音独立许可，以及退出与 TTL 清理。

## 会话与来源保护

游客 bearer 不会通过原 `current_actor` 身份检查；iOS 游客模型不持有本人 pairing，后台采集、连接恢复和深链均不能恢复本人权限。开放来源的快照和修订在读取、生成发布、原音返回和每段声音合成时重新检查。iOS 每2秒及播放前核验，失效或网络无法核验时隐藏内容并停止播放。

退出、密码复验成功、本人登出和范围变更清理服务端内存中的游客上下文。异常离线或客户端崩溃时，会话最长2小时，服务启动及每60秒清理到期／失效授权元数据；本机录音不落盘，重新启动仍会清扫旧版本遗留文件。花园响应晚到和麦克风权限回调晚到均使用状态代次防止重新显示资料或在后台启动录音。

## 交付边界

生产服务仍需包含 `0029_guest_access` 迁移与本轮 Backend 代码，才能与新入口联用。现有声音供应商、识别模型与本人音色听感未在本轮真实联调；不可由自动化替身检查推断自然交流体验。原有录音和记忆不自动开放，不迁移或删除本人原数据。

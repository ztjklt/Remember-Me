# 声纹姓名与手机外放统一部署

2026-10-16，Asia/Singapore。用户在确认声纹匹配及绿色姓名显示的区别后明确要求「部署」，替代此前暂缓发布的要求。本次仅部署已保留的 iOS／CloudBase／LiveKit 增量，没有合并 Android PR #94。

## 发布结果

- Backend：工作区 `/Users/jitian/.codex/worktrees/speaker-introductions/Remember Me`，源码 `e3a7e24`，姓名实现提交 `88bd1cf`。基于原 `ios-wearable-capture-fcb7aa0` 的固定镜像 digest，仅覆盖 `services/backend/app/api/realtime.py` 与独立姓名事件 schema。CloudBase 任务 `2370267` finished，新版本 `remember-ios-api-045`，公网 release `ios-speaker-display-e3a7e24`。
- `/ready` 的 database 与 object_store 均为 ok。数据库迁移仍是 `0024_voiceprint_entrust`；现有环境变量仅修改 release ID，CPU、内存、副本数、端口、VPC 与公网配置均与发布前一致。CloudBase CLI 原登录失效，已通过原账号的官方登录及本机回调恢复。
- Worker：原 Agent `CA_tPrXyGHActp3`、原 `ap-south` 区域，部署版本 `75qCzegzrBFb`，控制面状态 Running。没有修改供应商、长期密钥或诊断开关。
- iOS：重新执行 Release 签名构建及 `codesign --verify --deep --strict`，均通过。**1.13.2 / 2026101508** 已覆盖安装至 iPhone 15 Pro Max「黑幕」，系统安装清单确认从 1.13.1 升级。未卸载或清空容器；与既有文件清单比较，7 个原有 m4a 文件均存在，大小与修改时间一致。
- 安装时手机锁屏，前三次启动被拒。用户随后解锁，`devicectl device process launch` 已返回 success，确认运行进程，并再次核对版本 1.13.2 / 2026101508。成功启动日志为 `build/voice-speaker-launch-unlocked-20261016.json`；真人声纹和外放体验仍待用户实际使用。

## 实际检查

- 本次重新执行 Backend `test_voiceprint_person_model.py`：12 项通过；Worker `test_natural_capture.py`：7 项通过。iOS 通话的三个源码文件 SHA-256 与此前已通过 23 项逻辑、2 项 UI 检查的版本相同；本轮不把历史 UI 检查算作重跑。
- 公网姓名接口：仅使用既有 `ios-synthetic-demo` 隔离账号及声明的系统合成声音，经真实 ASR 和声纹模型处理。首次登记返回空姓名，后续匹配返回 `speaker_names: ["小王"]`，撤销模板后返回空姓名。临时通话、许可、模板和本轮派生录音已清理，剩余有效模板为 0；没有使用本人的声音或声纹。
- 第一份姓名探针选用了旧 `speaker_qa_` 空间，该空间不在生产实时通话开放范围，capabilities 返回 404，未登记模板或创建通话。保留失败报告；随后在现有允许的专用合成账号通过，未扩大生产开放名单。
- 原生产票据、默认声音的完整 RTC 场景：14.006 秒进入 listening，前两次答案分别于 31.351／43.776 秒出现，共收到 55 个非零音频帧；自动插话及手动打断后宽限窗口均无旧声音恢复。静默65秒后第三次输入未收到新问题／答案，最终 `third_answer` TimeoutError，**完整场景失败**。
- 上述 RTC 通话结束、VOICE 撤销均 HTTP 200；本轮合成答案已删除，持久状态确认已结束，个人音色仍为 missing，清理无错误。Worker 汇总记录了3个 ASR final，但未取得第三次输入缺失的确定根因；不将累计发帧或服务上线当作完整通话修复。

## 证据与边界

主工作区 `build/speaker-display-deployment-summary-20261016.json` 保存脱敏汇总；构建、安装和启动日志分别为 `build/voice-speaker-deploy-20261016.log`、`build/voice-speaker-install-20261016.log`、`build/voice-speaker-launch-20261016.log` 与 `build/voice-speaker-launch-retry-20261016.log`。

后端工作区 `build/speaker-display-deployment-verified-20261016.json`、`build/speaker-display-public-api-verified-20261016.json` 与 `build/speaker-display-rtc-scenario-20261016.json` 保存发布、姓名接口和完整通话结果；原始控制面与测试脚本在 ignored `build/private/`，不提交凭据、原音或用户内容。

绿色姓名为每轮发言后台声纹结果，不是逐字即时识别。真人声纹准确率、相近声音／多人重叠、手机外放回声及完整通话稳定性仍未验收。本次发布不证明底层网络问题永久解决。

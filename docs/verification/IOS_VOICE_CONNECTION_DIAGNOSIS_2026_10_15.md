# 语音连接超时：重启缓解，稳定性仍未验收

2026-10-15，Asia/Singapore。本人反馈一直显示“连接中”后超时。本轮只恢复和检查原服务，没有发布待统一部署的声纹姓名更新，没有重新安装手机或改变 Backend Contract。

## 当前证据

- 原 Agent 日志中，20:31:46、20:32:00、20:33:24、20:34:33、20:40:10 共五个 job 在 `authorize_startup → HTTPX connect_tcp` 报 `ConnectTimeout`。它们尚未进入 ASR、Twin 或音色播放；不能归因为本人声音样本。日志没有目标 peer 或平台路由取证，不能断定具体网络设备或云平台责任。
- 本机 `/health` 与 `/api/v1/service-info` 均 HTTP 200，生产仍为 `ios-wearable-capture-fcb7aa0`。API 健康不代表 Worker 能从其运行位置访问 Backend。
- 20:46 执行官方 `lk agent restart` 成功。仍是原 Agent `CA_tPrXyGHActp3`、原版本 `twatnUv6ZbRt`、原 `ap-south` 区域；没有 deploy、修改密钥、购买资源或切换服务。新实例在 20:46:43 注册。
- 重启后空诊断房间成功调度一个 job；不存在的诊断 call 在约 3.9 秒返回预期 404，证明该次新 Worker 已能连接 Backend。诊断房间已删除，无音频或真实账号。
- 初始两次独立合成 QA 入房仍遇到信令超时；它们均结束通话并撤销临时 VOICE（HTTP 200），个人 profile 保持 missing。
- 随后两次独立合成 QA 均收到服务端 `listening`，从检查开始分别约 25.008 秒和 7.509 秒；RTC 分别约 20.019 秒和 4.437 秒。前者显式使用双 PeerConnection，后者只将单次信令等待设为 10 秒，均没有改变生产配置。不能凭这两个不同测试设置断定某个 SDK 选项修复了故障。
- 第三个默认设置的合成 QA 单轮实际识别出问题并收到 `CONVERSATION` 答案，26.366 秒 listening、33.420 秒 question、45.784 秒 answer。它等待足够的非零播放帧时超时，**声音检查未通过**；不能把 `speaking` 事件当作音频已送达。通话结束与 VOICE 撤销均 HTTP 200，个人 profile 仍 missing。没有本人样本或复刻。

## 检查限制和清理

原三轮／打断／65 秒静默回归工具两次在只读控制面 preflight 超时，尚未创建通话，不能算完整回归通过。只读数据库直连检查也未成功，未为此改变生产网络或认证设置。

单轮声音检查使用既有专用 `ios-synthetic-demo`，没有提供 Recording／Speaker Identification 许可，不采集 Episode、不注册声纹、不训练本人模型。因数据库控制面不可用，本次一条合成聊天答案暂保留在专用 QA 空间；其精确 answer/call/owner 编号只存于 Backend 工作区 ignored 的 `build/private/voice-connection-smoke-answer.json`，后续仅按这些编号清理，不删除整个账号的历史。各测试的临时 VOICE 和通话均已通过公开 API 清理。

脱敏报告在主工作区 `build/voice-connection-20261015/`。原始日志、测试脚本和清理定位材料在 `/Users/jitian/.codex/worktrees/speaker-introductions/Remember Me/build/private/`，不提交凭据、原音或问答正文。

## 结论

已确认并缓解原 Worker 到 Backend 的启动连接故障，之后三次通话能进入监听，其中一次完成识别和文字回答。但实时链路仍出现信令超时，实际音频检查失败，不能称稳定连接或完整语音修复。本人手机重拨结果与底层网络细因尚待确认；不以继续增加重试、放宽授权或切换供应商掩盖故障。

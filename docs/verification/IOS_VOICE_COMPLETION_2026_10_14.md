# iOS 前台实时语音完善

2026-10-14，Asia/Singapore。Product / Integration Owner 直接批准本聊天的实施计划。iOS 在主工作区保留既有未提交改动；Backend / Worker 在 codex/twin-chat-memory 工作区修改，延续 df7b22b 生产基线。

## 行为与接口

- 开始前重新检查 capabilities/profile/policy；用途改变必须重新确认。Backend ticket 创建继续检查真实登录、Subject、授权和音色，不由手机重建授权。
- 初始监听同时等待麦克风发布和 Worker 的 ASR-ready 监听事件；就绪前 question / speaking 不能绕过门槛。
- iOS reconnectAttempts=0，重连/断线回调结束通话；Worker ProxySTT max_retry=0 且错误不可重试。旧连接和轮次不能恢复收音或播放。
- 自动插话除了本机静音，还可靠发送当前轮 interrupt；保留服务端答案链、晚到结果排除和 UNKNOWN 不朗读。
- 显示系统路线，提供系统输出选择。耳机拔出、锁屏、后台和系统音频中断结束通话；不启用后台收音。
- Worker 与 Backend 的诊断默认关闭。启用时记录分阶段语音片段计数、数字化通话关联号、耗时和帧数，不保存 PCM、转写或凭据。各阶段片段编号独立，不能仅凭相同编号声称同一句已到达。播放首帧日志表示 Worker 将帧交给 SDK，实际 RTC 接收另由探测计数。
- 后端向 ASR 的 PCM 写入增加 2 秒上限，阻塞时关闭识别链路，不累积陈旧语音。既有终止落库和远端删房上限保留。
- 不修改公开 v0.6/v0.7 payload，不新增迁移，不切换供应商。普通通话不自动成为人格证据。

## 已实际运行

- 原生产 Cloud Agent 完整复测一次通过：两轮交流、自动/手动打断、65 秒静默后第三轮及原音输出。安全报告在原 livekit-twin 工作区 build/realtime-cloud-ready-control-report.json。专用 QA preset 引用先清空后撤销 VOICE、结束测试通话，profile missing。没有本人克隆。
- 这次原生产复测不能证明 10 月 13 日间歇故障的根因，也不是新实现验收；本次没有为了无法复现的故障猜测性更换供应商。
- Worker 49 项通过；含禁用 SDK 自动识别重试、失效 ready 清除、分阶段第三个语音片段和诊断隐私检查。
- Backend 定向回归 72 项通过，覆盖实时声音、多轮会话、旧聊天记忆、人物更新、授权；包含新增端到端 ASR 代理诊断格式检查。2 个依赖弃用警告。
- 主工作区 Contracts 23 项通过，v0.1–v0.7 兼容性保留。
- iOS 定向回归 86 项通过：Voice 16、连接/聊天 35、LocalRecording 20、PersonReview 15。第一次旧用例仍断言就绪前处理问题，并等待不再发生的打断发布，失败/挂起；中断旧测试进程，更新为新规则后通过。
- 新增语音路线 UI 用例通过，使用隔离 DEBUG 预览；显示路线、前台说明和控制，挂断后收起控制。此预览没有网络、音频或真实授权。

## 新实现联调与设备

前两次 staging 预检查因复用的 Cloud 脚本禁止 dispatch override，在 ticket 校验处停止；均独立清理了通话、preset 引用和专用 VOICE。改为显式 staging 参数后，新 Worker 本机运行、真实 Cloud 媒体及现有 Backend 的三轮/65 秒场景通过。逐片段诊断明确观察到第三段 RTC 输入、ASR 发送、第三次 final、Twin 回答和输出帧；源码回归脚本已纳入 tools/verification/realtime_voice_probe.py。

Backend / Worker 源码 85b4987 已推送 codex/twin-chat-memory。源包白名单 167 文件，SHA256 6196adf2b2005503c5f7e99039c6243c1f639e06f4891ef34127fa5b5302ab23，运行密钥扫描通过。CloudBase 019 / task 2352263 的 CreateVersion 和 ReleaseVersion 均 finished；构建镜像 digest dab881004d9f4a743c6e0b1345df823c2de1f72b6b4a9f068f0f3d01b5084312。镜像推送完成与管理任务完成之间存在延迟，准备过复用镜像的请求但没有执行；本次原发布任务成功。

实际 HTTPS service-info 返回 ios-voice-completion-85b4987，ready HTTP 200。未执行迁移，升级前后均为 0020_chat_memory、Episode 5、Memory 9。既有登录、RTC、模型、存储和资源配置保留。

新 Cloud Worker 与新 Backend 完整验收通过：首次监听 4.934 秒；三轮 question→answer 分别约 8.548、4.200、3.869 秒（不等于用户停说到听到声音的总时延）。第三段注入时刻 96.741 秒、第三条 question 101.727 秒、answer 105.596 秒。静默 65 秒后继续识别与播放；自动打断空档、手动打断后的静默均为 0 个非零音频帧，旧轮无重启。397 个合成输入帧均送出、捕获错误 0；结束和 VOICE 撤销 HTTP 200，preset 引用先清空，profile missing，专用测试通话均结束。累计关闭码 1006 在清理期出现，不能作为识别失败证据。本次原生产、staging、新 Worker 和新 Backend 的成功样本不证明旧间歇故障永久消失。

最终 iOS 1.7.1 / 2026101401 签名构建通过；包内版本与设备应用列表独立核对。devicectl 覆盖安装和启动均 success，没有卸载或清空容器，未传入测试启动参数。后台音频权限未开启。系统路线选择使用 AVRoutePickerView，最终 UI 用例复验及带输出选择图标的截图检查通过。231 个不同自动用例通过；不是所有检查在同一命令中运行。

本人音色、真人自然交互、实际蓝牙/有线耳机、拔出、锁屏及来电均需本人在真机上操作。模拟器、系统预置音色和构建不代替这些结果。

## 后续能力

会议全部后续事项已形成[提案与启动条件](../architecture/product-completion-proposals-2026-10-14.md)。本轮不实现多人声纹、受保护花园或身后开放。

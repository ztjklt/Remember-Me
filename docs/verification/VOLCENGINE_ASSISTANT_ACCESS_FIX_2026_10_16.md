# 本人音色助手未接入的定位与修正

2026-10-16，Asia/Singapore。本人反馈 App 可打开，但通话提示「语音助手未能接入，请重新开始通话」，并已连接解锁手机。本轮继续既有修复、部署及覆盖安装授权；不增加云权限，不使用本人原音做测试。

## 已确认的边界

- 读取失败诊断时，手机为 1.15.1 / 2026101606。该诊断中 RTC 已进房、音频采集与发布正常、最大上行 58 kbps，助手加入为 false，有效会话事件为 0。
- 失败窗口的两次创建、激活均为 HTTP 200；58 次状态查询及 24 次续租也全部成功。没有 ASR / CustomLLM 回调轮次。约 25 秒客户端助手等待超时后才停止续租，约 41 秒后台清理，不能把后续租约过期当作最初原因。
- CloudBase051 为唯一 100% 流量版本，只有一个 Running 实例。默认音色隔离测试成功收到 Bot 加入、Stage 1/2/3、上行约 57 kbps，后台生成回答，排除共享 RTC / ASR / CustomLLM 链路整体不可用。

## 对照证据与修正

使用隔离合成账号、随机房间、静音轨道比较两种配置；不申请麦克风，不创建或读取复刻音色，不传本人录音。两次 Start 均返回成功，但实际行为不同：

| 配置 | Bot 加入 | 20 秒内状态或错误消息 | 清理 |
| --- | --- | --- | --- |
| 原配置：TTSConfig 仅 AutoActive=false | 未加入 | 无 | Stop / call / 两项 grants 均完成 |
| 修正：false + Provider + ResourceId + audio.voice_type | 约 1.5 秒加入 | 无错误，静音未触发对话 | Stop / call / 两项 grants 均完成 |

Backend 保留关闭 TTS，同时补回最小的 provider 身份配置；不带此前触发 1000002 的 speech_rate / additions。字幕仍为不依赖 TTS 的模式 3，本人音色仍由已有独立合成服务播出。更新 transport policy generation，使新配置的通话票证与旧配置区分。

最新 [StartVoiceChat 官方文档](https://docs.volcengine.com/docs/real_time_communication/StartAIconversationStartVoiceChat-1?lang=zh) 仍将 Provider / ProviderParams 标为必选；是否能入房以本次真实 RTC 对照为证，不把 HTTP 200 当作接入成功。

iOS 增加只含数值的房间消息送达、conv 解码、sender/task/轮次/时间拒绝、用户与匹配助手进房计数。保留原校验、超时、通话行为，不保存消息、文字、身份或凭据。这样以后能区分「未收到消息」与「消息因校验未被采用」。交付版本为 1.15.3 / 2026101608。

## 本轮验证与交付状态

- Backend RTC / 功能复用 / 来源连续性 / 音色审核 30 项，以及删除 / migration 16 项，共 46 项定向测试通过；此前整体审核的测试结果见 [审核修复记录](VOICE_AUDIT_FIXES_2026_10_16.md)。
- iOS 数值诊断的 Simulator 原生编译通过；VolcengineVoiceTests / TwinVoiceCallTests / VoiceReviewTests 共 46 项通过。1.15.3 Release 构建和 deep / strict 签名校验通过。安装包与源输入摘要保存在主目录 `build/releases/RememberMe-1.15.3-2026101608.*`。
- CloudBase052 / `ios-voice-connect-d7165ce` 已完成发布，100% 流量及公开 service-info 读回一致。0026→0027→0028 事务迁移及五列一索引读回通过。168 个 Git 来源文件使用固定 045 运行镜像。051 已退役，镜像及私有配置快照保留；应用回退保留兼容的新增 schema，不删除验收和重试记录。
- 新 052 默认声音真实 RTC 回归通过：Bot 加入、Stage 1/2/3、约 66.5 kbps 上行、后台生成回答，lease 失败为 0。
- 新 052 本人模式完整合成测试通过：临时系统音色创建→非零试听→审核技术闸门→同一通话两次固定合成问句→两个不同保存答案→各自独立的 310080-byte 非零 24 kHz mono PCM。24 条房间消息、5 条 conv、约 67.4 kbps 上行、lease 失败为 0。独立 TTS 首包分别约 1.37 / 0.88 秒，只是 TTS 请求延迟，不能当作整轮响应延迟。
- 独立 DB 复核：两轮对应两个不同 voice_turn，通话已结束且无需远端停止，精确本次许可均撤销；临时音色已 deleted，原始样本和远端音色 ID 均清除。保留两条失效的 QA 回答审计记录，未读内容。默认回归也已结束并撤销其精确许可。
- 本轮使用合成账号和系统声音，没有使用真人原音；不宣称音色相似度、手机扬声器听感或两分钟真人持续通话已验收。
- **手机已覆盖安装并启动 1.15.3 / 2026101608。** 安装期间一度因 USB 不可用被 CoreDevice 4016 拒绝；本人再次要求安装后，读回 wired connected，取得新的安装前清单。从 SHA256 匹配的不可变 zip 解包后重新检查深度签名、版本、描述文件有效期和设备授权，再覆盖安装，未卸载 App。安装与启动均成功，应用列表读回版本一致、容器可访问；安装前后的 11 个 m4a 路径和完整 metadata 一致。旧音色及声纹保留，本人音色需在新版试听后确认使用。手机实际听感仍待本人验证。

主目录安装证据：`build/private/voice-connect-retry-files-before-20261016.json`、`voice-connect-install-1608-receipt-20261016.json`、`voice-connect-launch-1608-20261016.json`、`voice-connect-app-after-1608-20261016.json`、`voice-connect-files-after-1608-20261016.json`。安全汇总为 `build/volc-research/voice-connect-delivery-proof-20261016.json`；发布 manifest 已如实标记 installed=true / native_audio_verified=false。

安全证据在 ignored build：`access-diagnosis-proof-20261016.json`、`volc-default-probe-051-proof-20261016.json`、`volc-default-probe-052-proof-20261016.json`、`volc-personal-control-baseline-b93855fe334f-proof-20261016.json`、`volc-personal-control-minimal-0a4011353d4f-proof-20261016.json`、`volc-personal-e2e-99e2c4b39cb5-proof-20261016.json`、`volc-personal-e2e-independent-db-proof-20261016.json`、`voice-connect-deployment-20261016.json`。原始控制面回执和凭据仅保存在 private / 0600，不提交。

# 本人音色启动错误与设备验证修正

2026-10-16，Asia/Singapore。本人反馈 1.15.0 试听与通话均无声，通话提示「国内语音连接已中断，请重新开始」。本次继续原功能恢复授权，不增加许可范围或厂商密钥。

## 已确认的原因

手机诊断显示已进房、AI 已加入、收到 Stage.Code=0。数据库中两次本人模式通话分别约 2.45／2.25 秒结束，结束时租约仍剩 13 秒以上，尚无第一轮问答。不是以保活过期解释本次现象。

隔离合成账号通过真实 RTC 二进制消息复现 `ErrorInfo.ErrorCode=1000002`，Reason 为 `preParamCheck:unknown fields`，指出关闭 TTS 后仍带入 `Config.TTSConfig.ProviderParams.audio.speech_rate` 与 `Config.TTSConfig.ProviderParams.additions.enable_latex_tn`。此前仅 HTTP Start 成功的 API 探针没有覆盖这个异步初始化失败。

## 修正与交付

- Backend `cb8967c`：本人模式 TTSConfig 仅传 AutoActive=false，不传停用的合成参数；字幕改为不依赖 TTS 的 LLM 原始字幕模式 3。默认声音配置保留。官方 [StartVoiceChat 说明](https://docs.volcengine.com/docs/real_time_communication/StartAIconversationStartVoiceChat?lang=zh&redirect=1) 明确停用 TTS 后字幕模式 0／1 不可用。
- CloudBase051／`ios-volcengine-parity-cb8967c`，任务 2372967 已完成，100% 流量及 service-info 读回一致；050 下线、镜像和私有配置备份保留。
- iOS 1.15.1 / 2026101606 解析实际 ErrorCode 与文档 Code 两种数值键，保存数值原因并显示服务错误码，忽略厂商错误正文。试听新增仅数字的播放进度、时长、音量、输出是否为扬声器诊断，不保存音频、文字或标识；媒体音量为零时明确提示。
- 试听开始会释放上一次播放并清除请求编号。修正此后音频会话／播放器失败被旧编号校验吞掉的问题；保留账号、profile 和当前通话状态检查。
- 本机签名、证书链、有效期、设备在描述文件内均通过；覆盖安装前后 11 个 m4a 元数据一致。自动启动被 iOS 验证检查拒绝，本人改用蜂窝网络验证后明确回复「验证成功，可以打开」。[Apple 官方说明](https://developer.apple.com/help/account/provisioning-profiles/provisioning-profile-updates) 解释开发安装的联网验证要求；未撤销证书、删除 App 或绕过验证。

## 实际验证与未完成项

Backend 功能恢复／RTC 边界定向 20 项通过；iOS 通话与错误消息解码定向 35 项通过；最终 Release 构建及深度签名检查通过。此前两项复刻 UI 检查不冒称在本次重跑。

修正前 RTC 对照复现已保存。修正后的隔离浏览器对照未再收到 1000002，但合成音频注入未在 40 秒内产生答案，不能将这次探针称为 ASR→Twin→本人音色端到端通过。本人随后明确暂时无法通话验证，手机试听、两轮问答与约两分钟持续通话保留为待验。不能把安装或参数接受冒充真人听感通过。

## 证据

Backend ignored build：`volc-personal-startup-before-20261016.json`、`volc-startup-comparison-20261016.json`（含未通过结果）、`volc-personal-startup-deployment-20261016.json`、`volc-personal-startup-retire-050-20261016.json`、`volc-personal-startup-tests-20261016.log`。临时 QA 账号和系统合成声音用于对照，原账号音色与原音未用于探针。读回本轮未结束调用、待远端停止、有效临时许可、回答数均为 0，临时音色 deleted；当前只有 1 个 Running 实例。

主工作区 ignored build：`volc-research/ios-volc-startup-tests-20261016.log`、`volc-research/ios-volc-startup-release-20261016.log`、`private/volc-1606-install.json`、`private/volc-1606-files-before.json`、`private/volc-1606-files-after.json`、`private/volc-parity-latest-native-20261016.json`。包含凭据的原始平台响应与 SDK 日志只留 private，不打印或提交。

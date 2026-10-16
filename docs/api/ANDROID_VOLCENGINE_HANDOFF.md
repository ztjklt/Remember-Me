# Android 接入现有火山语音服务

2026-10-16。本人确认队友负责 Android 客户端，并复用现有 Remember Me 后端。本说明与 `codex/ios-latest-20261016` 的 iOS 参考实现、共享 Contract 一起交接。

## 交给队友的内容

| 材料 | 地址或位置 |
| --- | --- |
| 后端 Base URL | `https://remember-ios-api-327435-12-1411199312.sh.run.tcloudbase.com` |
| 客户端接口契约 | [火山通话 v2](../../packages/contracts/schemas/volcengine-voice-v2.schema.json)、[本人音色验收](../../packages/contracts/schemas/voice-review-v1.schema.json) |
| HTTP 参考代码 | [TwinVoiceAPI.swift](../../apps/ios/RememberMe/TwinVoiceAPI.swift)、[Network.swift](../../apps/ios/RememberMe/Network.swift) |
| 通话状态与资源清理参考 | [TwinVoiceCall.swift](../../apps/ios/RememberMe/TwinVoiceCall.swift)、[VolcengineVoiceTransport.swift](../../apps/ios/RememberMe/VolcengineVoiceTransport.swift) |
| 本人音色 PCM 播放参考 | [PersonalVoicePCMPlayback.swift](../../apps/ios/RememberMe/PersonalVoicePCMPlayback.swift) |
| 联调账号 | 由管理员单独交付队友的账号、密码；在此后端拥有独立本人空间 |

该 Base URL 是 Remember Me 的 HTTPS 接口，默认端口 443。客户端通过它登录、申请房间票据、控制通话；实际媒体由 Android RTC SDK 与火山服务传输。媒体连接由 SDK 管理，不应把此 HTTPS 地址当成 RTC 媒体服务器地址。

本次只读检查：`GET /ready` 为 200；`GET /api/v1/service-info` 为 200，`release_id=ios-latest-f54e295dc7d4`、`registration_allowed=false`；匿名访问火山能力接口为 401。这些结果只证明服务可达且需要登录，没有创建账号、启动收费通话或验证 Android 媒体链路。

当前关闭自助注册，需要管理员安排独立联调账号。Android 现有另一套后端的账号不一定能在此地址使用；`subject_id` 应从本次登录后的空间列表读取。账号密码、用户登录 token 和实际 RTC 房间票据不提交 Git。

新建空白账号注意：当前服务沿用 Twin 的首次初始化门槛，读取语音能力前还要求该空间有本人有效 `RECORDING` 许可；缺少时会返回 404，不能据此判断账号密码或空间有误。用户在客户端明确确认录音用途后，先通过 `/api/v1/consents` 建立该许可，再读取语音能力。管理员创建账号不会预先授予任何用途；`CLOUD_TWIN`、`VOICE` 在通话前仍分别确认。已有录音许可也不等于本次通话自动采集，是否上传原话仍由本次通话的可选采集字段和声纹许可共同决定。

## Android SDK

Android 需要集成自己的火山 RTC SDK 并实现媒体适配器。官方提供 [Android SDK 接入说明](https://docs.volcengine.com/docs/real_time_communication/Android-1?lang=zh)和 [SDK 获取／Maven 配置](https://docs.volcengine.com/docs/real_time_communication/GetSDK?lang=en)：Maven 仓库为 `https://artifact.bytedance.com/repository/Volcengine/`，依赖坐标为 `com.volcengine:VolcEngineRTC:<已验证版本>`。Android 负责人按所需音频场景、房间消息及 PCM 播放 API 验证并固定版本；本轮未选定或验证 Android SDK 版本。

iOS 仓库已提供 `apps/ios/scripts/prepare-volcengine.sh`，下载并校验固定版本 **3.60.107.1100** 的 iOS SDK。该版本号和 `.xcframework` 属于 iOS 交付，不能据此声称 Android SDK 已验证。SDK 二进制没有上传 Git，客户端源码与下载脚本已上传。

火山 AppKey、AK／SK、模型密钥和回调密钥继续由现有后端管理。Android 从每次通话票据读取公开 `app_id`、短期 `token`、`room` 和用户身份；不在客户端生成火山票据或调用 StartVoiceChat 等管理 API。

当前产品使用音频通话，不发布或订阅视频；接入时保持摄像头关闭。

## 登录与通话接口

以下路径都拼接在 Base URL 后。登录返回 `actor_token`，后续受保护请求带 `Authorization: Bearer {actor_token}`。`S` 表示该账号本人空间的 `subject_id`，`C` 表示本次通话 `call_id`。

| 顺序 | 方法与路径 | 要点 |
| --- | --- | --- |
| 1 | `GET /api/v1/service-info` | 查询服务信息 |
| 2 | `POST /api/v1/accounts/login` | JSON：`username`、`password`；读取 `actor_token` |
| 3 | `GET /api/v1/workbench/spaces` | 选择本账号的 owner 空间，读取 `subject_id` |
| 4 | `GET /api/v1/consents?subject_id={S}` | 查有效许可；新空白账号先处理首次录音用途确认 |
| 5 | `POST /api/v1/consents` | JSON：`subject_id`、`scope`、`evidence_ref`；本人明确确认后先初始化 `RECORDING`；默认声音也需要另行确认 `CLOUD_TWIN`、`VOICE` |
| 6 | `GET /api/v1/subjects/{S}/twin/voice/capabilities?transport=volcengine&features=2` | 完成首次初始化后读取当前 `notice`、`policy`、`available` 和可选能力；根据实际通话说明完成尚未确认的用途 |
| 7 | `POST /api/v1/subjects/{S}/twin/voice/volcengine/calls` | 申请当前用户、房间的短期票据 |
| 8 | Android SDK 加入 RTC 房间 | 使用票据的 `app_id`、`room`、`participant_identity`、`token`；先保持麦克风关闭 |
| 9 | `POST /api/v1/subjects/{S}/twin/voice/volcengine/calls/{C}/activate` | 原生进房成功后调用，再启用麦克风；根据真实机器人事件显示监听状态 |
| 10 | `POST /api/v1/subjects/{S}/twin/voice/volcengine/calls/{C}/lease` | 独立保活；iOS 当前约每 2 秒一次 |
| 11 | `GET /api/v1/subjects/{S}/twin/voice/volcengine/calls/{C}/status` | 获取问题、答案和说话人状态；iOS 当前约每 750 ms 一次，不阻塞保活 |
| 12 | `POST /api/v1/subjects/{S}/twin/voice/volcengine/calls/{C}/interrupt` | JSON：`turn_id`，只打断指定轮次 |
| 13 | `DELETE /api/v1/subjects/{S}/twin/voice/volcengine/calls/{C}` | 挂断；客户端同步停止采集、取消轮询并释放 SDK |

首轮使用默认声音，申请票据的示例请求如下。尖括号值均须替换为本次服务实际返回的值，不能固定复用其他账号的许可或旧 policy：

```json
{
  "cloud_consent_id": "<有效 CLOUD_TWIN 许可 ID>",
  "voice_consent_id": "<有效 VOICE 许可 ID>",
  "policy": "<本次 capabilities.policy>",
  "voice_mode": "default"
}
```

票据返回 `transport=volcengine`、`call_id`、`app_id`、`room`、`participant_identity`、`bot_identity`、`token`、`expires_at`、`voice_mode`。房间票据仅用于这次 RTC 会话，不替代账号登录凭据。过期、撤权或通话结束后不复用旧票据。

客户端需接收原生 RTC 房间二进制消息并按现有 iOS TLV／Conversation 解析处理识别、状态和打断；不能只调用 HTTP 接口就将页面标为可通话。短暂断线恢复时先核对 lease，确认通话仍有效后才恢复麦克风。401／403／404／410／422 按现有 iOS 逻辑结束当前通话，不无限重试。

## 本人音色、声纹与自动采集

先完成默认声音的真实 Android 通话，再按 `features=2` 返回的能力补齐下列行为，保持共享 Contract 与独立用途不变：

- 本人音色需当前 VOICE 许可对应的 profile 就绪，并由本人试听接受：`GET .../volcengine/profile/preview`，随后 `POST .../volcengine/profile/review`，JSON 为 `profile_id`、`accepted`。申请通话时明确 `voice_mode=personal`。本人音色仍复用现有 CosyVoice 服务。
- 本人音色通过 `GET .../volcengine/calls/{C}/speech/{turn_id}/{answer_id}` 获取 **24 kHz、mono PCM**。Android 必须实现稳定的 PCM 播放、尾帧、打断与清理，不能只依赖默认远端音轨。
- 自动保存原话／声纹需要额外且配对的 `recording_consent_id`、`speaker_consent_id`；自然音色准备还需按授权设置 `enroll_owner_voice`。只有票据和能力均允许时才采集上传。
- `POST .../volcengine/calls/{C}/utterances/{turn_id}` 或 `/samples/{sample_id}` 使用 multipart 字段 `sample`，为有界 **16 kHz、mono WAV**；完整边界按 iOS 实现及服务能力处理。未知、亲友和重叠声音不写入本人模型。
- 所有可选录音、识别和学习任务都须给正在进行的 RTC 通话让路；账号切换、撤权、离房和挂断均取消任务并清理音频资源。

## 交付边界

本分支给 Android 提供现有服务的接入契约和 iOS 参考，尚未实现或验收 Android 火山媒体适配器。首次验收记录真实默认声音通话、连续追问、静音、打断、挂断及断线清理；本人音色与声纹另以真实设备核对。

复用现有服务不需要将整套后端再打包给 Android。若以后要独立部署，需另行交付与已部署版本一致的 Backend／AI Core、数据库迁移和服务端配置模板；本次 iOS 源码快照没有包含这些未提交的服务端实现。

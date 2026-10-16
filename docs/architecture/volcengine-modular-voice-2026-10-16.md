# 火山 RTC 模块化实时通话 — Owner 授权重构

2026-10-16。Product / Integration Owner 在本聊天明确选择“火山 RTC＋模块化 ASR／Twin／TTS”，授权替换现有实时通话链路。本提案记录该直接批准，接口不再依赖 LiveKit。Android 原型和 v0.1–v0.12 接口完整保留。

## 线路与边界

火山 RTC 管理国内音频传输、持续 ASR、判停、打断和流式 TTS。自定义 LLM 回调只调用现有 Evidence Twin，后端持有 Actor／Subject／许可／来源／人物模型与多轮上下文。不开端到端模型，不将火山内置记忆作为事实来源。完整核验后才返回可朗读文本；UNKNOWN 返回空语音并保留原答案。禁止预填充未经核验的 LLM 内容。

独立 `/twin/voice/volcengine` 路由及严格 `volcengine-voice-v1.schema.json`；旧票据不变。新票据只含 app_id、指定 room/user、短期 RTC token、到期时间、call_id 和固定 bot_identity。服务端 AK/SK、AppKey、自定义 LLM 凭据、音色 ID 不进入移动端。SDK 在媒体适配层，ASR／Twin／TTS 仍全部由 Backend Contract 管理。

每次 call 绑定原登录凭据和 CLOUD_TWIN／VOICE 许可，30 分钟上限；移动端维持 15 秒租约，服务器每两秒检查撤权、来源失效、过期和停止重试。停止先落库，立即拒绝晚到答案，再调用 StopVoiceChat。服务器重启清理过期租约，不恢复旧通话。多轮 round_id 单调递增，以数据库条件更新隔离晚到／重复回调。打断只作用于对应旧轮。

## 能力分阶段开启

先用公共豆包 ASR 和默认 TTS 验证整个通路。原 CosyVoice profile 与样本保留；火山没有可用本人音色时明确不提供本人音色、自然复刻或声纹自动采集，不能把原音色 ID 发往新服务，也不能将未核验的发言当作本人资料。继续使用原线路需明确选择对应线路并重新确认用途，不能无感发送到其他服务商。

## 验收

本地契约／签名／权限／多轮／重复与乱序／UNKNOWN／晚到／撤权／租约回归，再做手机真实国内链路：连续多轮、65 秒静默后续聊、安静环境整段播放、自动与手动打断、静音／挂断／锁屏／断网。分别记录停说至识别、Twin 完成、首个可听声音，不能以 HTTP 200 或机器人入房代表完整就绪。未开通火山服务或未真实试通时必须明确记录。

参考：火山官方 rtc-aigc-demo（2025-06-01 API），RTC Token 鉴权文档及 VolcEngineRTC 3.60.107.1100 官方 SDK。

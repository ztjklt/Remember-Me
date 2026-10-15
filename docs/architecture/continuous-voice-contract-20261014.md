# 连续语音兼容接口提案（用户方案已批准）

保留现有 /api/v1。新入口默认关闭，仅指定测试账号可用。身份来自 Bearer，禁止 URL token。客户端不持有模型密钥。

## 会话

GET `/api/v1/voice-capabilities`：启用状态、协议版本、音频格式。

POST `/api/v1/subjects/{subject_id}/voice-sessions`：cloud_consent_id、mode(evidence/persona)、ASR/TTS 使用确认、简明模式。返回短期 session_id 和相对 websocket_path。

DELETE `/api/v1/voice-sessions/{session_id}`：结束并取消所有输出。

WSS `/api/v1/voice-sessions/{session_id}/stream`：Authorization Bearer，与创建身份相同；单次连接，不支持复用。

客户端发送：二进制 16kHz 单声道 PCM16LE；JSON pause/resume/interrupt/playback/end。服务端 JSON 事件统一含 session_id、turn_id、type；音频以 JSON audio.data(base64 PCM16LE / 24kHz) 避免无法归属的迟到二进制包。

服务端事件：ready、transcript(temporary/final)、turn_started、answer_ready、audio、audio_end、interrupted、paused、error、ended。音频附序号和累计样本数。playback 报告实际播放样本数；完成播放必须单独报告，音频生成完不等于听完。

## 规则

每轮重新验证身份、云端使用、来源版本。资料或授权变化停止输出并清空历史。取消同时使当前轮次失效；任何迟到回答/音频不可发布。断线/后台暂停停止收音及播放，不重放模型请求。

追问历史为独立的交互上下文，只使用实际播放完的回答及明确标为不完整的播放情况；不能作为人物事实或来源。默认不保存通话原音为记忆。

模型及音频调用不持有数据库事务。错误不能冒充 UNKNOWN。短答在提示词中约束为 1–3 句，保留条件，不通过字符切断。

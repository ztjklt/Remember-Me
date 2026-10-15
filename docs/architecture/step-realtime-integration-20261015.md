# StepAudio 语音试用接入

## 已选路线

Android 原有持续 PCM16/16kHz 输入 → ECS Paraformer 实时识别 → 当前账号可见的有效记忆检索 → StepAudio Realtime 文本输入／原生流式声音输出 → PCM16/24kHz AudioTrack。

沿用 `continuous-voice-v1`、认证 WSS、播放进度、暂停／结束和插话事件。没有调用 DeepSeek 或小米 TTS 生成本轮答案。模型为 `stepaudio-3-realtime-preview`，普通预置音色 `wenrounansheng`。

**决策：本批不启用 Step 自带音频输入/VAD。**此前独立试验的重复响应、收尾与未播放历史尚未解决，先保留现有 ASR 与手机打断。文本入口也是供应商真实 Realtime 接口，不包装文件合成。

## 兼容接口

- `GET /api/v1/voice-capabilities` 增加 `engines`。默认仅 `pipeline`；账号在既有白名单且配置完备时增加 `step_realtime`。
- 会话创建增加 `engine`，缺省 `pipeline`。Step 仅支持 `purpose=dialogue,response_speed=fast`；不能冒称独立模型审阅已执行，也不用于校准报告。
- `answer_ready` 可以多次携带增长的字幕。Step 输出 `source_scope=retrieved_context`，表示本轮检索相关材料，**不是逐句精确引用**。原管线字段及语义保持。
- 音频、轮次、打断、错误、播放进度沿用现有协议；不新增数据库迁移。

## 权限与状态

1. `generate_answer(context_only=True)` 仅内部使用，经过已有授权、有效来源、纠正、反例及人物表达开关检查；不调用模型、不保存答案。
2. 每轮按问题真实检索，支持上下文追问。未授权补记不传给提供商，亲友观点保留作者归属。
3. 每次提供商材料发送及输出事件前复查账号和来源版本；资料／授权变化停止输出，后台现有监测关闭会话。
4. 每轮新建供应商会话，仅传客户端确认已播放的历史。无可靠句子时间对齐时，中断的一整段回复不加入已听历史。
5. 旧轮次、迟到音频、重复 response ID、过长输出、断流均不可继续播放。失败是错误，不伪造 UNKNOWN。
6. 超时或失败不自动重播；用户下一句话重新创建供应商会话。通话及 Twin 回答不自动写入人物记忆。

## 配置与回退

`REMEMBER_STEP_REALTIME_ENABLED` 默认 false；`REMEMBER_STEP_REALTIME_API_KEY` 仅服务器 SecretStr；仍要求原语音账号白名单与 fast 开关。手机不持有模型密钥。

旧 pipeline 默认路线保留。已有提前检索实验增加 `REMEMBER_REALTIME_VOICE_PREFETCH_ENABLED=false`，避免本次发布顺带开启旧路线尚未发布的优化；Step 路线本身使用预取。

关闭 Step 开关后 capability 移除，已有通话停止，新打开弹窗默认原路线。发布目录和环境备份保留以回退，不覆盖数据库或音频。

## 验收界限

权限、来源失效和取消由后端确定性规则控制；内容仍可能被模型过度归纳。没有独立语义审阅，不能称为全部事实已验证。真实 API、真实检索、模拟器音频通道、实体手机收音分别记录。时间以问题结束至首个实际可听声音为最终指标，不将提供商首块或空白块冒充完整体验。

协议依据：https://platform.stepfun.com/docs/zh/api-reference/realtime/chat

# 云端 ASR 接力实施与兼容性提案

用户本轮明确要求停止使用本地转写，指定 `codestral-2508` 和
`mistral-code-fim-latest` 两个中转入口。保留微信 Deepseek-v4-flash 负责核对后的
文字提取、人物候选和来源问答。仅在 codex/agent-integration 本地工作，不推送。

## 证据和未决信息

用户附件确认两个入口各有 8 秒真实音频成功记录，尚无长录音验证；报告未附
中转完整 URL、密钥位置或成功请求体。已向用户请求这些接力信息。不得推测地址，
不得复用微信或小米密钥，不把单元测试视为真实云端验收。

## 接口变化（用户已授权云端切换，本提案记录具体边界）

- 继续使用已有 multipart `metadata` JSON；新增 `cloud_asr_policy` 值，由
  workbench capabilities 返回，绑定当前端点、模型、音频请求格式及提示词版本。
- capabilities 增加 `stt_processing`、`stt_configured`、`cloud_asr_policy` 和
  `stt_model`；均不含密钥。旧字段保留。
- 上传明确要求本段原音云端转写同意。服务端核对 policy，写入自身生成的
  `cloud_asr_receipt`（actor、policy、确认时间）；客户端不能伪造服务端确认记录。
- 旧客户端缺少云端同意时明确失败。旧队列未授权的原音不得因服务切换被发往云端。
  当前已保存原音、转写、核对和记忆不覆盖；新 ASR 对照采用新 Episode。
- 临时语音提问用 `X-Cloud-ASR-Policy` 明确同意，同样不默认为录音授权已覆盖外发。
- 无数据库迁移，不新增事实库。ASR 原始输出与简体核对稿继续分别保存。

## 任务

1. 云端 adapter：两入口白名单、显式完整 HTTPS 端点、服务端密钥、请求格式配置；
   单次请求、有界超时、跨进程串行与至少 35 秒间隔（报告限制 10 次/5 分钟）；
   截断、拒绝识别、空输出、错误状态均失败，不返回伪转写。保存无密钥的调用元数据。
2. 将 policy 同意接到上传、队列、临时提问及网页/Android；启动器默认 relay，
   不再启动 Whisper。不自动降级或切模型。
3. 补齐实际验证脚本：只上传音频字节，短样本验证后再跑完整故事；原音播放校验、
   技术核对、提取、候选和 QA 使用同一实际 Episode。API 配置缺失则明确待测。
4. 运行相关回归、Android 构建；一轮独立代码审查，修复重要问题；记录当前能证明
   和不能证明的结果。三人物长样本通过后才批跑月度材料。

## Review Focus

关注未授权旧队列外发、端点/模型变更后的同意失效、日志泄密、等待限流期间撤权、
拒绝音频却 HTTP 200 被当成功、输出截断、本机 ASR 意外回退及旧客户端兼容边界。

## 实际验收

模型连接信息待补齐。真实调用、识别质量、三人物长故事、60 问、手机实录分别报告；
不可用“接口已接入”代替这些验收。音频请求格式参考 Mistral audio_url/input_audio
协议定义，实际中转格式须通过用户同一端点实测后固定：
https://mistralai.github.io/mistral-common/code_reference/mistral_common/protocol/instruct/chunk/

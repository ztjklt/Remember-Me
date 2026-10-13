# Groq 云端转写接力（用户明确授权，2026-10-08）

## 兼容性和数据约束

用户提供 Groq 凭据并要求停止在 ASR 阶段卡住。新增服务端 `groq` STT 适配器，固定官方音频端点、`whisper-large-v3`，multipart MP3、`language=zh`、`verbose_json`、temperature 0；不传创作原稿或 gold 提示。保持原始音频不变。原始 ASR 与简体核对文字分别保存。

共享 Episode / Memory 契约不变。workbench capabilities 的既有 stt 字段增加 `groq` 值，并返回真实 host/model 和新的云端同意 policy；客户端沿用通用云端提示。持久录音和临时问题转写都检查当前 policy。旧 relay 上传凭据不能授权向 Groq 外发。

配置 `REMEMBER_STT_BACKEND=groq`、`REMEMBER_GROQ_API_KEY`、`REMEMBER_GROQ_ASR_MODEL=whisper-large-v3`，密钥仅在被忽略的服务端 .env。启动器保留显式选择，不启动本地 STT。Groq 使用当前环境代理：本机实测该路径 200，禁用代理路径 403；这不是对 403 原因的判定。没有自动换服务商。

HTTP 429 / 暂时服务错误 / 超时由既有任务最多三次预算处理。401 / 403 等拒绝明确失败。请求串行，原音、压缩音 SHA、耗时、状态与模型请求名称留痕。接口未报告模型身份、usage 或 finish_reason 时明确记为未报告。

## 批次切换

此前 relay 月度批次已完成 24 段：公交司机 10，消防员 7，重病者 7。消防员08、重病者08在旧渠道连接失败，09、10尚未上传。保留全部旧任务/调用/checkpoint；对两个失败08创建新的 Groq Episode（原音相同，新 policy、新幂等键），不要在旧 Episode 上改写来源。成功的24段不重做。后6段使用 Groq，报告按每条实际来源分别计数。

首个独立真实探针：公交司机01全长270.56秒，Groq HTTP200，约3.576秒，903字，原始结果在被忽略的 `var/groq-asr/probe-bus_driver-01.json`。这是连通性和实际转写证据，非人工听读或准确率验收。名称仍有错字。

后续批次和完整核验记录继续更新，不把探针或单元测试冒充全部产品验收。

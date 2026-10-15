# Step API 调研与接入准备（2026-10-15）

结论：按用户所述，将 Step API 理解为阶跃星辰 StepFun 官方开放平台。它是值得实测的低延迟候选；目前没有本项目的 Step 推理耗时，不能说已经比微信 DeepSeek 快。本轮仅调研、核查代码与网络连通，没有创建密钥、购买套餐、改动生产配置或推送 GitHub。

## 1. 官方文档确认

- 中国区标准 API：`https://api.stepfun.com/v1`，请求路径 `/chat/completions`，Bearer Key，OpenAI 兼容请求及 SSE。
- 推荐首批对照：`step-3.5-flash-2603` + `reasoning_effort: low`；`step-3.7-flash` + `reasoning_effort: low`。
- 3.5 的 2603 变体支持 low/high；3.7 支持 low/medium/high。低推理不等于关闭思考，不套用其他厂商的 `enable_thinking=false`。
- 支持 `stream: true`；Chat Completions 文档列出 JSON Mode/JSON Schema，实际所选模型兼容性仍需小样请求核查。
- 响应可能分 reasoning/reasoning_content 与 content；测试必须记录第一段正式正文及首个可用短句，不把思考流当作可播放回答。
- 3.7 官方仓库宣称最高 400 token/s；3.5 官方资料说明典型生成吞吐 100–300 token/s。这是生成吞吐，不是本项目首字延迟或端到端 2 秒保证。
- Step Plan 是另一条订阅通道，当前文档的 `step-router-v1` 会自动在不同模型间路由。本轮宜使用标准按量 API、固定模型 ID，保证对比可解释。

官方来源（核查日期为 2026-10-15）：

1. [Chat Completions API](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create)
2. [Step 3.5 Flash 及 2603 变体](https://platform.stepfun.com/docs/zh/guides/models/step-3.5-flash)
3. [Step 3.7 Flash 官方仓库](https://github.com/stepfun-ai/Step-3.7-Flash)
4. [Step 3.5 Flash 官方仓库](https://github.com/stepfun-ai/Step-3.5-Flash/blob/main/README.zh-CN.md)
5. [快速开始与申请密钥](https://platform.stepfun.com/docs/zh/quickstart/overview)

## 2. 已做的 ECS 网络探针

从现有 ECS 向 `https://api.stepfun.com/v1/models` 发出三次无凭据 GET，不发送记忆，不调用推理。

| 次数 | HTTP 状态 | TCP 就绪 | TLS 就绪 | 首个 HTTP 响应 |
|---|---:|---:|---:|---:|
| 1 | 401 | 41.6 ms | 76.2 ms | 110.5 ms |
| 2 | 401 | 35.4 ms | 74.2 ms | 111.9 ms |
| 3 | 401 | 35.8 ms | 75.1 ms | 113.5 ms |

这些数值从请求开始累计，不能把 TCP、TLS、首响应三列相加。401 是没有携带 Key 的鉴权拒绝；只证明服务器可以连到该接口，**不是模型 0.11 秒回答**。

## 3. 当前工程需要什么改动

现有 `services/ai-core/app/providers/weixin.py` 对 endpoint 和 model 有严格固定校验，直接替换配置会被拒绝。应在隔离测试中加入 Step 适配，而不是取消微信的地址校验。

最小接入只替换“组织文字回答”的供应商。Paraformer、记忆检索、权限、版本校验、来源结构、小米 TTS、Android 播放流程可以沿用。

Step 适配需要处理：

- 独立的服务端 Key 和固定官方 endpoint；不进入 APK、日志、报告或 Git。
- `reasoning_effort: low`，分别记录思考与正文耗时及 token 用量。
- 完整 SSE、结束原因、JSON、来源 ID 校验；流截断和 token 上限导致的不完整结果不能当成功。
- 总请求期限、取消、429 冷却与迟到结果隔离，保留现有规则。
- 用户插话后，过期请求不能继续交付声音。

当前已完成的是代码兼容性判断，尚未实现/部署 Step 生产适配。

## 4. 获取 Key 的实际步骤

已在 Codex 内置浏览器打开官方 [接口密钥入口](https://platform.stepfun.com/interface-key)，页面跳转到 `account.stepfun.com` 登录表单，供用户自行登录。

1. 完成手机号/邮箱等登录；个人账号按官方要求完成实名认证。
2. 进入“账户管理 → 接口密钥”，创建此次测试专用 Key。
3. 核对账户可用额度和请求限制；如需付费，再由用户决定测试预算，首轮不必购买订阅套餐。
4. 将 Key 写入本机忽略的私有环境配置/服务器凭据配置；不要发到公开仓库，也不需要截图展示密钥。中国区 Key 与中国区 endpoint 配套。

本轮没有代填手机号、验证码或身份资料，没有勾选协议，也没有创建 Key。

## 5. 拿到 Key 后的判断方法

先对两个候选各做少量协议小样，确认 low 生效情况、正式正文返回、JSON 选择结构及停止原因。再同一 ECS、同一材料、同一题目交替比较微信基线与 Step；不要把今天 Step 的结果直接和昨晚微信最快值比较。

建议七题各重复五轮，保留首次调用和连续调用的区别；逐次记录：连接、首正文、首个通过来源检查的可用短句、完成、超时/429、输入/输出 token。再将胜出的候选接入 Android，测讲完到第一声以及插话停声。

内容检查保留年份纠正、否定、个人口味的适用范围、旧杯子原因、跨轮追问和无依据拒答。请求成功、结构正确、语义正确分别报告。现有旧状态并列和原因漏答是两项重点回归，不能因换模型忽略。

评估是否替换应同时看成功率、成功耗时中位数、尾部耗时及内容质量；小样本不当服务承诺。基线上一轮模型成功中位数约 1.20 秒，但 Android 最新三题仍为 3.76/3.88/2.99 秒，说明仅提高模型 token/s 不能保证整条链路 2 秒。

StepAudio 实时语音属于另一条可研究路线，会改变收听、生成和播放架构；当前先验证文字模型替换，避免同时更换多个环节后无法归因。

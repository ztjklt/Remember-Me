> 本页是relay阶段的实际记录；之后剩余6段通过Groq完成，最新结果见 [月度闭环核验](GROQ_LIVE_RESULTS_2026-10-08.md)。

# 10月8日：x666 云端语音接入与真实产品验证

工作区 D:/codex_work/remember-me-agent-loop，分支 codex/agent-integration。
不推送、不合并、不发布。密钥只读被 Git 忽略的服务端 .env。

## 实际链路

小米虚构人物原音 → FFmpeg 传输副本 → x666 ASR → 保存原始转写 → 已授权的非完美 ASR 技术确认 → 微信 Deepseek-v4-flash → 本地结构/证据校验 → 记忆、人物候选、来源问答、授权与撤权。

本轮未使用本地 Whisper。FFmpeg 只转换格式，不做识别。原始 WAV 始终保留，传输 MP3 与原音分别记录哈希、大小。创作原稿和 gold 答案未进入 ASR 请求。微信仍仅作文本处理。

## 连接实测

| 请求 | 结果 | 边界 |
|---|---|---|
| GET https://x666.me/v1/models | 200，15 个入口 | 存在不等于音频可用 |
| codestral-2508，input_audio，8/20 秒 WAV | 200，中文转写 | 小样可用 |
| mistral-code-fim-latest，8 秒 WAV | 200，中文转写 | 第二指定入口可用 |
| audio_url 字典格式 | 422 | 产品采用已验证 input_audio |
| 270.6 秒、约 13 MB WAV，codestral | 3 次 429，每次冷却 | 原始载荷失败；不能断言具体额度/大小原因 |
| 同一完整故事约 1.6 MB MP3，codestral | 200，约 13 秒 | 压缩传输有效，没有截短原音 |
| 同一完整故事 MP3，code-fim-latest | 200 | 完整样本可用，不代表批量稳定性已验收 |
| 431 秒公交第2段，压缩传输 | 200 | 有超过五分钟的实际样本 |

名称是中转返回的路由标识，不能独立证明底层模型身份或官方原生音频能力。产品默认 codestral-2508，不自动换模型或回退本地。

## 三人物小样闭环：已完成

运行目录 services/backend/var/monthly-eval/cloud-asr-runs/relay-compact/，与旧 Whisper 数据隔离。

| 人物 | 首段 Episode | 记忆 | 待确认人物候选 |
|---|---|---:|---:|
| 公交司机 | ep_2e3105ad327141bc | 23 | 3 |
| 消防员 | ep_fdb9bdc0be084801 | 21 | 3 |
| 人生回顾 | ep_4a3b740838fc4ccf | 24 | 3 |

共 68 条记忆、9 条候选、9 次真实问答（每人所有者已知、读者已知、未知密码问题）。未知密码均为 UNKNOWN；原音下载哈希一致；撤权后原音和此前读者答案均拒绝访问。候选不是本人认可的稳定人格。逐字证据对应 ASR，只证明文字来源一致，不证明听写正确。

## Android 实际运行

LiveCloudWorkbenchTest 在 emulator-5554 上通过：应用内登录 → 读取真实故事 → 打开公交原音 → 播放、暂停、继续、停止 → 退出清除播放器。通过 ADB 连接本机 8877，测试凭据临时放应用私有文件，结束删除。模型服务密钥不进 Android。

实际 UI 测试 1 项通过，18.8 秒。截图 services/backend/var/cloud-android-player.png，日志 cloud-android-live-test.log。此结果不代表实体手机、真人麦克风或人工听读通过。

## 实际失败与质量问题

1. 公交首段把“平安回家比多跑一趟重要”转为“平安回家，必多跑一趟中药”。问答继承错误：事实质量不通过，不能拿创作原稿偷偷修补 ASR。
2. 人名同音字和“妻子/棋子”有误识别；尾句完整性需听读核查。
3. 人生回顾首段提取超过原有最多 24 条约束失败。补充提示词上限后重试成功，Schema、引用、权限约束未放宽。
4. 一次 Twin 输出校验失败返回 503，没有答案记录；有记录的重试成功。旧响应未记录具体原因，不能臆断根因。现在补充不含正文的校验类型诊断。
5. 月度批次出现 HTTP 400 / upstream_error / 3051。部分同音频有界重试后成功；上游错误含义尚不明确，没有把所有 400 改为自动重试。
6. 公交第3段重复讲述两次提取均为空列表。保留全文并标质量问题，不生成假记忆，也不宣称正确去重已验证。修订故事若无有效记忆仍禁止确认。

## 月度扩充

执行 tools/monthly_eval/cloud_monthly.py --run relay-compact，从检查点按个人模拟日期推进。关联新首段真实 Memory ID；纠正要在实际新证据中找到旧年、新年及纠正含义，补充、变化分别处理。第4/7/10段私密；第9段读者提问，第10段本人回答未授权则不可见。

成功阶段不重复调用，失败历史不覆盖，含糊的 POST 结果不盲目重放。30 段及新 60 问的总结果在批次结束后补记，旧 Whisper 结果不计入本轮。

## 工程修复

- 压缩在跨进程串行门内执行，转换前和发出前复核授权。
- FFmpeg 仅允许本地格式/协议，120 秒超时，输出文件限 25 MiB；触及上限拒绝，不能发送可能已截断音频；不把无界输出收进 PIPE。
- 提取和问答校验只记录安全字段及错误类型，不记正文/密钥。
- 完整 ADD/SUPPORT/CONFLICT/CHANGE 人物状态机仍见 PEER_MEMORY_ADOPTION_2026-10-08.md；本轮不宣称已完整移植。

## 证据文件

- services/backend/var/cloud-asr/models.json、calls.jsonl：实际入口及请求。
- services/backend/var/monthly-eval/cloud-asr-probes/：两入口短/完整样本。
- relay-compact/followthrough-results.json：首段答案、候选、撤权结果。
- relay-compact/monthly-state.json、monthly-steps.json、recovery-steps.json：扩充与恢复。
- relay-first/：原始 WAV 失败历史，不能算成功样本。
- services/backend/var/cloud-final-tests.xml、cloud-ai-final-tests.xml：本轮确定性回归。

运行证据在被忽略的 var 下。身份文件含本机测试登录凭据，不应公开。

### 追加修复记录

- 明确提取提示词 v3 的 domain 与 memory_type 枚举，仍使用原有严格本地校验；不会静默映射非法类别或裁掉多余输出。
- 经两次同音频成功恢复验证，对 x666 独有的 HTTP400/upstream_error/3051 且不含额度/载荷拒绝提示的情况，交给原有三次任务预算处理。并非所有400重试；鉴权、余额、格式和无效输出仍明确失败。新规则已先复现失败后通过5个差异场景测试。
- 消防员第4段的自动结果选错证据句，严格纠正闸门拒绝确认。通过现有Owner记忆纠正接口逐字引用实际ASR的完整纠正句，替换一条记忆；删除另外10条引用不支持内容的结果，审计历史保留。原始ASR未变，创作稿/gold未输入。该条标为操作员协助修复，不算自动提取质量通过；证据类型为CALIBRATION，不伪称ORIGINAL。
- 早期人物采用文档已标注后续实现：4b1b4e3中Owner审核的四类更新规则实际存在；完整自动状态机仍未完成。

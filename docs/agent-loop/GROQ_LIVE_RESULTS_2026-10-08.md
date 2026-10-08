# Groq 接力与月度 Agent 闭环结果

2026-10-08，北京时间。本机分支 `codex/agent-integration`，目录 `D:/codex_work/remember-me-agent-loop`。没有修改饮食项目，没有 push / merge / publish。

## 当前结果

ASR 阻塞已解除。用户授权切换 Groq 后，已接入正式后台，并完成之前剩余的6段。三组各10段实际小米合成音频，全部经过真实云端转写、授权的技术核对与微信模型处理，能从网页与 Android 读取同一份结果。不是用创作文本替代 ASR。

|人物空间|录音处理|ASR来源|当前有效记忆|本轮人物候选|
|---|---|---|---:|---:|
|76岁公交司机|10/10 ready|10段 relay/codestral-2508|152|3 pending|
|32岁消防员|10/10 ready|7段 relay + 3段 Groq|130|3 pending|
|48岁人生回顾者|10/10 ready|7段 relay + 3段 Groq|165|3 pending|

合计447条有效记忆，另3条旧年份记忆为 superseded，历史保留。公交第03段返回合法空记忆结果，完整转写保留；不能把它称作成功的自动去重，29段实际产生非空记忆。人物候选是系统建议，未代本人确认或宣传稳定人格。

当前链路：真实原音 → Groq云端Whisper → 保留原始ASR与简体核对草稿 → 明确确认 → 微信Deepseek-v4-flash → 本地结构与引用校验 → Memory/Evidence保存 → 可见范围内的画像与问答 → 原音。

## ASR接入与失败恢复

- Groq固定官方 `https://api.groq.com/openai/v1/audio/transcriptions`，请求模型 `whisper-large-v3`；中文、multipart MP3、verbose_json，未提供文本原稿或标准答案。此 Whisper 在 Groq 运行，本机只做 ffmpeg 格式转换。
- 6个正式Groq录音请求均HTTP200；另有1个约270.56秒的独立全长探针成功。记录请求模型；响应未给出的模型身份、usage、finish_reason不编造。
- 24段已成功旧结果保留。旧渠道失败的两个08故事没有覆盖，在新policy、新幂等键下建立Groq任务，旧Episode与失败日志留下。
- 新旧云端授权不互通；队列等待后再次检查权限。缺密钥、拒绝、无效输出不换服务商。临时错误沿用最多三次任务预算。
- 消防员08首次微信提取发生字段缺失/非法枚举，严格校验拒绝；一次明确手动重试恢复。原ASR未重做，校验未放宽。
- 此前消防员04的来源错配曾通过Owner修订接口进行人工操作式修复：只采用实际ASR文字，保留失败与修复清单。不得称该段自动提取质量通过。
- 人物归纳提示更新为v4，要求中性称呼与证据限定。提取提示是source-selection-v4；修复今后新记忆误用通用prompt_version的问题。既有批次不倒改历史版本字段，真实提示SHA与调用日志继续作为运行依据。

配置在被忽略的server `.env`，`REMEMBER_GROQ_API_KEY`不进入Android、前端、Git或报告。当前主机经已有代理连Groq成功；直连403原因未归因。不启动本地STT 8878。详见[接入约定](GROQ_CUTOVER_2026-10-08.md)。

## 真实问答与修复

固定60问实际得到60个结果，共63次模型请求尝试，失败尝试保留。类型为13 ORIGINAL / 32 SIMULATION / 15 UNKNOWN。答案不是测试fixture。

助手离线读取回答和当前材料：33项所问要点有支持，23项仍需质量修正，4项漏答，见[逐题记录](QA_CLOUD_MONTHLY_2026-10-08.md)。来源范围、引用文字/类型、ORIGINAL逐字一致检查0错误。这不是对全部历史请求载荷的抓包审计，也不是人工听读或临床评估。

4项漏答为消防员q13私人备忘位置、q19静音原因，人生回顾q11同名人物、q16看海城市/日期未定。资料里“暂不分享”的历史叙述可能被模型误读为当前权限。Twin提示v3明确：服务端已过滤当前访问者权限，原文中的历史授权措辞不能用于再次隐藏已提供事实；不向模型补充任何私密材料。

随后单独跑12个针对性问题（保留原60问，不替换原结果）：

|检查|结果|
|消防员q13|恢复答出手机私人备忘位置；“灰伞/灰散”ASR错字仍在|
|消防员q19|恢复答出为完整听完唱片、免受提示音打断|
|人生回顾q16|恢复答出城市和日期尚未确定|
|人生回顾q11|仍UNKNOWN，尚未通过；Reader同题能区分，不能据此声称Owner也通过|
|读者私密/旧年份对照|继续UNKNOWN；未发现私密答案泄露|

12项复测的来源与权限机械检查同样0错误。7项所问要点有支持，4项有字形或措辞问题，1项失败。不是重新跑完整60问后的新准确率。姓名、地名、第一人称、性别代词、冗长原话和多余细节仍需打磨；人物候选中也存在ASR姓名误差与归纳情境超出所引证据的情况，继续pending。

## 产品与APP核验

- 全部30段经真实认证API取回原音，SHA256与素材原音一致；不等于人工听读通过。
- 三组读者各访问故事01（纠正后失效）和04/07/10（私密），共12次音频访问均404。三组Reader人物视图均为shared_stories_only，所有来源属于实际可见故事。
- 月度流程实际执行补充、年份纠正、过去/现在住址叙述、读者问题和私密回答。修订历史不删除；第10段在关联问题后不会自动分享。
- 发现并修复评测脚本消防员问题单与回答主题不符：原误问灰色本子，实际09/10是手机静音。旧问题标为declined并保留，独立Reader重新提交正确问题，Owner关联已核对的真实回答，Reader仍看不到未分享的回答录音。
- Android模拟器真实登录当前人物空间，打开最新Groq故事，调用实际MediaPlayer播放/暂停/继续/停止，再退出身份；1项仪器化测试通过（10.414秒）。另保留此前relay故事播放测试。新截图 `var/groq-android-player.png`。
- 测试APK成功构建；实际安装的主APK能消费同一后台。没有在本轮完成新的真人麦克风采集、实体Android设备或iOS验证。

确定性测试：Backend 353项通过；评测脚本23项通过（修复了新增模型元数据导致测试fixture缺字段的问题）；AI Core 173项通过；网页5项Node测试通过。新Groq适配/同意/队列/来源/错误检查包含在Backend中。没有把替身测试当作真实模型验收。

## 采纳的Agent结构与后续边界

沿用单个在线Twin、记忆整理、人物候选、校准与问题单，不新增互相聊天的Agent。共享后端负责事实、证据、修订与权限。

同学的ADD / SUPPORT / CONFLICT / CHANGE已在之前的本地提交4b1b4e3落实为Owner审核的人物更新资源，网页与Android有操作入口、历史和确认。自动判断语义重复、自动检测冲突、完整自动Trait状态机仍未完成，不能宣传成全部移植。此次没有代Owner确认9个人物候选。校准的锁定答案规则继续保留且有确定性回归，本批次没有新增真实校准音频验收。

当前可以继续由人操作核心闭环；不能宣布整体产品完全验收。剩余优先级：同名人物问答稳定性；实际听读并修正专名/关键否定；审核人物候选；实体手机麦克风、后台保存、断网重试和完整双身份流程。ASR渠道和API密钥不再是当前阻塞。

## 可复核产物

以下均相对 `services/backend`，数据文件在Git忽略目录内，无密钥输出：

- `var/monthly-eval/cloud-asr-runs/relay-compact/`：monthly-state、product-episodes、groq-cutover、monthly-verification、qa-text-review、qa-v3-recheck-review、audio-and-reader-scope-audit、question-repair-history/result/steps。
- `var/monthly-eval/qa-relay-compact-cloud-v1.json`：固定60问；`qa-groq-scope-v3-recheck.json`：独立12项复测。
- `var/groq-asr/calls.jsonl`：6个实际Groq任务调用；独立probe另存。旧relay调用与失败日志保留。
- `var/cloud-monthly-groq*.log`、`var/cloud-monthly-verification.log`、`var/groq-qa-scope-v3.log`：各阶段实际运行记录。
- `var/groq-ai-tests.xml`、`var/groq-eval-tests.xml`、`var/groq-web-tests.log`、`var/groq-android-live-test.log`：检查结果。`groq-regression.xml`保留最初353个Backend通过+1个评测fixture失败的现场；该评测修复后在23项脚本回归中通过，没有覆盖失败历史。

启动与六身份使用见[运行说明](RUNBOOK.md)。网页：`http://127.0.0.1:8877/workbench/`。Android APK：`apps/android/app/build/outputs/apk/debug/app-debug.apk`。

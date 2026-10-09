# 服务端转写、Android 与 Agent 实跑验收

核验日期：2026-10-09，北京时间。当前分支 `codex/agent-integration`，未 push/merge。ECS 新目录 `/opt/remember-me/releases/paraformer-20261009`，以前的 `b2f827b` 保留；PostgreSQL 和原音存储没有迁移或重置。

## 结论

Android 已通过公网 IP HTTPS 直接上传真实音频，由 ECS 完成 Paraformer V2 转写、核对等待、微信 DeepSeek 记忆整理与持久化，随后在 App 中播放来源、提问、查看人物视图。**本路径不再依赖电脑执行 ASR，也不使用 SSH/ADB 转发承载业务流量。** ADB 本次只负责安装包、操作模拟器及准备测试音频。

输入是此前实际经过 Android MediaRecorder 的19.622秒虚构语音录音；本轮从原生 App 再上传这份保留的录音，**不是重新完成一次真人麦克风录制，也不代表实体手机验收**。该素材早先来自小米合成语音与虚拟麦克风，不冒充真实患者或真人访谈。

## 真实结果

| 阶段 | 证据和结果 |
|---|---|
| 百炼连接 | ECS 请求工作空间原生上传策略、私有文件上传、Paraformer V2提交与结果下载均200；独立探针任务完成，服务报告处理19秒 |
| 新产品任务 | `ep_2ee5dafa9faa46b0`；百炼任务 `d9df58be-6024-49a3-ab3b-f67105d6b4c4`；`stt_model_version=bailian/paraformer-v2` |
| 核对门槛 | App 保存的核对前快照 `waiting_for_review=true`、`reviewed=false`、`memories=[]`、`model_version=null` |
| 实际纠错 | 机器稿末句“不是说所有情况下都不要正经”，技术核对仅将“正经”改为“挣钱”；机器稿保持不变，没有用整篇创作原稿覆盖 ASR；非人工听读验收 |
| 记忆整理 | 本人核对接口提交后，ECS 实际调用 `Deepseek-v4-flash`，保存3条带来源记忆，状态 ready；引用均逐字位于核对稿 |
| Android | `paraformerServerUploadReviewMemoryAndTwin` 通过，24.128秒；登录、转写核对、记忆回读、播放/暂停/定位、来源问答、四人物视图、退出清理会话 |
| 原音一致性 | ECS 回读与原始242586字节文件哈希一致：`a3589f8b3ce69eb2dc95545d5d4b668c3b457da8200314ae27695e2742edf3a3` |
| 只用新故事问答 | 独立读者只获本条故事，回答引用仅来自本条新来源；回答标为 SIMULATION，保留具体冲突情境与“并非任何时候都不要挣钱”的否定 |
| 未知问题 | 问“他第一次坐飞机是哪一年？”，真实模型链路返回 UNKNOWN，无伪造证据 |
| 人物候选 | 实际 profile 任务完成，得到2条当前 pending 候选，未自动确认。安全选择观察中，同一录音重复上传只计1个独立观察；另一条茶偏好由此前3段有效材料支持 |
| 授权/撤权 | 3轮真实请求：只见指定故事，原音哈希正确；每轮撤权后原音、故事、新问答均404。测试结束已撤销临时故事授权 |

App 中所有者问答可合法引用同一段话的旧有效来源，所以另外使用只获新故事的读者验证新来源链，未把所有者的旧来源回答冒称“仅用新数据”。问答与人物候选是读取核对过的材料生成，不是模型永久训练出了一个人格。

语义人工文本审阅（助手，非用户听读）：回答保留了条件、否定与来源。3条记忆中第二条“认为一家人平安回家比赚钱更重要”单独看时较宽泛，应在浏览时和原文情境一起呈现；本例不能证明普遍准确率。新人物归纳保留具体适用情境，仍由本人确认。

## 本轮发现的问题和修复

1. HTTPX INFO 日志可能记录临时签名 URL：已抑制 HTTPX/HTTPCore 请求级日志，保留脱敏的调用状态审计；捕获运行日志的测试先复现再通过。
2. 测试工具使用 ADB shell 标准输入复制二进制，文件截断为4175字节并导致 DECODE_ERROR：改为 ADB 文件同步，云端调用前校验哈希。失败 Episode `ep_4a015024ecf1414f` 和原失败任务保留，不算成功样本。
3. 百炼把提交的 `oss://` 文件标识解析成签名 HTTPS URL：改为核对上传时保存的主机及完全相同的对象路径，不比较两种形式的整串 URL；错误文件仍拒绝。已成功的同一个云任务恢复查询，没有重新提交收费任务。
4. 核对弹窗与页面存在两个 Compose 根节点，测试截图函数失败：修复测试截图选择器。这个失败发生于测试采集，不是转写或记忆失败，历史日志保留。

## 回归与实际模型证据分开

- Backend 完整测试：403 passed、3 skipped、3 warnings。3项跳过为需单独启用 PostgreSQL 环境的既有探针；不能把本轮 SQLite 回归当 PostgreSQL 并发全量复测。
- 新 Paraformer 14项边界检查包含未配置、原音传输、子任务失败、任务恢复、歧义提交禁止重复、撤权阻止提交、签名日志、核对等待及来源 URL 映射。外部网络使用测试替身；真实结果另记在上表。
- 网页云端上传规则4项通过；Android 原生单元测试39项、构建通过；lint 0 errors、34 warnings。
- Android 模拟器真实模型流程1项通过；本轮没有把 fixture 或规则提取冒充真实模型输出。
- 安装于模拟器的主 APK 哈希与交付包一致；ADB reverse 为空。交付 APK 解包及本轮源码对已知供应商密钥/测试密码的匹配均为0，不代替完整安全审计。
- 实体Android、iOS以及30段月度音频全部重新跑 Paraformer，均未在本轮执行。旧批次结果保持各自模型来源。

原始材料位于 Git 忽略目录 `services/backend/var/paraformer-20261009/`：`paraformer-before-review.json`、`paraformer-result.json`、`followthrough.json`、`android-test.log`、三次失败日志、`backend-final-junit.xml`、调用审计、截图、`delivery.json`。账号和供应商凭据不放入报告。

## 运行配置与恢复

ECS 的 `/etc/remember-me/api.env` 与 `worker.env` 使用：

```dotenv
REMEMBER_STT_BACKEND=paraformer
REMEMBER_PARAFORMER_BASE_URL=https://<北京工作空间主机>
REMEMBER_PARAFORMER_API_KEY=<仅在受限服务端配置>
REMEMBER_PARAFORMER_STATE_DIR=/var/lib/remember-me/paraformer-asr
REMEMBER_PARAFORMER_POLL_TIMEOUT_SECONDS=120
REMEMBER_STT_TIMEOUT_SECONDS=45
```

本次主机来自用户提供的百炼 workspace URL，实际 ASR 使用 `/api/v1/uploads`、`/api/v1/services/audio/asr/transcription` 与 `/api/v1/tasks/{task_id}`，不在 `/compatible-mode/v1` 后拼接音频接口。模型固定 `paraformer-v2`。请求路由可以确认，服务未单独返回底层模型版本，审计 `response_model=null`，不伪装身份验证。

百炼临时文件是私有副本，有效期48小时，客户端提示已补充；任务结果链接有效期24小时。密钥不进入 APK，下载结果的请求不带供应商 Bearer。原音、机器转写、核对稿各自保留。请求超时/限流受原任务三次尝试预算约束，不无限重试。提交响应丢失而无任务编号时需要管理者核查，避免自动重复创建收费任务。

替换比赛方 ASR 时：若协议相同，可换服务端配置；若鉴权、上传、流式或结果结构不同，需要新增适配器，不能保证“随便换 URL 和 key”就兼容。客户端继续使用同一业务接口和核对规则。

回退只恢复 `/opt/remember-me/current` 指向旧 `b2f827b`，并从 `/root/remember-me-paraformer-probe/env-backup/` 恢复本次 API/worker 配置后重启四个服务；先检查是否有后续变更。不要恢复旧数据库、删原音或清检查点。日常进服务器仍用 `ssh remember-me-ecs`。

## 使用与待验收

安装包：`output/remember-me-android-server-asr-20261009.apk`。

SHA256：`20e8d330db1a035fba818ed650f3ad56926022a26cbe64246fad66923e06cdf1`。

1. 手机与当前测试电脑使用相同公网出口，安装包默认连接 `https://39.108.183.47`，登录既有测试账号。
2. 在“今天”允许录音，完成后试听，勾选本次完整原音云端识别，再点“上传并等待核对”。新录音不再走电脑导出/导入；旧接力草稿仍保留其历史方式。
3. “档案”核对识别文字，必要时改字或另写补充，确认后查看记忆。“对话”提问并查看证据；“人物”阅读四视图及候选。

仍需实体手机验证麦克风权限、后台保存、重启、不同网络，以及 iOS 编译/设备联调。现有白名单仅当前出口 `183.6.9.111/32`，证书为测试包专用信任，到期2027-01-07；不能承诺任意网络或公开用户安装后直接可用。网络限制并非靠把供应商密钥放进手机解决。

完整用户旅程及两端后台分工见 [USER_JOURNEY_2026-10-09.md](USER_JOURNEY_2026-10-09.md)。

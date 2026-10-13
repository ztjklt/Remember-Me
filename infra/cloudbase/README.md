> 2026-10-14 当前 iOS 生产为 CloudRun023，源码 `codex/twin-chat-memory` / `6cb7c17`，包含默认声音通话和本人音色试听。源包成员须显式 0644，容器非 root 用户必须能读取启动与源码文件；本次修正记录见 `docs/verification/IOS_DEFAULT_VOICE_AND_READINESS_2026_10_14.md`。旧版本记录保留为历史。

> 2026-10-13 最新生产源码：`codex/twin-chat-memory` / `df7b22b`，CloudRun018，包含实时Voice和旧聊天长期记忆。迁移head为0020_chat_memory；后续发布从此基线继续。验证见 docs/verification/IOS_CHAT_MEMORY_2026_10_13.md。

# iOS 独立 CloudBase 内测后端

> 2026-10-13 当前生产源码在 `codex/ios-realtime-livekit`，已包含获准的连续会话、Twin 身份和实时声音接口。后续后端修改应先合入这份源码再发布，保留实时迁移、适配器及运行参数；下面早期“未部署声音克隆”段落是历史状态。验证见 [实时 Voice 记录](../../docs/verification/IOS_REALTIME_VOICE_2026_10_13.md)。

2026-10-12 用户决定：iOS 独立后端，使用其腾讯云 CloudBase 账号新建环境。这里只复用已经交付的 API 和适配器实现；iOS 的账号、数据库、原音、授权、密钥和任务都属于新环境。Android ECS 不迁移、不部署。共享客户端 Contract 无修改。

本次后台基线为 `origin/codex/team-handoff-20261010` 的 `a12354a`，包含普通账号、空间、核对文字、证据 Twin 和人物候选接口。原工作区未提交的 iOS 画像审核／AI 实验不在本部署源码中。环境创建、代码构建、真人端到端旅程分别报告。

## 计算与持久化

- 一个容器中只有两种 HTTP 进程：Backend 对外监听 `PORT`，AI Core 只监听容器内 `127.0.0.1:8100`。一个主模型后面保留已有 Schema worker。
- 不运行永久后台 worker。私人定时云函数每分钟调用受独立密钥保护的 `/internal/jobs/processing-tick` 和 `/internal/jobs/profile-tick`，每次请求同步完成一段工作。Backend 数据库 job lease 和本人核对门槛保留；只转写不会自动进入提取。
- 当前候选代码需要可通过 PostgreSQL 协议直连的数据库，保存应用账号、授权、原文、记忆、任务和向量缓存。用户已升级标准版及独享集群，原生 PostgreSQL 路线已确定；实例运行中，内网地址 `172.17.0.11:5432`，原生认证、证书链与主机校验，以及应用容器就绪均已实际通过。业务表使用私有 `remember_ios` Schema；连接强制 `verify-full`，禁止覆盖为明文或不校验证书。当前原文 RAG 使用 BGE CPU 编码、原生 pgvector 精确余弦排序及文字匹配；没有部署 ANN 索引。
- 使用此 PG 环境原生 Storage API 的私有桶 `remember-me-ios-audio` 保存原音和转写检查点。服务端专用 API Key 不进入客户端；对 `anon` 和 `authenticated` 配置 restrictive policy，阻止这个桶通过其他 permissive policy 暴露。存储适配器不跟随重定向、不把错误响应正文写入异常。S3 adapter 仍可作为另选部署方式。
- 2026-10-13 用户指定主 LLM 优先 DeepSeek V4 Flash，当前官方目录使用 `deepseek-flash`（旧 V4 Flash 别名由当前 Flash 模型提供服务）。该独立 Key 来自用户自己创建的 RM Key，只发到 `https://api.deepseek.com`。合成文本的真实提取、Twin 和人物候选均通过；这不是已部署 CloudBase 或手机验收的声明。本环境已由用户选定普通百炼 Paraformer V2，合成 WAV 与 AAC M4A 实际转写通过；此前 Anker Key 的 401 与未经验证的音频协议仅保留为历史。本人手机录音仍待试用者确认上传。TTS 别名不是本人声纹或已部署声音克隆。
- 同步 relay 在私有存储保存提交标记和成功的原始机器稿；冷替换读已有结果，结果不确定时拒绝重放原音。明确拒绝的 4xx／429 可以重新核对配置；超时、5xx、截断输出不暗中重放。读取缓存仍验证当前授权。默认 relay 本机行为不变，只有本部署选择持久化。
- Paraformer 在提交供应商任务之前先持久化 `submitting` 检查点；结果不确定或检查点不可读时不重新提交。冷启动会继续轮询已有任务。临时锁和诊断 JSONL 可丢失；原音、任务 checkpoint 和 Episode 结果不依赖容器临时盘。
- 为保持当前跨进程文件锁和供应商配额语义，首次内测最大副本 **1**，网关并发 **1**，新版本切换先停旧版本再启动新版本。不得直接改成并行蓝绿或多副本；多副本需要分布式 quota／检查点锁。
- 云端声音克隆尚未部署，不能把它标为可用。独立声音授权、provider seam 仍保留。

## CloudBase 控制台准备

环境名称 `remember-me-ios`，环境 ID `remember-me-ios-d5f9twwlcae71c69`，上海，PostgreSQL。最初通过兑换码创建免费体验环境；用户随后自行升级标准版，并接受及提交数据库独享升级。2026-10-12 配置页确认实例 `postgres-drasbama` 已运行，1 核／2 GiB／20 GB，每小时 352 点（30 天约 253,440 点）。数据库公网入口未启用。原生数据库密码已由用户在控制台重置，随后按其明确要求保存至本机 ignored 私密配置；不进入源码。用户已自行确认 CloudBase 与 CODING 协议，云托管已开通，应用服务已于 2026-10-13 上线。非敏感身份记录在 `ENVIRONMENT.json`。

云托管、网络、存储与模型调用用量仍需实际核算，不能把标准套餐或数据库点数当作全部后端费用；未开启超限按量或新增付费网络产品。

1. 创建独立 PostgreSQL 数据库／Schema 和专用数据库角色，连接串必须开启适合该环境的 TLS，不使用 Android 的数据库地址或账号。确认服务到数据库的私网／受控连接及迁移权限。
2. 私有 CloudBase Storage 桶和 restrictive policy 已创建，真实 put/get/delete readiness 已通过；匿名读取现存测试文件返回 404。后端专用 Key 有效期 30 天，需要在到期前轮换；所有测试对象已删除。此 Key 不能用于客户端，也不能当作 S3 密钥。
3. 在服务端 secret 配置中填入 `.env.example` 的空字段，ASR 与 LLM 使用用户自己的独立凭据；不从队友 ECS 导出密钥，不把密钥放进源码／镜像／手机／聊天。拿到服务地址后配置 `REMEMBER_ALLOWED_HOSTS` JSON，包含实际 hostname 与本机地址；默认仅接受本机 Host。内部定时请求另用随机至少 32 字符的凭据。
4. 仅在直连数据库配置可用时部署此候选容器，监听端口 8000，最小副本可为 0，最大副本 1，模型调用并发为 1（未验证网关并发配置为 1）；先选测试期实际允许且预算批准的 CPU／内存规格。Dockerfile 设计为构建时下载指定 revision 的 CPU BGE，运行时离线加载；本机曾因磁盘错误失败；后续腾讯云远端已成功构建并推送，不能将两者混为本机构建成功。平台默认 hostname TLS。
5. **迁移是单独步骤**。本次已用 Alembic PostgreSQL 离线 SQL，通过官方 ExecutePGSql 管理接口在单个事务代码块中迁移空 `remember_ios` Schema；初始 head `0016_share_invitations` 和 34 张表已另行查询确认；原文 RAG 增量升级至 `0017_evidence_chunks` / 35 张表。后续用同一镜像执行 `migrate`，普通 API 启动不自动创建表／跑迁移。未复制或重置 Android 数据。
6. 执行 `account-create 新用户名 昵称`，密码由管理员交互输入。此命令只创建新账号及其 owner 空间，不默认签署 RECORDING、CLOUD_TWIN 或 VOICE，不打开公开注册，不重置现有用户。
7. 部署 `timer/index.py` 为 Python 定时函数，入口 `index.main_handler`，超时至少 120 秒，定时每分钟触发，不开启 HTTP 入口；配置新服务 HTTPS origin 与同一 `CLOUDBASE_WORKER_TOKEN`。它拒绝重定向，不输出凭据，重叠 tick 返回 409。
8. `/health` 为存活检查，`/ready` 必须确认 PostgreSQL／私有存储。验证普通 Actor token 无法调用 `/internal/jobs/*`；AI 的 8100 不对外开放。确认定时器在手机退出后仍能推进转写，并观测超过一分钟的处理中状态。

源码 bundle：

```bash
python3 infra/cloudbase/package.py build/ios-cloudbase-context
docker build --platform linux/amd64 -t remember-me-ios-cloudbase:20261012 build/ios-cloudbase-context
```

bundle 同时生成 zip 和 tar.gz，仅复制白名单目录，包含内容哈希清单；不包含 iOS、Android、录音、数据库、`.env`、私密证书或密钥、模型凭据或用户样本；公开的 PostgreSQL CA `.crt` 是明确的运行时例外。`Dockerfile.dockerignore` 只保证新 BuildKit 的完整 checkout 构建；旧 Docker builder 必须用最小 bundle。为降低磁盘消耗，uv 安装不保留下载缓存；不再在磁盘紧张的 Mac 上重新构建大镜像。

## 网关与手机适配待验收

官方云托管限制列为请求 60 秒、包体 20 MB。Backend 把原音上限降到 18 MiB，预留 multipart 开销；大段原音仍需手机保留／拆分或另行提出直传 Contract。模型与定时函数超时设置只是单次调用边界，某些 Twin 验证有多次模型调用，不能由它推断总耗时小于网关限制；真实压力与长材料测试必须确认，不能先声称无限时对话。

当前已装 iOS ECS 包固定旧地址及测试证书。必须在拿到并验证新服务 origin 后，修改 iOS 的环境配置以使用新 hostname 的系统 TLS，再验证登录、空空间、上传、核对、提取、Twin 来源；**不要**复用 Android ECS 的证书 pin，也不要关闭 TLS。

人物任务若在容器退出时停在 running，沿用“明确重试，不暗中重放模型调用”原则，检查后台记录后将中断状态告知用户；新环境目前未验证该恢复操作，不自动把所有 running 任务改掉。更完整的任务 lease 与流式 Twin 超时方案另行准备。

## 验证记录

本地执行结果记录于 `docs/verification/IOS_CLOUDBASE_BACKEND_2026_10_12.md`。官方参考：

- [Python／容器云托管](https://docs.cloudbase.net/run/introduction)
- [无状态、请求内 CPU、监听 PORT](https://docs.cloudbase.net/run/develop/developing-guide)
- [包体、超时与按量限制](https://docs.cloudbase.net/run/limitation)
- [CloudBase PostgreSQL + pgvector](https://docs.cloudbase.net/recipes/add-rag-with-pgvector-cloudbase)
- [COS 支持 S3 API](https://cloud.tencent.com/document/faq/436/50743)

## 当前权限与凭据待处理

CloudBase SQL 管理与原生存储已可调用。原生 PostgreSQL 的账号创建、账号查询、SSL 读取／修改 API 曾返回 `OperationDenied.CamDeniedError`；没有成功创建 `remember_ios_app` 角色。2026-10-13 控制台已确认强制 SSL 开启，下载了腾讯云 PostgreSQL 官方 CA。按用户明确要求，将其数据库密码填入本次 worktree 的 ignored 私密配置，并加入 CA；不打包、不提交、不回显。临时 Event 云函数在数据库同 VPC 中完成密码认证、证书链和服务器身份验证，读取到 34 张业务表及 head `0016_share_invitations`。随后不含凭据的 Python 云托管检查容器也通过数据库 TLS 校验、DeepSeek 公网目录可达检查（无 Key 返回 401），所选 VPC + 平台默认出口路径无需新增 NAT。两项临时检查资源已清理。这证明原生直连及网络可用，尚不代表应用容器或手机闭环已上线。

## 赛事模型适配与验证

用户提供主办方分配的共用模型 Key 和[接入文档](https://anker-in.feishu.cn/docx/HAtJdgo45otz2Px31bYcu3PDnRf)。在 Safari 直接读取文档，确认 Base URL `https://ai-router-cn-pub.anker-in.com`、`/chat/completions` 和 Bearer 认证；没有向猜测的其他平台发送该 Key。只发送了一条不含个人数据的 JSON 测试请求，Qwen 路由返回 401；随后读取同主机的模型目录也返回 401。未发送原音、个人记忆或生成语音请求。需要确认赛事 Key 的激活／有效期／权限；当前没有切换客户端或部署未经验证的服务。

新 `anker` AI adapter 复用原有源编号选择、原话回填、引用验证、人物候选和校准协议，保留真实响应模型身份；它只接受文档列出的 HTTPS host 和别名，拒绝重定向、缺模型身份、坏 JSON、截断输出及认证失败。不是将平台 Key 当作 DeepSeek 官方或百炼原生 Key。

## 2026-10-13 Token Plan 凭据核对

用户补充自购 Token Plan 个人版凭据与官方端点。只读模型目录返回 200、16 个条目，未发送模型推理或录音请求。该凭据与赛事 Key 分开存放，仅在本机 ignored 私密目录，不加入应用运行环境。官方个人版使用范围明确排除自定义应用后端及自动化脚本；应用路径仍等待普通按量 API 凭据（或有效赛事凭据）与对应费用授权。部署启动校验拒绝把 `sk-sp-` 工具套餐 Key 发到应用模型／ASR供应商，定向部署测试 16 项通过，2 条上游弃用提醒。

Safari 已打开北京默认业务空间的普通 API Key 创建表单，尚未提交；观察到专属端点 `https://ws-5hudj5uvce12kiug.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。没有创建、重置或导出用户既有 API Key，没有执行其 Token Plan 工具安装脚本，也没有修改用户全局编程工具配置。

- [Token Plan 个人版使用范围](https://help.aliyun.com/zh/model-studio/token-plan-personal-overview)
- [普通百炼 API Key](https://help.aliyun.com/zh/model-studio/get-api-key/)
- [按量预算管理](https://help.aliyun.com/zh/model-studio/budget-management)

## 2026-10-13 DeepSeek Flash 接入

用户随后提供自己在 DeepSeek 官方平台创建的 RM Key，并选择 Flash 路线；不再把百炼按量作为已经获费用授权的默认路线。Key 归属在控制台确认，官方模型目录返回 200，当前列出的 Flash ID 为 `deepseek-flash`。记忆提取和 Twin 沿用原有适配器，人物候选／已有 Schema worker 接入同一个主模型；共享有界 JSON transport 与供应商固定目标验证，保留本人确认门槛和证据编号映射。

用虚构文字真实执行：提取返回 200（0.77 秒），2 条记忆及 2 条证据；Twin 返回 200（0.60 秒），引用存在，原话保留尚未决定报名的意思；人物候选返回 200（0.94 秒），1 项候选，所有引用属于输入。均记录实际响应模型 `deepseek-flash`。没有发送个人记录或原音。定向 AI 回归 74 项通过，2 条上游弃用提醒。结果在 ignored `build/deepseek-*-live-probe-20261013.json`。原生数据库密码／CA／直连的后续验证见“当前权限与凭据待处理”；后续 ASR、应用容器和手机交付结果见文末已上线状态。

[官方 Flash 模型与旧别名说明](https://api-docs.deepseek.com/quick_start/pricing/)

## 2026-10-13 普通百炼语音识别

用户选定普通按量百炼 ASR，并提供自行创建的工作空间 Key。当前候选使用 `paraformer-v2`，固定北京 workspace HTTPS origin，不含 compatible-mode 路径；Key 只保存在后端私密配置。适配器兼容现行 `ws-` 与既有 `llm-` 工作空间域名。真实合成中文音频 6 秒、3.7 秒完成转写且内容一致；定向回归 38 项通过。该结果仅覆盖供应商适配器，CloudBase 应用容器和手机闭环另验。

远端初次应用构建未产出镜像，终止本次尚未上线的构建任务后改为已在腾讯云成功使用的 `python:3.12-slim`，通过 PyPI 安装固定 `uv==0.12.18`（版本目录已核实）；继续使用冻结 lock 和 CPU retrieval 依赖。并不由这项改动推断完整应用构建已成功。

## 2026-10-13 已上线状态

独立 `remember-ios-api` 已部署，origin 与实际就绪信息见 `ENVIRONMENT.json`，当前 release 为 `ios-cloudbase-173f3ff`。数据库和私有存储 ready；真实合成语音已经走通上传、待核对、DeepSeek Memory、带原文证据的 Twin、原音读取与匿名拒绝。语音提问及 AAC M4A 都通过。每分钟 Event worker 已启用，并实际把待处理的人物候选任务推进为 complete。未开通额外 NAT、EIP 或 CLS。

账号 `jitian` 为独立空间，初始密码只保存在本机 `build/private/ios-internal-account.json`。本人权限由手机自行确认，测试使用另一个虚构账号。iPhone 已安装并启动 iOS 1.2.1 / 2026101301；真人录音旅程仍待使用者实测，云端声音克隆没有部署。详细结果以 dated verification 为准，前文未完成状态是各时间点的历史记录。


## 2026-10-13 原文 RAG / Nuwa 首版交付

代码 c2e8af7 远端镜像构建与 release task 均完成，remember-ios-api-004 已接收 100% 流量。service-info 确认 ios-cloudbase-c2e8af7；ready 确认 database / object_store 为 ok。原文向量表是 PostgreSQL public.vector，已在隔离合成账号实际写入三个 512 维、指定 BGE revision 的片段；迁移前后的录音 2 / 记忆 4 没变。

真实搜索“明天准备去哪里阅读？”返回图书馆原文，包括一个非 MemoryItem 的 episode: 原文命中；Twin 返回 ORIGINAL 和一项所属录音证据。无来源的护照号码问题返回 UNKNOWN；不携带登录 Cookie / Bearer 的全新客户端返回 401。缓存后的两次查找 0.17 / 0.16 秒、一次 Twin 0.98 秒，仅是这个短合成例子的热缓存结果，不是全库性能保证。检索范围、失效边界及测试结果见 [设计记录](../../docs/architecture/evidence-rag-nuwa.md)。

现有每分钟 Event worker 实际将新人物候选任务推进为 complete，产生一条 profile-proposals-nuwa-v5 / pending 候选，仍待本人决定。旧 v4 候选保留；没有自动确认或改写本人理解。新方法的小样本 A/B 没有证实总体忠实度优于 baseline。

iOS 已覆盖安装 1.3.1 / 2026101304，中文记忆页新增描述搜索与原文回看；锁屏阻止了自动打开，需要本人解锁或打开 App。未卸载或清空数据。真人新录音旅程及人物理解质量仍待真实使用反馈；云端声音克隆未部署。


## 2026-10-13 本人反馈与正式问答复核

当前 remember-ios-api-006 / ios-cloudbase-173f3ff 已完成 release task 并上线；ready 的 database / object_store 均为 ok。正式 DeepSeek 问答已实际接入 GroundedTwin / twin-points-v7 的生成与语义复核，而非此前的单次 DeepSeekTwinProvider。新答案使用 t7e2: 的不透明依据版本；旧未经过此路径的答案会过期，原文与已确认人物记录保留。

隔离合成账号实走：有来源 Twin 预测先锁定 → 上传 16 kHz 合成语音 → 普通百炼 ASR → 核对文字 → 记忆处理 → DeepSeek 比较五个维度 → 再问不同的条件问题。补充“时间紧留在家里”的原文之后，条件题由 UNKNOWN 变成有新录音证据的 ORIGINAL。只说明原文反馈被使用，不代表人格预测提升。

表达测试曾发现旧路由将明天计划概括为“通常”；已接通正式证据复核、加入情境限制并修正官方 JSON 模式提示词要求，真实重测保留这次计划与时间紧的条件。当前云端验证返回 SIMULATION / available 表达；创建校准后 locked_answer 等于手机展示的措辞。旧表达答案读取为 stale，无证据或可用 expression。所有自动确认仅操作合成 QA 账号，不替真实本人审核。

Backend 516 passed / 6 skipped，AI Core 285 passed，iOS 本轮 13 个 ECSConnectionTests + 6 个 SimpleFlowUITests 通过。iOS 1.3.2 / 2026101305 已覆盖安装；锁屏仍阻止自动启动。长期盲评趋势和真人相似度提升尚未验证。当前真实账号已有 CLOUD_TWIN 授权，但本轮未替用户发起个人选择测试或确认理解，等待其先给问题。方法、保留限制和诊断记录见 [相似度反馈设计](../../docs/architecture/twin-fidelity-feedback.md)。

## 2026-10-13 实时 Twin 语音增量

本人已选择 LiveKit Cloud 与普通百炼 CosyVoice，并授权创建及部署专用后端凭据。新接口、迁移 `0019_realtime_voice`、请求期间的 ASR/TTS 代理和撤销维护见 [实时方案](../../docs/architecture/realtime-twin-voice-contract-proposal.md)；常驻语音 Agent 位于 LiveKit Cloud，而 CloudBase 继续提供授权和经证据验证的 Twin。

平台环境变量总长限制为 5 KiB；公开的腾讯 PostgreSQL CA 链已作为 runtime 的 `.crt` 文件打包，启动仍强制 `verify-full`，不会关闭 TLS 或主机名校验。已有 PEM 配置仍可优先使用。镜像增加 FFmpeg 用于验证专用样本的实际时长和音量。未扩大既有网络或副本配置。实时迁移是增加两张表，未重置用户数据。

本轮检查旧部署参数时发生凭据进入工具输出的失误；用户选择稍后自行轮换旧凭据。需要一起更新数据库密码、百炼 ASR/CosyVoice Key、DeepSeek Key、CloudBase 私有存储 Key、CloudBase 定时任务 token；token 在 API 与 timer 必须一致。新生成的 LiveKit Secret 未回显。详细部署及验证状态以新 dated report 为准。


云托管代理后的 WebSocket 使用业务心跳保活：每秒重新检查通话本人、凭据和授权，再发心跳；完整识别问题提交前另行验证。Uvicorn 明确选择 wsproto，协议 Ping interval 为 0，避免网关处理控制帧时触发 40 秒 Ping 超时。识别端只向 Twin 提交完整句子，不为每个逐字中间结果执行一组 SQL。LiveKit Agent 独立读取本人麦克风，SDK 负责 VAD 和播放；短暂识别断流在重新验证授权后有限重连，不重放已消费音频。

当前已验证发布为 `remember-ios-api-016`（100% 流量，release `ios-realtime-1475135761e6`）。RTC 识别采用无损 WebSocket 压缩与 100 ms PCM 批次；发送前推进时钟，避免网络等待重复补零。超过两秒的发送阻塞或已排队实时帧延迟会结束识别。跨 Mumbai／上海网络曾在初始授权发生 ConnectTimeout；该次启动失败保留于验证记录，不能由 Agent Running 推断每次连接成功。

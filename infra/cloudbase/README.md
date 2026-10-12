# iOS 独立 CloudBase 内测后端

2026-10-12 用户决定：iOS 独立后端，使用其腾讯云 CloudBase 账号新建环境。这里只复用已经交付的 API 和适配器实现；iOS 的账号、数据库、原音、授权、密钥和任务都属于新环境。Android ECS 不迁移、不部署。共享客户端 Contract 无修改。

本次后台基线为 `origin/codex/team-handoff-20261010` 的 `a12354a`，包含普通账号、空间、核对文字、证据 Twin 和人物候选接口。原工作区未提交的 iOS 画像审核／AI 实验不在本部署源码中。环境创建、代码构建、真人端到端旅程分别报告。

## 计算与持久化

- 一个容器中只有两种 HTTP 进程：Backend 对外监听 `PORT`，AI Core 只监听容器内 `127.0.0.1:8100`。一个主模型后面保留已有 Schema worker。
- 不运行永久后台 worker。私人定时云函数每分钟调用受独立密钥保护的 `/internal/jobs/processing-tick` 和 `/internal/jobs/profile-tick`，每次请求同步完成一段工作。Backend 数据库 job lease 和本人核对门槛保留；只转写不会自动进入提取。
- 当前候选代码需要可通过 PostgreSQL 协议直连的数据库，保存应用账号、授权、原文、记忆、任务和向量缓存。用户已升级标准版及独享集群，原生 PostgreSQL 路线已确定；实例运行中，内网地址 `172.17.0.11:5432`，云托管与数据库的实际连通仍待验证。业务表使用私有 `remember_ios` Schema；连接强制 `verify-full`，禁止覆盖为明文或不校验证书。当前检索依旧是 BGE CPU 编码与 Python 排序，向量列是 JSON；没有声称已切换 pgvector ANN 索引。
- 使用此 PG 环境原生 Storage API 的私有桶 `remember-me-ios-audio` 保存原音和转写检查点。服务端专用 API Key 不进入客户端；对 `anon` 和 `authenticated` 配置 restrictive policy，阻止这个桶通过其他 permissive policy 暴露。存储适配器不跟随重定向、不把错误响应正文写入异常。S3 adapter 仍可作为另选部署方式。
- 2026-10-13 用户指定主 LLM 优先 DeepSeek V4 Flash，当前官方目录使用 `deepseek-flash`（旧 V4 Flash 别名由当前 Flash 模型提供服务）。该独立 Key 来自用户自己创建的 RM Key，只发到 `https://api.deepseek.com`。合成文本的真实提取、Twin 和人物候选均通过；这不是已部署 CloudBase 或手机验收的声明。转写供应商依然开放：此前 Anker Key 认证返回 401，其 ASR 音频协议尚待真实验证，当前不发送手机原音。TTS 别名不是本人声纹或已部署声音克隆。
- 同步 relay 在私有存储保存提交标记和成功的原始机器稿；冷替换读已有结果，结果不确定时拒绝重放原音。明确拒绝的 4xx／429 可以重新核对配置；超时、5xx、截断输出不暗中重放。读取缓存仍验证当前授权。默认 relay 本机行为不变，只有本部署选择持久化。
- Paraformer 在提交供应商任务之前先持久化 `submitting` 检查点；结果不确定或检查点不可读时不重新提交。冷启动会继续轮询已有任务。临时锁和诊断 JSONL 可丢失；原音、任务 checkpoint 和 Episode 结果不依赖容器临时盘。
- 为保持当前跨进程文件锁和供应商配额语义，首次内测最大副本 **1**，网关并发 **1**，新版本切换先停旧版本再启动新版本。不得直接改成并行蓝绿或多副本；多副本需要分布式 quota／检查点锁。
- 云端声音克隆尚未部署，不能把它标为可用。独立声音授权、provider seam 仍保留。

## CloudBase 控制台准备

环境名称 `remember-me-ios`，环境 ID `remember-me-ios-d5f9twwlcae71c69`，上海，PostgreSQL。最初通过兑换码创建免费体验环境；用户随后自行升级标准版，并接受及提交数据库独享升级。2026-10-12 配置页确认实例 `postgres-drasbama` 已运行，1 核／2 GiB／20 GB，每小时 352 点（30 天约 253,440 点）。数据库公网入口未启用。原生数据库密码已由用户在控制台重置，未传入聊天或源码。用户已自行确认 CloudBase 与 CODING 协议，云托管已开通，应用服务尚未部署。非敏感身份记录在 `ENVIRONMENT.json`。

云托管、网络、存储与模型调用用量仍需实际核算，不能把标准套餐或数据库点数当作全部后端费用；未开启超限按量或新增付费网络产品。

1. 创建独立 PostgreSQL 数据库／Schema 和专用数据库角色，连接串必须开启适合该环境的 TLS，不使用 Android 的数据库地址或账号。确认服务到数据库的私网／受控连接及迁移权限。
2. 私有 CloudBase Storage 桶和 restrictive policy 已创建，真实 put/get/delete readiness 已通过；匿名读取现存测试文件返回 404。后端专用 Key 有效期 30 天，需要在到期前轮换；所有测试对象已删除。此 Key 不能用于客户端，也不能当作 S3 密钥。
3. 在服务端 secret 配置中填入 `.env.example` 的空字段，ASR 与 LLM 使用用户自己的独立凭据；不从队友 ECS 导出密钥，不把密钥放进源码／镜像／手机／聊天。拿到服务地址后配置 `REMEMBER_ALLOWED_HOSTS` JSON，包含实际 hostname 与本机地址；默认仅接受本机 Host。内部定时请求另用随机至少 32 字符的凭据。
4. 仅在直连数据库配置可用时部署此候选容器，监听端口 8000，最小副本可为 0，最大副本 1、并发 1；先选测试期实际允许且预算批准的 CPU／内存规格。Dockerfile 设计为构建时下载指定 revision 的 CPU BGE，运行时离线加载；当前本机镜像构建因磁盘错误失败，不能写成已通过。平台默认 hostname TLS。
5. **迁移是单独步骤**。本次已用 Alembic PostgreSQL 离线 SQL，通过官方 ExecutePGSql 管理接口在单个事务代码块中迁移空 `remember_ios` Schema；真实 head `0016_share_invitations` 和 34 张表已另行查询确认。后续用同一镜像执行 `migrate`，普通 API 启动不自动创建表／跑迁移。未复制或重置 Android 数据。
6. 执行 `account-create 新用户名 昵称`，密码由管理员交互输入。此命令只创建新账号及其 owner 空间，不默认签署 RECORDING、CLOUD_TWIN 或 VOICE，不打开公开注册，不重置现有用户。
7. 部署 `timer/index.py` 为 Python 定时函数，入口 `index.main_handler`，超时至少 120 秒，定时每分钟触发，不开启 HTTP 入口；配置新服务 HTTPS origin 与同一 `CLOUDBASE_WORKER_TOKEN`。它拒绝重定向，不输出凭据，重叠 tick 返回 409。
8. `/health` 为存活检查，`/ready` 必须确认 PostgreSQL／私有存储。验证普通 Actor token 无法调用 `/internal/jobs/*`；AI 的 8100 不对外开放。确认定时器在手机退出后仍能推进转写，并观测超过一分钟的处理中状态。

源码 bundle：

```bash
python3 infra/cloudbase/package.py build/ios-cloudbase-context
docker build --platform linux/amd64 -t remember-me-ios-cloudbase:20261012 build/ios-cloudbase-context
```

bundle 同时生成 zip 和 tar.gz，仅复制白名单目录，包含内容哈希清单；不包含 iOS、Android、录音、数据库、`.env`、证书、模型密钥或用户样本。`Dockerfile.dockerignore` 只保证新 BuildKit 的完整 checkout 构建；旧 Docker builder 必须用最小 bundle。为降低磁盘消耗，uv 安装不保留下载缓存；不再在磁盘紧张的 Mac 上重新构建大镜像。

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

CloudBase SQL 管理与原生存储已可调用。当前 CLI 登录授权调用独立 PostgreSQL 的账号创建、账号查询、SSL 读取／修改 API 返回 `OperationDenied.CamDeniedError`；没有成功创建 `remember_ios_app` 角色，没有获得实例 CA。SQL 查询 `ssl` 为 on，但并不等于后端已通过证书验证或获得直连能力。控制台的 SSL 强制开关也未观察到开启。保留严格 TLS 连接要求，待核对该环境支持的 CA／原生连接配置。数据库密码和供应商 Key 由用户填写本次 worktree 的 `build/private/credentials.json`，不打包、不提交、不回显。

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

用虚构文字真实执行：提取返回 200（0.77 秒），2 条记忆及 2 条证据；Twin 返回 200（0.60 秒），引用存在，原话保留尚未决定报名的意思；人物候选返回 200（0.94 秒），1 项候选，所有引用属于输入。均记录实际响应模型 `deepseek-flash`。没有发送个人记录或原音。定向 AI 回归 74 项通过，2 条上游弃用提醒。结果在 ignored `build/deepseek-*-live-probe-20261013.json`。原生数据库密码仍未填入本机连接配置，CA／直连及 ASR 仍待验证，容器服务和手机尚未切换。

[官方 Flash 模型与旧别名说明](https://api-docs.deepseek.com/quick_start/pricing/)

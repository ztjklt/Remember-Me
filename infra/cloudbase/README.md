# iOS 独立 CloudBase 内测后端

2026-10-12 用户决定：iOS 独立后端，使用其腾讯云 CloudBase 账号新建环境。这里只复用已经交付的 API 和适配器实现；iOS 的账号、数据库、原音、授权、密钥和任务都属于新环境。Android ECS 不迁移、不部署。共享客户端 Contract 无修改。

本次后台基线为 `origin/codex/team-handoff-20261010` 的 `a12354a`，包含普通账号、空间、核对文字、证据 Twin 和人物候选接口。原工作区未提交的 iOS 画像审核／AI 实验不在本部署源码中。环境创建、代码构建、真人端到端旅程分别报告。

## 计算与持久化

- 一个容器中只有两种 HTTP 进程：Backend 对外监听 `PORT`，AI Core 只监听容器内 `127.0.0.1:8100`。一个主模型后面保留已有 Schema worker。
- 不运行永久后台 worker。私人定时云函数每分钟调用受独立密钥保护的 `/internal/jobs/processing-tick` 和 `/internal/jobs/profile-tick`，每次请求同步完成一段工作。Backend 数据库 job lease 和本人核对门槛保留；只转写不会自动进入提取。
- 当前候选代码需要可通过 PostgreSQL 协议直连的数据库，保存应用账号、授权、原文、记忆、任务和向量缓存。已创建的免费共享集群没有控制台可用的直连地址，不能直接部署此候选；待用户决定采用原生 HTTP／事务函数适配，或提供独立直连数据库。当前检索依旧是 BGE CPU 编码与 Python 排序，向量列是 JSON；没有声称已切换 pgvector ANN 索引。
- 独立私有 COS 桶保存原音与 Paraformer 任务检查点。COS 的 S3 兼容接口复用现有 adapter；服务端配置 `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`（临时凭据另带 `AWS_SESSION_TOKEN`），均只授权本桶的 put/get/head/delete。
- Paraformer 在提交供应商任务之前先持久化 `submitting` 检查点；结果不确定或检查点不可读时不重新提交。冷启动会继续轮询已有任务。临时锁和诊断 JSONL 可丢失；原音、任务 checkpoint 和 Episode 结果不依赖容器临时盘。
- 为保持当前跨进程文件锁和供应商配额语义，首次内测最大副本 **1**，网关并发 **1**，新版本切换先停旧版本再启动新版本。不得直接改成并行蓝绿或多副本；多副本需要分布式 quota／检查点锁。
- 云端声音克隆尚未部署，不能把它标为可用。独立声音授权、provider seam 仍保留。

## CloudBase 控制台准备

环境名称 `remember-me-ios`，环境 ID `remember-me-ios-d5f9twwlcae71c69`，上海，PostgreSQL。免费体验版通过用户输入的兑换码购买，6 个月、订单实付 0 元，附加商品未选。数据库配置页显示共享集群，版本 PostgreSQL 17.11，内网地址为 `-`，外网开关不可操作。升级入口要求先升级标准版（页面标价 ¥199/月），尚未提交。用户已自行确认 CloudBase 与 CODING 协议，云托管已开通，但应用服务尚未部署。以 `ENVIRONMENT.json` 记录非敏感环境身份，按用户后续部署路线继续。

需要确认本账号免费环境是否允许容器云托管。官方文档对旧云托管按量与新资源点有不同说明，以控制台实际能力和报价为准；环境已创建不代表云托管也免费。若要求升级／开启超限按量，先向用户展示实际套餐和计算费用后再操作。

1. 创建独立 PostgreSQL 数据库／Schema 和专用数据库角色，连接串必须开启适合该环境的 TLS，不使用 Android 的数据库地址或账号。确认服务到数据库的私网／受控连接及迁移权限。
2. 创建独立 `remember-me-ios-*` **私有** COS 桶和仅此桶的服务端凭据。不要将 CloudBase 前端身份 token 当作 COS 的 S3 密钥。先运行真实 COS put/get/delete readiness。
3. 在服务端 secret 配置中填入 `.env.example` 的空字段，ASR 与 LLM 使用用户自己的独立凭据；不从队友 ECS 导出密钥，不把密钥放进源码／镜像／手机／聊天。内部定时请求另用随机至少 32 字符的凭据。
4. 仅在直连数据库配置可用时部署此候选容器，监听端口 8000，最小副本可为 0，最大副本 1、并发 1；先选测试期实际允许且预算批准的 CPU／内存规格。Dockerfile 设计为构建时下载指定 revision 的 CPU BGE，运行时离线加载；当前本机镜像构建因磁盘错误失败，不能写成已通过。平台默认 hostname TLS。
5. **迁移是单独步骤**。在同一镜像、同一 secret 配置中执行 `migrate`；普通 API 启动不自动创建表／跑迁移。此环境是空数据库，不复制或重置 Android 的数据。
6. 执行 `account-create 新用户名 昵称`，密码由管理员交互输入。此命令只创建新账号及其 owner 空间，不默认签署 RECORDING、CLOUD_TWIN 或 VOICE，不打开公开注册，不重置现有用户。
7. 部署 `timer/index.py` 为 Python 定时函数，入口 `index.main_handler`，超时至少 120 秒，定时每分钟触发，不开启 HTTP 入口；配置新服务 HTTPS origin 与同一 `CLOUDBASE_WORKER_TOKEN`。它拒绝重定向，不输出凭据，重叠 tick 返回 409。
8. `/health` 为存活检查，`/ready` 必须确认 PostgreSQL／COS。验证普通 Actor token 无法调用 `/internal/jobs/*`；AI 的 8100 不对外开放。确认定时器在手机退出后仍能推进转写，并观测超过一分钟的处理中状态。

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

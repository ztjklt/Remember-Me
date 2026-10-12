# iOS 独立 CloudBase 环境与后台部署候选

日期：2026-10-12，Asia/Singapore。用户授权 iOS 使用其 CloudBase 账号、新建独立环境。工作目录在 `codex/ios-cloudbase-backend` 的独立 worktree，基于最新 Android 后台基线 `a12354a`。原工作区的未提交 iOS 画像审核和 AI 实验保留，Android ECS 未修改，共享 Contract 未变。

## 外部实际状态

- 环境 `remember-me-ios-d5f9twwlcae71c69` 已创建，上海。最初使用兑换码免费创建，随后用户自行升级标准版。数据库独享升级配置由用户明确接受并亲自在控制台提交。
- 数据库配置页确认实例 `postgres-drasbama` 运行中，PostgreSQL 17.11、1 核／2 GiB／20 GB，内网地址 `172.17.0.11:5432`，VPC `vpc-4hhp8p9k`、子网 `subnet-9tpjt6z9`。批准规格每小时 352 点，30 天约 253,440 点；未开启数据库公网入口。
- 用户自行重置原生数据库密码，已回复完成；密码未出现在聊天、源码或测试中。真实直连及 TLS 尚未验证。
- 用户自行确认 CloudBase 云托管服务条款及 CODING 第三方软件授权弹窗。云托管服务创建入口已可用，应用服务尚未部署。磁盘中断后创建表单草稿重置。
- 原生 PostgreSQL 路线已确定。候选连接强制证书和主机验证，业务表放入私有 `remember_ios` Schema；该 Schema 不属于默认 public 数据接口。

- `remember_ios` 私有 Schema 真实创建并收回 PUBLIC 权限。官方管理接口执行 Alembic PostgreSQL 离线迁移 SQL，事务代码块仅允许空 Schema。真实表数 34，head `0016_share_invitations`，已通过单条独立查询确认。
- 原生私有存储桶 `remember-me-ios-audio` 创建成功，`public=false`；restrictive policy `remember_ios_backend_only` 对 anon/authenticated 生效。真实 put/get/delete readiness 通过；匿名读取现存合成测试对象返回 404；测试对象已删除。
- 用户自行批准并完成腾讯云官方 CLI 设备登录授权；该授权不代表 PostgreSQL 各 API 均可用。原生 PostgreSQL 账号创建、查询及 SSL 配置 API 返回 `OperationDenied.CamDeniedError`，未反复尝试扩大权限。后台专用存储 Key 在本机私密文件中保存，有效期 30 天，未回显。

## 已实现并验证的候选代码

- 最小部署包，只选 Backend、AI Core、Contract Schema 与运行脚本，不含手机工程、原音、数据库、`.env`、证书、供应商或账号密钥。生成 zip、tar.gz 与逐文件 SHA-256 清单。
- Backend 公网 HTTP 与 AI Core 容器内 loopback HTTP 两种进程；任务由独立密钥保护的定时请求推进，无常驻后台处理循环。Actor 凭据不能调用内部 tick；重叠 tick 拒绝并返回 409。
- Paraformer 检查点可选择已有 ObjectStore，默认本机行为不变。提交结果不确定时保存 `submitting`，冷启动不重放；已有任务继续轮询，存储不可读时不重新提交原音。内测候选要求最大副本 1，未宣称具备多副本分布式锁。
- 注册仍关闭，创建内测账号不默认授予 RECORDING、CLOUD_TWIN 或 VOICE。声音生成未部署。
- 现有 BGE CPU 检索实现保留；未新增 pgvector ANN 迁移，未声称检索在新环境已经可用。

## 执行结果

Python 3.12 + SQLite：以下 105 项测试通过。Python 3.12 + 本次创建的独立 PostgreSQL 16 测试库：同一组 105 项测试通过，0 失败。PostgreSQL 测试使用每项独立 Schema；只含虚构测试数据。测试结束后已停止本地测试库，未操作用户既有数据库。

```bash
cd services/backend
uv run --python 3.12 pytest tests/test_cloudbase_deployment.py \
  tests/test_paraformer_asr.py tests/test_accounts.py \
  tests/test_cloud_asr_consent.py tests/test_worker.py tests/test_object_store.py

REMEMBER_TEST_POSTGRES_URL='postgresql+psycopg://cloudbase_fixture@127.0.0.1:65436/remember_ios_test' \
  uv run --python 3.12 --extra deployment pytest tests/test_cloudbase_deployment.py \
  tests/test_paraformer_asr.py tests/test_accounts.py \
  tests/test_cloud_asr_consent.py tests/test_worker.py tests/test_object_store.py
```

另有两条来自 Starlette/httpx 的弃用提醒，未把警告隐藏为无警告结果。

本机 Linux amd64 Docker 构建未通过：先遇到 Colima 缺失 DNS 配置、Docker Hub EOF 与已不存在的官方镜像 tag；修正后使用实际可拉取的 `ghcr.io/astral-sh/uv:0.12.18-python3.12-trixie-slim`，安装 CPU 依赖时因主机磁盘不足导致 snapshot 输入／输出错误。没有完成镜像，也没有运行容器 smoke test。恢复后删除本次创建的 default Colima 临时环境，主机可用空间从约 5.3 GiB 恢复到约 11 GiB；保留此前存在的 `campusmate-validation` 环境。

后续 Dockerfile 关闭 uv 下载缓存，准备改用远端构建。远端构建仍未执行。源码包与 `git diff --check` 已检查；新增 zip 打包后定向复测打包排除敏感文件／本机状态与定时器拒绝重定向，2 项通过，12 项未选中。

TLS 与私有 Schema 配置修改后，定向执行 `tests/test_cloudbase_deployment.py`：15 项通过。新增原生 Storage adapter 后，定向 18 项通过，再运行上述测试组加 `test_cloudbase_object_store.py`：109 项通过（SQLite），仍有同样两条弃用提醒。没有将新增 adapter 的结果写成已在本地 PostgreSQL 重跑。

## 未完成

原生数据库凭据／CA／直连已于 2026-10-13 验证（见末节）。仍待完成：应用容器实际连通、ASR 凭据、独立 App 内测账号、手机录音上传到新私有存储的验证、定时器、后端服务部署与 HTTPS origin、iPhone 切换新环境、本人真实录音到 Twin 的闭环。旧 iPhone ECS 包仍指向旧 ECS，不将环境创建成功写成 App 已切换成功。

后台准备指南在 `infra/cloudbase/README.md`。官方资料与当前控制台分别作为证据：

- [CloudBase PostgreSQL 的访问方式](https://docs.cloudbase.net/database/postgresql/initialization)
- [管理接口 ExecutePGSql](https://docs.cloudbase.net/en/api-reference/manager/node/postgresql)
- [HTTP 执行 SQL：管理员限定](https://docs.cloudbase.net/en/http-api/pgdb/exec-pgsql)
- [共享与独享实例及升级](https://docs.cloudbase.net/database/postgresql/database-management)
- [云托管边界](https://docs.cloudbase.net/run/limitation)

## 2026-10-12 赛事模型平台续接

用户补充共用 Key 与赛事文档。文档中的模型 ID 是路由别名，不是各个模型独立的密钥。实际验证 `https://ai-router-cn-pub.anker-in.com/chat/completions` 的 Qwen 最小 JSON 请求返回 HTTP 401；同主机 `/models` 也返回 401。没有发送个人材料、录音、声音样本，也没有进行 TTS 请求；没有凭模型列表宣称 ASR 已工作。

新增 Anker 模型 adapter 与同步 relay 持久检查点候选；复用既有证据协议，不修改公开 Contract。AI 定向 `test_anker.py test_weixin.py test_api.py test_twin.py`：56 通过；Backend 定向 `test_durable_relay_asr.py test_cloud_asr.py test_cloud_asr_consent.py test_cloudbase_deployment.py test_worker.py`：88 通过，两组分别各有 2 条上游弃用提醒。真实 ASR payload、模型延迟及真人闭环仍未验证。

## 2026-10-13 DeepSeek 官方 Flash 续接

用户提供 RM Key 并选择 DeepSeek Flash。先在当前 DeepSeek 控制台确认归属，未将它当作百炼或赛事 Key。目录 HTTP 200，仅列当前 `deepseek-flash` 路由。官方说明旧 V4 Flash 别名仍兼容，实际服务由当前 Flash 版本承担；代码记录接口返回的模型标识。

通过本机实际 AI Core 适配器调用官方 API，只有虚构文字：

- `/process`：200，0.77 秒，2 条记忆、2 条已通过定位校验的证据；实际模型 `deepseek-flash`。
- `/twin`：200，0.60 秒，ORIGINAL，引用都存在，原话保留尚未决定报名的意思；实际模型 `deepseek-flash`。
- `/profile-proposals`：200，0.94 秒，1 项待本人确认的候选，引用属于输入；实际模型 `deepseek-flash`。

新增 DeepSeek profile JSON adapter，共用固定目标、有界 JSON transport；原有公开 Contract 不变。定向 `test_deepseek.py test_anker.py test_api.py test_twin.py test_weixin.py test_profile_relations.py`：74 通过、2 条上游弃用提醒。该结果不是全量评估、CloudBase部署或真人录音闭环。

截至以上模型验证时，原生数据库密码仍未填入后端私密配置；后续数据库续接见下节。没有用 Token Plan Key 做应用后端推理，没有开启自动充值，没有提交百炼的新普通 Key 或月预算。

## 2026-10-13 数据库密码与原生 TLS 续接

用户随后在聊天提供数据库密码，并明确要求代填。密码已写入 ignored `build/private/credentials.json` 和运行配置，两文件均为 0600；不把聊天中的值复制进本文或源码。此前“密码未出现在聊天”的记录仅描述当时状态。

Safari 配置页确认强制 SSL 复选框开启、保护地址 `172.17.0.11`，下载腾讯云官方 `TencentDB-PG-SSL-CA/ca.pem`。CA 可由系统 SSL parser 读取，证书有效期至 2042-06-12，issuer 为 Tencent Root CA；运行配置已加入 CA，启动器仍强制 `verify-full`。

在该独立环境部署并调用临时 `remember-ios-db-preflight` Event 函数：Nodejs20.19、128 MB、20 秒，无 HTTP 入口、无触发器，绑定数据库 VPC／子网。实际证书 SAN 与 CN 对应数据库私有 IP。Node pg 的初次 SSL 主机推断失败；显式使用 Node 标准 `tls.checkServerIdentity` 校验目标 IP 后，完整证书链／身份校验和密码认证通过，读取 head `0016_share_invitations`、表数 34、实际角色 `cloudbase_postgres_postgres_drasbama`。没有关闭证书验证，没有创建数据库公网地址。原生直连结果保存在 ignored 私密测试报告中。

VPC 查询没有 NAT 网关；该 VPC 云函数访问 DeepSeek 模型目录超时，未携带模型 Key。另行用不含凭据的临时 Python 容器检查云托管的 VPC 连接及平台默认公网出口。实际 HTTPS 检查响应 200，PostgreSQL SSL 协议及标准 Python SSL 证书链／目标 IP 校验通过；未带 Key 的 DeepSeek `/models` 返回预期 401，证明公网 HTTPS 出访可达。这条路径无需新增 NAT，未购置 NAT／EIP 或启用固定公网出口。临时镜像由腾讯云远端构建，Mac 没有再次构建大型应用镜像。应用 Backend／AI Core 镜像、ASR、独立 App 账号、定时器和手机环境切换仍未完成。

临时数据库函数调用完成后已删除并查询确认函数列表为空。网络检查服务也已删除，清理后的函数列表和云托管服务列表均为空；它不含任何数据库密码、模型 Key、业务数据或公开业务接口。云托管日志检索曾提示尚未启用日志服务，未为诊断新增 CLS 计费服务；网络结果通过 HTTPS 测试响应取得。

[云托管公网出访配置](https://docs.cloudbase.net/run/deploy/networking/egress)与[目的 VPC 网段的路由说明](https://docs.cloudbase.net/run/faq/network)用于解释实测；云函数与云托管的公网路径分别验证。

## 2026-10-13 普通百炼 ASR 续接

用户明确选择普通百炼 ASR，随后自行创建普通工作空间 Key 并授权用于语音模型；它独立于 Token Plan 和 DeepSeek Key。只保存于 ignored 私密配置，固定使用已在控制台观察到的北京工作空间 `ws-5hudj5uvce12kiug`。临时上传策略真实返回 200，要求 private 且 forbid-overwrite；没有公开 CloudBase 原音桶。

现有 Paraformer adapter 原先只接受 `llm-` 工作空间地址，补充当前 `ws-` 前缀，仍拒绝非 HTTPS、用户名／密码、路径、query、port 和非阿里云目标。新增测试验证 ws host 可以转写，认证请求只发到该 workspace，并在错误目的地址时零请求。`test_paraformer_asr.py test_cloudbase_deployment.py` 共 38 项通过，2 条既有上游弃用提醒。共享客户端 Contract 无修改。

真实 provider adapter 使用 macOS Tingting 生成的 6 秒中文测试音频完成私有临时上传、异步提交、轮询、结果下载，返回文字与合成内容一致，耗时 3.7 秒，来源 `bailian/paraformer-v2`。报告在 ignored `build/paraformer-live-probe-20261013.json`；没有使用本人声音、手机录音或个人记忆。正常配置已选 Paraformer，DeepSeek Flash 仍为主 LLM。应用容器／手机闭环结果需另行记录。

[Paraformer 文件转写 API](https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-restful-api)及[临时文件上传](https://help.aliyun.com/zh/model-studio/get-temporary-file-url/)为协议依据。

## 2026-10-13 云端应用与 iPhone 交付

完整应用镜像已由腾讯云远端构建并推送，源码基线 `fe37b16`。服务 `remember-ios-api` 使用 1 CPU／2 GiB，min 0／max 1，数据库同 VPC + 平台默认公网出口；无需新增 NAT／EIP。原音及 ASR 检查点保存在本环境私有存储。原先构建任务未产出镜像时取消并重试，不能把该次当作已通过。随后完整应用构建、部署与就绪成功。

HTTPS origin：`https://remember-ios-api-327435-12-1411199312.sh.run.tcloudbase.com`。`/health` 200，`/ready` 200 且 PostgreSQL／private ObjectStore 为 ok；`/api/v1/service-info` 200，发布身份 `ios-cloudbase-fe37b16`，注册 false。固定 allowed-host 为实际域名和 loopback，未用全局通配符。发布身份配置在定时器启用和测试 Job 创建前更新；后续替换仍要求避免多版本同时处理任务。没有实测配置网关并发上限；代码采用单 API worker、AI 并发 1、内部 tick 互斥与数据库 job lease。

独立账号使用现有 `account_admin.create_account` 生成 Actor、Account、Subject，通过受保护 SQL 管理接口事务写入新 Schema；已存在账号则拒绝创建，不重置。初始随机密码仅在本机 ignored 私密文件中。账号 `jitian` 登录真实返回 200，1 个 owner 空间；核对时该空间 Episode 0、Consent 0，没有代其授予录音、文字模型或 VOICE 权限。另建独立虚构测试账号进行闭环，不把测试记忆放入本人空间。普通 Actor 调内部 tick 返回 401。

合成 WAV 的真实云端 API 闭环：上传 201 → Paraformer 原始机器稿 → 待核对 → 确认 200 → DeepSeek 提取及模型更新 → result 200、1 条 Memory → Twin 200、ORIGINAL、1 个已存在的原文引用。原音下载 200 且 SHA-256 与上传字节相同；匿名下载 401。核对前读取 result 得到 409；初次 harness 未完整处理转写后进入 reviewing 的状态推进，修正测试流程后确认文字才继续，不放宽产品门槛或重放原音。

语音提问 `/twin/transcribe-query` 真实 200，识别正确且 Episode 数未增加。额外验证与 iOS 录音相同类型的 AAC M4A（48 kHz／mono／128 kbps），`audio/mp4` 原音真实转写 200、内容一致。以上均为合成语音，没有发送本人录音／声纹。报告位于 ignored `build/cloud-*-probe-20261013.json`。

`remember-ios-worker` Python3.9 Event 函数部署成功，无 HTTP 触发器、无 VPC（只调用已审核的 HTTPS API），120 秒 timeout。人工调用返回 timer_completed；启用 `remember-ios-minute` 的每分钟触发器。随后提交独立测试 Subject 的人物候选任务，返回 queued；没有人工调用 worker，之后读取为 complete、1 项 pending 候选、无 error，证明定时处理实际推进。统一日志读取返回 TopicNotExist，未为调试开通新的 CLS 服务；任务结果可由数据库／API 查询。

iOS 来源为主工作区当前版本（包括已有未提交人物审核代码）；这些用户改动保留，本次只改连接、系统 TLS、cloudbase 本地配对类型、版本及对应测试。使用系统证书只适用于固定 CloudBase origin；旧 ECS／Mac 配对仍走原有 pin。两种会话都拒绝 HTTP 重定向，provider Key 不进入 App。连接测试 `ECSConnectionTests` 9 项通过（iOS27 模拟器），签名真机构建通过。补齐 Xcode build settings 的版本，实包核对为 **Remember Me iOS 1.2.1 / 2026101301**，bundle `me.remember.personal.ios`；已安装到 iPhone 15 Pro Max「黑幕」并由 devicectl 确认启动。只证明安装／启动，不冒称已经完成本人真机录音旅程。

仍待本人在手机完成一次实际录音、核对、整理、Twin 试用。声音克隆／云端本人声纹朗读未部署；语音识别成功不等于声音克隆成功。单段原音上限 18 MiB，超出时仍需保留本机原音并另行处理。当前 BGE CPU 检索已在云端 Twin 路径工作，向量仍存 JSON，未切换 pgvector ANN。服务端存储 Key 有既定 30 天有效期，后续需要轮换；CLI 登录和签名开发包也按各自有效期管理。

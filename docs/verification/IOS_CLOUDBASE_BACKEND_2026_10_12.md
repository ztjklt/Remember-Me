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

原生数据库凭据／CA／服务实际连通、供应商凭据、独立 App 内测账号、手机录音上传到新私有存储的验证、定时器、后端服务部署与 HTTPS origin、iPhone 切换新环境、本人真实录音到 Twin 的闭环。旧 iPhone ECS 包仍指向旧 ECS，不将环境创建成功写成 App 已切换成功。

后台准备指南在 `infra/cloudbase/README.md`。官方资料与当前控制台分别作为证据：

- [CloudBase PostgreSQL 的访问方式](https://docs.cloudbase.net/database/postgresql/initialization)
- [管理接口 ExecutePGSql](https://docs.cloudbase.net/en/api-reference/manager/node/postgresql)
- [HTTP 执行 SQL：管理员限定](https://docs.cloudbase.net/en/http-api/pgdb/exec-pgsql)
- [共享与独享实例及升级](https://docs.cloudbase.net/database/postgresql/database-management)
- [云托管边界](https://docs.cloudbase.net/run/limitation)

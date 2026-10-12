# iOS 独立 CloudBase 环境与后台部署候选

日期：2026-10-12，Asia/Singapore。用户授权 iOS 使用其 CloudBase 账号、新建独立环境。工作目录在 `codex/ios-cloudbase-backend` 的独立 worktree，基于最新 Android 后台基线 `a12354a`。原工作区的未提交 iOS 画像审核和 AI 实验保留，Android ECS 未修改，共享 Contract 未变。

## 外部实际状态

- 环境 `remember-me-ios-d5f9twwlcae71c69` 已创建，上海，PostgreSQL，免费体验六个月，实付 ¥0，2027-04-12 到期；未选择订单附加产品。环境卡片与数据库管理页已观察到，未只凭按钮点击推定成功。
- 用户自行在页面确认 CloudBase 云托管服务条款及 CODING 第三方软件授权弹窗。云托管服务创建入口已可用；不存在已部署的应用服务。
- 创建表单此前准备服务名 `remember-ios-api`、端口 8000、最小实例 0、最大实例 1。磁盘中断后 Safari 重启，表单草稿重置；没有点击部署，也没有上传带密钥的源码包。
- 数据库配置页显示 PostgreSQL 17.11、共享集群、内网地址 `-`，外网地址开关不可操作。独享集群升级入口显示本版本不支持，要求升级标准版，标价 ¥199/月；没有提交升级。数据库与容器资源计费还需另核实，不能把套餐价格当完整后端费用。
- 当前候选是 SQLAlchemy / psycopg 直连方案，不能把 CloudBase HTTP 数据库地址替换到 DSN 中直接运行。免费环境仍可使用官方 HTTP／PostgREST／RPC 能力，但需要重做事务适配以保留账号隔离、授权、幂等、job lease 与源版本比较。目前等待用户明确原生适配或独立直连数据库路线。

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

后续 Dockerfile 关闭 uv 下载缓存，准备改用远端构建。远端构建仍未执行。源码包与 `git diff --check` 已检查；新增 zip 打包后定向复测打包排除敏感文件／本机状态与定时器拒绝重定向，2 项通过，11 项未选中。

## 未完成

CloudBase 数据持久层路线、服务端凭据、真实数据库迁移、独立 App 内测账号、私有录音存储、定时器、后端服务部署与 HTTPS origin、iPhone 切换新环境、本人真实录音到 Twin 的闭环。旧 iPhone ECS 包仍指向旧 ECS，不将环境创建成功写成 App 已切换成功。

后台准备指南在 `infra/cloudbase/README.md`。官方资料与当前控制台分别作为证据：

- [CloudBase PostgreSQL 的访问方式](https://docs.cloudbase.net/database/postgresql/initialization)
- [管理接口 ExecutePGSql](https://docs.cloudbase.net/en/api-reference/manager/node/postgresql)
- [HTTP 执行 SQL：管理员限定](https://docs.cloudbase.net/en/http-api/pgdb/exec-pgsql)
- [共享与独享实例及升级](https://docs.cloudbase.net/database/postgresql/database-management)
- [云托管边界](https://docs.cloudbase.net/run/limitation)

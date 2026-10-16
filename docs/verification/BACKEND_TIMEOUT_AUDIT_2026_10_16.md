# Backend timeout audit — 2026-10-16

本轮检查和修复的是服务端录音、通话及其共享数据库路径。源码已在当前工作区修复并验证，**没有发布新 Backend，也没有提交或变更共享 Contract / 数据库迁移**。现网 054 的阻塞由主任务单独解除；现网恢复可访问不等于以下源码修复已上线。

## 已定位的阻塞链

`api/twin.py::read_answer` 在读取回答前取得全局 publication lock。正常、未过期回答直接返回，没有提交事务；其锁原本要等 FastAPI 结束请求并清理 Session 才会释放。

通话的普通 / 国内 RTC 发言上传原本是 `async def`，却直接执行同步 SQLAlchemy INSERT / commit 和同步对象存储请求。在单个 Uvicorn 事件循环中，如果上传先等到前一个回答状态请求尚未释放的锁，事件循环就不能继续运行前一个请求的 Session 清理，形成自锁。此时连不访问数据库的 `/health` 也无法响应，表现为录音、通话和其他页面一起超时。

主任务从生产 PostgreSQL 观察到同一时间起的两个会话：一个 idle-in-transaction 持有几乎全部业务表的 ShareRowExclusiveLock，另一个 INSERT `voice_utterances` 等待对应 RowExclusiveLock；等待超过 18 分钟。主任务只取消该条已确认阻塞的 SQL 后，原 054 的 `/health`、`/ready` 和 `/api/v1/service-info` 恢复。这是运行时证据；下面的修复和自动检查是独立的源码验证。

另有两个会放大等待的问题：

- 本人音色登记在持有全局 publication lock 时上传私有音频，对象存储的一次网络等待就可能阻塞其他录音或通话写入。
- 音色状态查询复用供应商登记操作默认 45 秒的网络超时；未知提交的恢复可能连续 list + query，共两次请求。其等待超过移动端状态读取预算。

## 本地修复

- `read_answer` 先构建已核验的响应，再提交、释放 publication lock，才返回。来源失效和授权检查保持原逻辑。
- 普通和国内 RTC 的发言、音色片段上传及创建票据改为 FastAPI 同步工作线程处理；音色读取 / 登记、试听初始核验、实时播放初始核验、激活 / 打断 / 挂断和远端控制维护的同步数据库片段也移到工作线程。异步媒体 / 外部 RTC 操作继续异步执行。
- 音色样本先完成私有存储上传，再进入短的发布事务；重新核验 Actor / Subject、声音许可、现有 profile 和采集来源，竞态失败清理本次尚未入库的样本，不删除已有录音或已保存资料。
- 音色状态 list / query 各使用 6 秒的供应商网络超时；创建音色保留原登记预算。状态读取不自动重放创建请求。
- PostgreSQL 连接使用 5 秒连接超时，每条新连接设置 `lock_timeout = '5s'`，防止普通 INSERT / UPDATE 永久等待。锁超时仍走既有 `55P03 → STATE_CONFLICT / HTTP 409` 脱敏处理。

未更改供应商、已有账号、原音、许可含义、Subject 隔离或响应 schema；AI Core 未修改。

## 实际验证

在 `services/backend` 执行：

```sh
uv run pytest -q -o addopts='' --junitxml=/tmp/remember-timeout-backend-full.xml
```

结果：**978 passed, 7 skipped，209.20 秒**。跳过的 7 项要求独立 PostgreSQL；4 条警告是既有 Starlette / AnyIO 和 Python SQLite 日期适配弃用警告。

另启动独立、仅监听本机的 PostgreSQL 16 测试集群和 `remember_timeout_audit_test` 数据库，每个用例使用单独 schema。最初准备失败的原因分别是本机环境未安装 deployment extra 的 psycopg、PostgreSQL 未安装 pgvector；前者使用项目已有 `--extra deployment`，后者补齐固定 v0.8.1 的测试依赖后重跑。没有使用生产数据或修改生产 schema。

在仅指向上述测试数据库的 `REMEMBER_TEST_POSTGRES_URL` 下执行：

```sh
uv run --extra deployment pytest -q -o addopts='' --tb=short --maxfail=1 \
  tests/test_postgres_runtime.py tests/test_realtime_responsiveness.py \
  tests/test_volcengine_voice.py tests/test_volcengine_features.py \
  --junitxml=/tmp/remember-timeout-backend-postgres.xml
```

结果：**36 passed，23.99 秒**。覆盖真实 PostgreSQL publication lock 与普通写入的互斥、默认锁等待截止、读取回答后仍保持 reader Session 打开时另一写事务可以立即完成，以及国内 RTC 生命周期 / 功能回归。

新增响应性检查使用可控的依赖等待，要求在音频存储或 profile 数据库读取仍未结束时，`/health`、`/api/v1/service-info` 能独立响应；音色登记等待期间其他许可写入仍可完成。另验证存储上传途中撤销声音许可时，登记被拒绝且本次孤立样本清理。

最后强化正常回答分支的断言（明确 `stale == false`）后，单独在 PostgreSQL 重跑该锁释放用例：**1 passed**。随后关闭独立测试集群。

## 尚未由本轮证明的事项

- 修复尚未部署，原 054 仍可能再次触发旧阻塞链。
- 多人录音 `POST .../speaker-recordings/{id}/process` 当前在工作线程内同步执行识别，含对象存储和 ASR 等待；不会再因本轮发言上传问题阻塞事件循环，但仍需客户端按已保存状态恢复，不能把一次 HTTP 超时视为原音丢失。
- 云端 ASR / LLM / TTS 供应商的实际延迟、识别质量、真人音色及真机持续通话不由上述自动检查替代；本轮没有创建真人录音、完成真人通话或发布新服务。

# Python 后端与完整运行交接

## 本地启动

以下命令从项目根目录执行。第一次需在 `services/backend` 和 `services/ai-core` 分别 `uv sync --locked`。服务互相通过 HTTP 调用，两个 `app` 包不要混装进一个 Python 路径。

1. 将 `services/backend/.env.example` 复制为同目录 `.env`，设置本地数据库、存储目录。默认 fake/fixture 只做连通性开发，不产生真实识别结果。
2. 真实模型开发使用两服务各自的 `.env.cloud-demo.example` 作为起点，再配置本节后面的语音参数。配置应进入私有 `.env` 或进程环境。
3. 在 `services/backend` 执行 `uv run --locked alembic upgrade head`。新 SQLite 可本地开发；ECS 使用 PostgreSQL，迁移前备份。
4. 分别开终端启动以下进程：

```bash
# services/ai-core 工作目录
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8879

# services/backend 工作目录，以下三个命令各一个终端
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8877
uv run --locked python -m app.worker
uv run --locked python -m app.profile_worker
```

`REMEMBER_AI_CORE_URL=http://127.0.0.1:8879`。工作台开关为 `REMEMBER_ENABLE_WORKBENCH=true`，浏览器入口 `/workbench`；实际路由和错误契约以源码 `app/main.py`、`app/api` 为准。健康检查不代替录音到记忆的验证。

## 实际供应商与配置

| 组件 | 当前线路 | 配置位置/字段 |
| --- | --- | --- |
| LLM | DeepSeek，经微信兼容端点适配器 | AI Core `AI_PROVIDER=weixin`、`WEIXIN_CHAT_API_KEY`；完整模板见 AI Core `.env.cloud-demo.example` |
| 录音/语音 ASR | Paraformer | Backend `REMEMBER_STT_BACKEND=paraformer`、`REMEMBER_PARAFORMER_BASE_URL`、`REMEMBER_PARAFORMER_API_KEY` |
| 连续语音 TTS | 小米，当前代码使用预设声音 | Backend `REMEMBER_XIAOMI_VOICE_API_KEY`；实现见 `app/realtime_providers.py`，不是启动 Mac `services/voice` |
| 语音入口 | Android 到 Backend WSS | `REMEMBER_REALTIME_VOICE_ENABLED=true`、`REMEMBER_REALTIME_VOICE_ACTOR_IDS=["实际账号ID"]`，reviewed 路线；不要为快打开跳核验开关 |
| 免登录演示 | 限定两个虚构演示身份 | `REMEMBER_DEMO_ACCOUNTS_ENABLED=true`、`REMEMBER_DEMO_OWNER_ACTOR_ID`、`REMEMBER_DEMO_RELATIVE_ACTOR_ID`、`REMEMBER_DEMO_SUBJECT_ID` |
| 数据/原音 | PostgreSQL/SQLite + 对象存储 | `REMEMBER_DATABASE_URL`、`REMEMBER_OBJECT_STORE_*` |
| 检索 | 本地 BGE 中文模型 | `uv sync --locked --extra retrieval`；`REMEMBER_EMBEDDING_MODEL` 可指向已下载模型 |

演示开关不会自动建立账号或伪造授权。新环境先通过已有账号、空间、consent、分享接口建立两身份与虚构资料，再绑定 ID。可参考 `tools/delivery/provision_team_accounts.py` 和 `services/backend/tests/test_demo_accounts.py`；不要重跑旧服务器固定路径脚本去覆盖现有账号。

## ECS 接手与部署

现有服务入口为 `https://39.108.183.47`。0.16.7 使用仓库内公开测试证书校验；换域名/证书需同步客户端信任配置，不关闭 TLS 校验。

服务器 release 结构：`/opt/remember-me/releases/`；0.16.7 已验证 API release `paired-voice-clean-0167d-20261017`。服务私有配置位于 `/etc/remember-me/{api,worker,profile,ai,proxy}.env`。模板和 systemd/启动脚本在 `infra/aws/`，目录名保留历史，当前主机是 ECS。该目录旧 README 中 Groq 等供应商说明是历史，不覆盖本次 Paraformer/DeepSeek/小米配置。

新主机需 Python3.12、uv、PostgreSQL、FFmpeg、HTTPS 反向代理；部署额外依赖用 `uv sync --locked --extra deployment --extra retrieval`。先创建新 release、安装依赖、检查迁移和模型缓存，再切换服务；不能覆盖当前正在运行目录。API、worker、profile、AI 使用对应环境文件与同一待验收代码版本。

`infra/aws/prepare-host.sh` 会准备主机；`activate.sh` 会迁移并启动；`backup.sh` 保存数据库。这些不是只读检查，请在确认目标主机及环境后运行。回退保留原音和数据库，不以删资料回退。

## 客户端

Android：JDK17、SDK35，`apps/android/gradlew.bat :app:assembleDebug -PrememberServiceUrl=http://10.0.2.2:8877` 用于模拟器本地服务。录音豆构建另传 `-PrememberSoundcoreSdk=<soundcore-1.3.02.aar绝对路径>`；现有签名内测 APK 已含该 SDK。发布脚本为 `tools/delivery/build_signed_internal.py`，签名私钥不在源码包中。

Web：在 `apps/web` 执行 `node build.mjs`、`node --test tests/*.test.mjs`、`node --env-file-if-exists=.env server.mjs`；依照 `.env.example` 配置固定后端。`start-local.ps1 -Demo` 是原维护电脑的私有快捷入口，新电脑不能假定存在其外部账号文件。

iOS：需 macOS/Xcode，按 `apps/ios/README.md`；独立 iOS/CloudBase 路线的差异在 `docs/integration/`。不要把 Android ECS 的认证直接套到独立 CloudBase。

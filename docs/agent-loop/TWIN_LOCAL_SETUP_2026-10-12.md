# Twin / Persona：新克隆本地启动说明

本说明针对 2026-10-12 的代码交接。新克隆启动的是**自己的空数据库**：仓库不附带 A01 账号、会话、数据库、录音、模型权重或已确认的人物理解。历史截图和评测结果不是安装后的预置内容；本说明也不修改 ECS。

## 1. 环境与配置

需要 Python 3.12+、`uv`，以及可安装锁定依赖的网络或本地缓存。以下为 PowerShell 命令；每段标注了工作目录。两套服务各自使用 `.venv` 和 `.env`，不要把其他 checkout 的密钥文件复制进来。进程环境变量会覆盖 `.env`；若终端曾运行旧环境，先检查并移除不适用的 `REMEMBER_*` / `AI_*` 配置。

从仓库根目录准备 Backend：

```powershell
cd services/backend
uv sync --locked
if (Test-Path .env) { throw '已有 .env，请人工比对 .env.twin.example；不要覆盖。' }
Copy-Item .env.twin.example .env
New-Item -ItemType Directory -Force var/twin-local | Out-Null
uv run --locked alembic upgrade head
uv run --locked alembic current
```

迁移是建表入口。模板将 SQLite 和对象存储放在 `services/backend/var/twin-local/` 下；目录被 Git 忽略。不要为试跑复用别人已有的数据库路径。`alembic current` 应显示本分支的迁移头；本轮交接为 `0021_twin_review_summary`。

另开终端，从仓库根目录准备 AI Core：

```powershell
cd services/ai-core
uv sync --locked
if (Test-Path .env) { throw '已有 .env，请人工比对 .env.example；不要覆盖。' }
Copy-Item .env.example .env
```

默认 Backend 使用 `fake` ASR，AI Core 使用 `fixture` 提取器。这能检查启动、登录和基础接口接线，**不会识别真实录音，也不提供 Persona、人物候选、故事整理或真实 Twin 回答**。不要把夹具输出记为真实模型验收。

## 2. 普通账号与四个进程

在 `services/backend` 创建自己的普通登录账号。命令交互输入两次密码，密码不写入命令参数；长度为 8–128 字符。用户名为 3–64 位英文字母、数字、点、下划线或短横线。

```powershell
uv run --locked python -m app.account_admin create local-owner --name '本地记录者'
uv run --locked python -m app.account_admin create local-reader --name '本地亲友'
```

每次创建账号同时创建它自己的空人物空间。第二个账号不会自动成为第一个空间的亲友；记录者需在产品内邀请并选择分享范围。账号遗忘密码时可用 `uv run --locked python -m app.account_admin reset local-owner`，该操作会撤销该账号已有会话。模板关闭公开注册，CLI 仍可创建账号。这里不使用打印开发 token 的 `app.seed` 代替普通账号登录。

分别在四个终端保持以下命令运行；改 `.env` 后重启相应进程。

| 终端 | 工作目录 | 命令 | 作用 |
| --- | --- | --- | --- |
| 1 | `services/ai-core` | `uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8892 --log-config app/logging.json` | 内部模型接口；客户端不直接连接它。 |
| 2 | `services/backend` | `uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8891` | 登录、内容、权限和 Twin API。 |
| 3 | `services/backend` | `uv run --locked python -m app.worker` | 录音转写、记忆提取及建模任务。API 不会自动启动它。 |
| 4 | `services/backend` | `uv run --locked python -m app.profile_worker` | 人物候选、关系及故事整理队列。只运行一个本地 profile worker。 |

`app.narrative_worker` 由 profile worker 内部调用，不是要额外启动的第五个服务。只浏览空库时两个 worker 没有工作；要处理录音和整理任务则都需要保持运行。

在新的 PowerShell 终端检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8892/health
Invoke-RestMethod http://127.0.0.1:8891/health
Invoke-RestMethod http://127.0.0.1:8891/ready
```

`/health` 仅确认服务存活，Backend `/ready` 仅检查数据库连通和对象存储；它们不验证模型密钥、worker、迁移完整性或回答质量。随后打开 [本机工作台](http://127.0.0.1:8891/workbench/)，使用刚创建的账号登录；[人物与亲友页面](http://127.0.0.1:8891/workbench/companion.html) 读取当前账号实际有权访问的数据。

Android 构建先按 [Android README](../../apps/android/README.md) 准备 JDK 17、SDK 等工具。从 `apps/android` 执行：

```powershell
./gradlew.bat assembleDebug '-PrememberServiceUrl=http://10.0.2.2:8891'
```

该地址用于同一电脑上的 Android Emulator；真机不能把它当成电脑地址。模板显式允许这个开发 Host，但账号 HTTP 例外仍要求本机回环 TCP 来源。真机连接应另行配置已验证的 HTTPS 或本机转发路线。使用本地 `debug` 构建；`internal` 构建是既有服务配置，不是本说明的空库入口。

## 3. 开启真实模型与录音

在自己的私有 `.env` 中配置后重启四个进程。以下为现有代码支持的本轮路线，不包含任何可用密钥。

| 服务 | 必填设置 | 说明 |
| --- | --- | --- |
| AI Core | `AI_PROVIDER=weixin`、自己的 `WEIXIN_CHAT_API_KEY` | 当前 Persona、profile 和 narrative 路线由该适配器提供。代码为它设置 `https://chatapi.weixin.qq.com/openai/v1` 和 `Deepseek-v4-flash`；如显式配置 URL/模型，必须匹配这两个值。 |
| Backend | `REMEMBER_STT_BACKEND=paraformer`、自己的 `REMEMBER_PARAFORMER_API_KEY` 与 `REMEMBER_PARAFORMER_BASE_URL` | Base URL 必须是自己的北京工作空间 HTTPS 主机，形如 `https://llm-<workspace>.cn-beijing.maas.aliyuncs.com`，无路径、查询参数或 `compatible-mode`。占位符不能原样使用。 |
| Backend → AI Core | `REMEMBER_AI_BACKEND=http`、`REMEMBER_AI_CORE_URL=http://127.0.0.1:8892` | 模板已配置。交互超时为 100 秒；Persona 自身总预算为 90 秒，单次调用上限为 45 秒。 |

先用自己授权的虚构测试录音：登录记录者 → 单独确认录音及当前云转写范围 → 上传或录音 → 检查并核对真实转写 → 等待提取完成 → 主动发起整理 → 审阅候选并确认或拒绝 → 单独同意云端问答后再问。未确认的人物候选不会因为安装完成而自动变成有效理解；亲友内容也需本人处理及双方各自允许模型使用。每个阶段可能产生实际 API 用量，失败状态应保留并检查。

FFmpeg 不是 Python 依赖，需单独安装并放入运行 Backend/worker 的 `PATH`。可用 `ffmpeg -version` 检查。当前 Paraformer 适配器直接发送原音，不通过 FFmpeg 转码；FFmpeg 用于代码中的本地 Whisper sidecar，以及 Groq / 选择 MP3 转码的 relay 路线。仅启动默认夹具或 Paraformer 路线不要求额外启动 Whisper sidecar。

## 4. 本地 RAG 是额外能力

Twin 请求的 `retrieval_mode` 默认是 `full`：使用权限范围内的完整材料并检查容量。选择 `local` 检索模式，或使用 `/memory-search` 时，还需要 Backend 的 retrieval 依赖和模型。在 `services/backend`：

```powershell
uv sync --locked --extra retrieval
```

该额外依赖包含 `sentence-transformers` 和 CPU 可用的 PyTorch。默认模型为 `BAAI/bge-small-zh-v1.5`，代码固定其 revision；第一次实际向量检索可能下载权重。也可私下准备本地模型目录并设置 `REMEMBER_EMBEDDING_MODEL`。仅安装依赖不等于已经下载模型，设置离线模式前须确认缓存可用。模型缺失会明确报错，不能视为成功检索。外部 RAG 服务尚未配置与验收，本说明不提供或虚构外部端点。

## 5. 可选的虚构合成音色

默认 `REMEMBER_VOICE_SYNTHETIC_BACKEND=disabled`，新账号没有可播放的历史 A01 声音。若要启用本轮 Xiaomi 虚构声音路线，需在自己的 Backend 私有配置中同时设置：

- `REMEMBER_VOICE_SYNTHETIC_BACKEND=xiaomi` 和自己的 `REMEMBER_XIAOMI_VOICE_API_KEY`。
- `REMEMBER_A01_VOICE_SUBJECT_ID`：自己新建的**虚构人物空间**的真实 ID，不复制历史报告中的 ID；可从登录后的空间 API 返回值确认。
- `REMEMBER_A01_VOICE_REFERENCE_PATH`：自己准备并有权使用的虚构合成参考 WAV；存入忽略的本地目录，不能用亲友补充录音冒充本人参考。适配器限制有效 PCM WAV、1–2 声道、8–96 kHz，且不超过 8 MiB。

这些 `A01` 命名是现有配置字段与 preset 名称，并不意味着自动导入历史 A01。配置后仍要由记录者单独授予 `VOICE` 并设置合成声音 preset；亲友播放另需声音授权。只能为当前有效的已保存回答生成声音；配置文件本身不生成音频。默认 Xiaomi URL/模型已在示例中列出。另一条真人样本的本地 Voice sidecar 路线见 [Voice README](../../services/voice/README.md)，它不是上述四进程的必需项。

## 6. 离线开发检查与历史脚本

在各服务目录可分别运行 `uv run --locked pytest -q`。测试通过只证明相应自动化范围，不代表真实录音、模型质量或真机体验已验证。

两份 Web 交互夹具使用普通 `require('playwright')` 和已安装的 Google Chrome（`channel: 'chrome'`）。从仓库根目录按需安装本地依赖并运行，不使用个人电脑缓存路径：

```powershell
npm install --no-save --package-lock=false --prefix services/backend playwright
node services/backend/tests/test_companion_frontend.cjs
node services/backend/tests/test_persona_companion_frontend.cjs
```

这些脚本通过 HTTP fixtures 检查前端，不启动真实 Backend 或调用模型。`apps/android/scripts/persona_*_live.py` 保留本次历史验收上下文，依赖忽略的私有材料、固定 ID 和已存在状态；它们不是新克隆的 bootstrap，也不应直接加入空库默认验收。Android 脚本的 ADB 查找已支持 `ANDROID_HOME`、`ANDROID_SDK_ROOT`、`PATH`，其数据前置条件见 [历史脚本说明](../../apps/android/scripts/PERSONA_COMPANION_LIVE.md)。`tools/a01_*` 该组历史实验工具留在原工作区，不随本次交接分发。

## 命令依据与本说明的验证范围

命令与配置来自本分支实际代码：两服务的 [Backend 配置](../../services/backend/app/config.py) / [AI Core 配置](../../services/ai-core/app/config.py) 与 `pyproject.toml`；[账号 CLI](../../services/backend/app/account_admin.py)；[录音 worker](../../services/backend/app/worker.py)；[profile worker](../../services/backend/app/profile_worker.py) 及 [任务分派](../../services/backend/app/profiles.py)；[AI Core 路由构建](../../services/ai-core/app/api.py)；[本地检索](../../services/backend/app/retrieval.py)；[Paraformer 配置校验](../../services/backend/app/paraformer_asr.py)；[声音参考校验](../../services/backend/app/voice_client.py)。本文编写时只执行配置解析、CLI help、语法及模拟工具查找检查，没有创建真实账号、启动服务/设备或进行 provider 调用；按上述步骤的新机器端到端运行仍需执行者验证。

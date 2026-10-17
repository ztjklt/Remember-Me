# 勿忘我 · 完整源码与 AI 接手入口（2026-10-17）

**本文件是这次提交入口。Python 后端不是外部黑盒，完整代码就在本仓库。**

- 交付分支：`codex/work3200-device-20261016`。
- 固定交付版本与附件：[submission-full-20261017](https://github.com/ztjklt/Remember-Me/releases/tag/submission-full-20261017)。请使用该版本的源码包，不要从旧 `main` 页面猜测当前状态。
- 最新已验证 Android：`0.16.7-device-internal`；对应 Android 源码 `e9ad009`，已验证 ECS 服务代码 `17fb424`。交付提交还包含文档与此前本地 Web 源码，不代表服务器已部署所有后续改动。
- 快速交给 AI：下载 `remember-me-complete-source.zip`，从本文件开始；若只查后端，可先看 `remember-me-python-backend.zip`。

## 1. 所有实现在哪里

| 路径 | 交付内容 |
| --- | --- |
| `services/backend/` | 完整 Python/FastAPI 后端：账号、权限、录音入库、转写、任务、人物/记忆、托付、Twin、实时语音 WSS、供应商适配器、数据库迁移、测试、锁定依赖 |
| `services/ai-core/` | 完整 Python AI 服务：DeepSeek 适配器、提示词、结构校验、事实/人物回答、语义核验、记忆提取、测试、锁定依赖 |
| `services/voice/` | 独立 Mac/MLX 本地声音适配器源码及锁定依赖；当前 Android 的小米实时 TTS 在 Backend 中，不依赖启动这个 Mac 服务 |
| `apps/android/` | Kotlin/Compose 客户端、录音豆 SDK 接口层、无 SDK 回退构建、录音/同步/转写/聊天/花田/信笺、测试 |
| `apps/ios/` | 本分支已有的 iOS 客户端源码；不表示与队友独立 CloudBase 版本或 Android 已全量合并 |
| `apps/web/` | Web 客户端、同源网关、构建脚本、15 项测试；连续语音尚未移植到 Web |
| `packages/contracts/` | 共享 JSON Schema、接口类型和验证工具 |
| `infra/` | 迁移说明、systemd、HTTPS 代理、主机准备、启动、备份与配置模板 |
| `tools/` | 构建、发布、评测、数据处理、模拟器语音测试工具源码 |
| `assets/`、`docs/`、`evaluations/` | 品牌/界面资源、设计、产品说明、接口说明、测试记录和虚构评测资料 |
| `docs/submission/` | 本次部署接手说明、虚构陈守义素材、外部资源清单及进行中补丁的使用说明 |

## 2. 新电脑先运行什么

Python 3.12+、uv；Android 另需 JDK17 与 SDK35；Web 需 Node22+。两个 Python 服务的包都叫 `app`，必须在各自目录和虚拟环境运行。

```bash
git clone --branch codex/work3200-device-20261016 https://github.com/ztjklt/Remember-Me.git
cd Remember-Me

cd services/backend
uv sync --locked
uv run --locked pytest -q

cd ../ai-core
uv sync --locked
uv run --locked pytest -q
```

这些是接手后的运行命令，不是宣称本次重新跑过全部历史测试。本次与 0.16.7 相关的已执行证据见[验收记录](docs/validation/2026-10-17-voice-demo-cleanup.md)。

实际服务的配置和启动顺序见 [运行交接](docs/submission/RUNBOOK.md)。仅运行 `uvicorn` 不会启动录音处理和人物处理后台任务；不要漏掉 `worker` 与 `profile_worker`。

## 3. 核心数据流和代码入口

```text
录音豆 SDK / 手机录音 → Android 本地原音 → Backend Episode
→ ASR → 转写草稿 → 本人编辑/保存 → AI Core 提取 → 记忆及人物候选

语音聊天 → WSS/Paraformer → 授权检索 → DeepSeek
→ 语义核验 → 小米 TTS → Android AudioTrack
```

- `services/backend/app/main.py`、`app/api/`：HTTP/WSS 入口。
- `services/backend/app/models.py`、`migrations/`：存储与版本迁移。
- `services/backend/app/retrieval.py`、`app/rag_contract.py`：授权检索和上下文。
- `services/backend/app/realtime_providers.py`、`app/api/voice_sessions.py`：实际语音链及断句。
- `services/ai-core/app/persona.py`、`app/conversation_style.py`、`app/conversation.py`：生成、措辞、正常招呼与核验；完整目录包含其余记忆/画像能力。
- `apps/android/app/src/main/java/`：Android 主逻辑；`src/soundcore/` 为硬件实现。

## 4. 当前可用与未完成

两个免登录身份是虚构陈守义本人/亲友，共享同一人物、权限不同。旧测试身份已停用；公开素材不包含旧账号数据库。当前通话保留双方历史，跨通话持久历史尚未新增。

0.16.7 最后两批模拟器合成 PCM 输入，共 8 轮真实服务语音请求均完成播放；说完至出声 **3.35～11.73 秒**，尚未稳定 3～5 秒。没有把模拟器测量当作真机麦克风或录音豆验收。未核验草稿不播放。普通招呼由 DeepSeek 正常生成，不用人物记忆硬凑。

Web 是本地已验证的独立前端/网关，仍需正式 HTTPS 部署，未接录音豆和连续语音。第三方 SDK、模型权重、云账号配置与旧数据库不是仓库内自动具备的依赖，见[外部资源](docs/submission/EXTERNAL_RESOURCES.md)。

## 5. 给接手 AI 的任务顺序

1. 固定 Release/commit，先读本文件、`AGENTS.md`、运行交接、验收记录和共享契约。
2. 明确本地代码、已安装 APK、线上 release 三者版本；不把它们自动当作同一版本。
3. 跑对应模块测试；已有两演示身份有实际授权差异，不用清库或关权限换取演示成功。
4. 查看 Release 的 `remember-me-handoff-evidence.zip`：实际截图、逐轮时延、APK 清单以及快照时正在修改的 `work-in-progress.patch`。补丁可能与之后的提交重叠，先比对；没有把它当成已部署成品。
5. 优先处理语音尾延迟、未开放记忆的隔离、跨通话历史；保留旧失败和慢例。不要写死回答、伪造 SDK 数据或跳过核验来制造达标。

公开包包括项目源码、配置模板和虚构样例。真实密钥、令牌、签名私钥及数据库备份不公开；字段、用途和原维护环境位置已说明，接手环境应自行注入合法凭据。

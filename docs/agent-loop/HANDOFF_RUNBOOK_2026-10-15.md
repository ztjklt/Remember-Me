# 接手与发布步骤（2026-10-15）

> **本日后续发布补充：** 已按用户授权完成受控 ECS 更新及同签名 0.12.1 发布，记录见[同步结果与回退信息](CLOUD_SYNC_RESULTS_2026-10-15.md)，队友直接使用[安装说明](ANDROID_0121_QUICK_START_2026-10-15.md)。下文“不自动部署”描述的是较早源码交接；源码默认开关仍关闭，当前 ECS API/worker 已明确开启自动校对。PR 保持未合并。

本说明承接 [交接总览](TEAM_HANDOFF_2026-10-15.md)。本次更新 PR #94，不合并、不自动部署。

## 1. 获取代码

新电脑：

```bash
git clone --branch codex/continuous-voice-20261014 https://github.com/ztjklt/Remember-Me.git
cd Remember-Me
git rev-parse HEAD
```

已有仓库先保存自己的未提交工作，再 `git fetch origin`。要审阅这次交接，可以单独建立工作目录：

```bash
git worktree add --detach ../Remember-Me-review origin/codex/continuous-voice-20261014
```

不要 reset 或整目录覆盖队友自己的分支。评审基线是 `21e960e`；PR 本身仍显示相对其父分支的累计差异。

## 2. 本地运行与检查

详细建库、账号、服务启动沿用 [新电脑运行手册](TWIN_LOCAL_SETUP_2026-10-12.md)。Python ≥3.12、uv、JDK17、Android SDK35；JS 合约使用 Node24。分别在两个 Python 服务目录执行 `uv sync --locked`。AI 和 Backend 的模块都叫 `app`，使用各自虚拟环境/工作目录，不混用 PYTHONPATH。

```bash
# services/ai-core
uv run --locked pytest -q
uv build --wheel
uv run --locked python scripts/check_wheel.py

# services/backend
uv run --locked pytest -q

# packages/contracts
npm ci
npm test

# apps/android (Windows 使用 gradlew.bat)
./gradlew :app:testDebugUnitTest :app:assembleDebug -PrememberServiceUrl=http://10.0.2.2:8891
```

fixture/fake 仅用于确定性开发测试，不提供真实识别、完整人物生成或真实语音。真实使用需在各服务的私有 `.env` 配置既有供应商凭据。仓库只有模板和虚构结果；数据库、原音库、签名私钥与模型凭据不在 Git 中。

## 3. 新增配置和兼容性

配置模板位于 `services/backend/.env.example` 与 `services/ai-core/.env.example`。新能力默认关闭，先在隔离库、指定账号启用。

| 配置 | 用途/依赖 |
|---|---|
| `REMEMBER_TRANSCRIPT_CORRECTION_ENABLED` | 启用本人服务器 ASR 后校对；同时需要 `REMEMBER_AI_BACKEND=http`，AI Core 已有 `/transcripts/correct`，API/worker 配置一致 |
| `REMEMBER_TRANSCRIPT_CORRECTION_TIMEOUT_SECONDS=50` | 整个纠错请求等待上限；失败保留机器稿进入核对，不伪造完成 |
| `REMEMBER_REALTIME_VOICE_ENABLED` / `REMEMBER_REALTIME_VOICE_ACTOR_IDS` | 通话总开关与允许的账号 ID 列表；从已登录身份解析，不由客户端任意冒认 |
| `REMEMBER_REALTIME_VOICE_FAST_ENABLED` | 对话可选择跳过独立大模型语义审阅的快速路径；不是审阅在后台继续运行。来源、结构、版本及权限检查仍保留 |
| `REMEMBER_REALTIME_VOICE_STREAMED_ENABLED` | 快速开关同时开启时提供流式试验路径 |
| `REMEMBER_REALTIME_VOICE_PREFETCH_ENABLED` | streamed 路线的临时识别预取；版本不一致时不能复用；测量命中收益后再启用 |
| `REMEMBER_EMBEDDING_WARMUP` | 预加载检索模型；机器需要准备模型文件与内存 |
| `AI_VOICE_CALL_TIMEOUT_SECONDS=8` | streamed Twin 开启串行恢复时为共享模型预算；其他路径是单次上游调用上限，并保留各自逻辑重试策略。都不是整个手机回答延迟 |
| `AI_VOICE_RETRY_AFTER_SECONDS` | 默认 0；仅 streamed Twin 启用共享预算恢复，试验设为 3；reviewed/fast/Persona 不据此切换重试策略，认证/限流不盲目重试 |
| `REMEMBER_STEP_REALTIME_ENABLED` / `REMEMBER_STEP_REALTIME_API_KEY` | StepAudio 可选路线，还需要通话总开关、账号名单及 fast；密钥只在服务端。原路径保留 |

Step 文本模型 3.5/3.7 的对照脚本属于隔离实验，没有把所有业务模型默认切换成 Step；不能只改 `AI_MODEL` 就宣称全部模块兼容。Smart Turn 有独立试验记录，没有替换默认轮次判断。

自动校对要由新客户端读取 capabilities，上传时携带所选 policy；旧客户端不传仍走原流程。不要手工伪造 receipt 或把自动稿当成本人确认稿。本轮无新增数据库迁移，仍需按现有迁移工具确认环境 revision。

## 4. 发布顺序与回退

1. 保存当前发布目录、各服务配置、数据库与音频备份，在隔离环境检查恢复。
2. 新目录检出明确提交；安装 locked 依赖，确认现有迁移 revision；先保持新开关关闭。
3. 升级 AI Core，检查 `/health` 与新内部接口；再升级 API、worker、人物后台任务，使它们使用一致源码与配置。
4. 隔离账号开启自动校对，走“原音→ASR→模型修订→本人确认→记忆→修订再问”；另测旧客户端、超时、撤权和晚到结果。历史材料不自动重写。
5. 开启指定账号的语音路线，使用同题多轮和真实手机检查后再扩大范围。
6. 从已提交源码执行 `tools/delivery/build_signed_internal.py --signing-dir PRIVATE_DIRECTORY --output NEW_OUTPUT_DIRECTORY`。复用固定签名，保存 APK 哈希、source commit、能力范围及证书信息。此脚本需要本机 Android 工具链，路径可由 `--toolchain` 指定。
7. 验证客户端与服务器版本组合后，再更新 GitHub Release 与下载说明。CI debug APK 指向模拟器宿主机，不可充当云端内测包。

关闭校对开关可停止新录音使用该工序；已保存机器稿、修订稿和核对稿保留。关闭 Step 开关撤回试用入口。应用回退用旧目录与对应配置，不通过清库、覆盖原音或撤销用户授权回退。

## 5. 工具与证据的使用边界

- `tools/a01_eval`：固定样例、原始 ASR、记忆修订与校对评测。部分脚本依赖原工作区样例和私有配置，不能声称干净克隆后一键运行全部历史实验。
- `tools/voice_call/benchmark_*`、`probe_*`、`record_*`：隔离模型比较、延迟探针与模拟器原速录像。先读参数和对应报告，真实调用有费用/配额。
- `tools/voice_call/stage_*`、`cutover_*`、`deploy_*`：保留当日服务器操作记录，含固定目录、端口和 systemd 名称。它们会修改服务器，**不是新电脑初始化步骤，也不要直接重跑旧日期脚本**。新发布按上节准备新目录与恢复方案。
- `docs/agent-loop/evaluations` 与 `evaluations/a01-*`：公开虚构样例和模型输出。作者身份、未知项、失败记录一并保留，不作真人人格认可证据。
- [原速视频](demos/20261015/README.md)可以直接从仓库下载；更完整的运行库、原始音频/日志保留在本机忽略目录，由维护者按必要范围提供，不公开打包凭据。

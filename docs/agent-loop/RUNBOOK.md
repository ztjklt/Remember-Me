# 勿忘我 · 本机 Agent 工作台

2026-10-07。实现分支 `codex/agent-real-loop`，基线 `develop@4dc3d5a`。
当前目录 `D:/codex_work/remember-me-agent-loop`。未推送、未合并、未发布。

## 能做什么

两个独立身份登录，同一人物空间分 owner / reader。录音或导入实际音频，
保存原音后由本机 Whisper 转写。本人核对文字后才调用云端 AI Core。
支持完整故事授权、撤权、来源问答、人物证据视图、补充/纠正/时间变化、
读者问题单，以及沿用已有的锁定答案校准。

不要将工作台当成手机验收，也不要将确定性测试里的模型替身当成真实 AI。
当前真实云端验收被缺少 `AI_API_KEY` 阻塞。未接入服务时会保留录音与文字，
显示失败并允许重试，绝不会自动切换到 fixture/fake。

## 这台机器的启动方式

1. 进入 `D:/codex_work/remember-me-agent-loop/services/backend`。
2. Python 环境：`D:/codex_work/remember-me-review/verification-venv/Scripts/python.exe`。
3. 数据库已迁移，两个测试身份已经创建，凭据只保存在
   `services/backend/var/local-identities.json`（Git 忽略）。不要发到群里或提交到 Git。
4. 运行 `python run_workbench.py`；打开 <http://127.0.0.1:8877/workbench/>。
   端口：Backend 8877、STT 8878、AI Core 8879；只监听本机。
5. 两个独立浏览器会话分别用 owner / reader 的 `actor_token` 登录。
   分享时输入 reader 的 `actor_id`，不是他的 token。

启动器日志在 `services/backend/var/`。Ctrl+C 会结束它创建的服务进程。
没有密钥时 AI Core 不启动，但 Backend、STT、Worker 可以运行。
启动器不自动执行迁移；迁移前先备份已有数据库和对象存储。

## 配置真实云端模型

在 **`services/ai-core/.env`** 中配置以下字段。密钥只在本机文件中填写，
不要粘贴进聊天、网页或命令行参数：

```dotenv
AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash
AI_MODEL_VERSION=deepseek-v4-flash
AI_API_KEY=
AI_TIMEOUT_SECONDS=90
```

这些模型名称来自仓库现有适配器，本轮没有用真实密钥验证账户对该模型的访问能力。
填好后重启启动器，在故事列表点“重试处理”；不必重新上传已保存的原音。
只用本目录的专用测试故事验收，不能默认发送私人日记或真实病史。

## 新机器安装

- 安装 Python 3.12+ 和 backend、ai-core 各自 pyproject 中的运行依赖；
  另安装 backend 的 retrieval 依赖。服务都在自己的目录运行，避免两个 `app` 包互相覆盖。
- 安装 ffmpeg、[官方 whisper.cpp](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.9.2)
  和[多语言 base 模型](https://huggingface.co/ggerganov/whisper.cpp)。不要使用 `.en` 模型。
- 这台机器使用 whisper.cpp v1.9.2 Windows x64，下载包 SHA256：
  `49dcc16de826f20bd53d44f947a1ae49dfa81f86cad67a64d80820cb192d674a`。
  base 模型 SHA256：`60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe`。
- Backend `.env` 可参考 `.env.workbench.example`。
- 在 backend 运行 `python -m alembic upgrade head`，再运行
  `python -m app.workbench_setup --output var/local-identities.json`。
  已存在身份文件时拒绝覆盖；不要反复创建新身份代替登录。
- Windows 文件访问依赖 NTFS 权限；POSIX chmod 测试不等价于 Windows ACL 验证。

## 旧数据兼容与权限变化

迁移增加 nullable owner、故事授权、修订与问题单；不删除旧录音。
旧人物空间不会自动认领。管理员核实对应关系后执行：

```text
python -m app.workbench_setup --map-subject <原 subject_id> --owner-actor <已有 actor_id>
```

该命令不允许转移已有所有者。未映射人物空间不能被读者共享访问。
已有自授权记录不能创建所有权；legacy Episode 接口也按当前所有者检查。
旧 Android 上传路径保持原语义，本轮工作台使用 IMPORT 并强制转写核对。
手机端下一步应接同一套核对/授权接口，不得伪装成 iOS 来源。

## 本轮有意保留的边界

- 记录者和读者由本机管理员创建，尚无生产登录、找回账号与公共注册。
- 共享按整段故事，不支持片段级音频授权；撤权不能收回已经保存的副本。
- 一个故事内有被纠正的记忆时，读者的该故事显示不可用，避免旧全文继续误导；
  新修订必须另行授权。细粒度分享留待后续设计。
- 人物页面是按可见证据组织的四个视图，没有声称完成心理画像或稳定人格学习。
- 波形来自实际音量；原音使用浏览器真实播放器。没有时间对齐模型，故播放完整原音。
- 浏览器录音停止后、上传前暂存在页面内存；离开有提示并可下载。
  后台切换会停止录音，但这不是原生手机的后台持久化验收。
- SQLite 的短事务与来源版本回查已测试；PostgreSQL 并发语义未验收，不得直接宣称可生产多用户部署。
- 暂无真实麦克风录制验收、真实云端模型验收、手机验收或目标用户测试。

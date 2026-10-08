# 勿忘我 · 本机 Agent 工作台

更新于2026-10-08。实现分支 `codex/agent-integration`，基线 `develop@4dc3d5a`。
当前目录 `D:/codex_work/remember-me-agent-loop`。未推送、未合并、未发布。

## 能做什么

两个独立身份登录，同一人物空间分 owner / reader。录音或导入实际音频，
保存原音后由 Groq 云端 Whisper 转写（不是本地模型）。本人核对文字后才调用微信云端 AI Core。
支持完整故事授权、撤权、来源问答、人物证据视图、补充/纠正/时间变化、
读者问题单，以及沿用已有的锁定答案校准。

不要将工作台当成手机验收，也不要将确定性测试里的模型替身当成真实 AI。
当前密钥已在被忽略的服务端配置中配置，真实结果见 [10月8日验证](GROQ_LIVE_RESULTS_2026-10-08.md)。未接入服务时会保留录音与文字，
显示失败并允许重试，绝不会自动切换到 fixture/fake。

## 这台机器的启动方式

1. 进入 `D:/codex_work/remember-me-agent-loop/services/backend`。
2. Python 环境：`D:/codex_work/remember-me-review/verification-venv/Scripts/python.exe`。
3. 数据库已迁移。当前三组月度故事的六个独立身份在
   `services/backend/var/monthly-eval/cloud-asr-runs/relay-compact/identities.json`（Git 忽略）。
   其中每组有 owner / reader；`var/local-identities.json` 是早期空白工作台身份，不是这批月度材料。不要将凭据发到群里或提交到 Git。
4. 运行 `python run_workbench.py`；打开 <http://127.0.0.1:8877/workbench/>。
   端口：Backend 8877、AI Core 8879；只监听本机。不启动本地 STT 8878。
5. 两个独立浏览器会话分别用 owner / reader 的 `actor_token` 登录。
   分享时输入 reader 的 `actor_id`，不是他的 token。

启动器日志在 `services/backend/var/`。Ctrl+C 会结束它创建的服务进程。
没有文本密钥时 AI Core 不启动，但 Backend、Worker 可以运行。Groq 缺密钥则明确失败，不切换服务商。
启动器不自动执行迁移；迁移前先备份已有数据库和对象存储。

## 配置真实云端模型

在 `services/backend/.env` 中设置云端 ASR（已有密钥不要重新写入文档）：

```dotenv
REMEMBER_STT_BACKEND=groq
REMEMBER_START_LOCAL_STT=false
REMEMBER_GROQ_API_KEY=
REMEMBER_GROQ_ASR_MODEL=whisper-large-v3
```

Groq 走官方 `/openai/v1/audio/transcriptions`；转写只收到音频，不收到创作稿或标准答案。
当前主机通过已配置的环境代理连接 Groq 成功。压缩传输副本后发送，原 WAV 不变；保存原始 ASR，再生成简体核对草稿。
切换 ASR 路线必须重新确认云端政策；旧路线排队任务不会自动发往新服务。

在 **`services/ai-core/.env`** 中配置以下字段。密钥只在本机文件中填写，
不要粘贴进聊天、网页或命令行参数：

```dotenv
AI_PROVIDER=weixin
AI_BASE_URL=https://chatapi.weixin.qq.com/openai/v1
AI_MODEL=Deepseek-v4-flash
AI_MODEL_VERSION=Deepseek-v4-flash
WEIXIN_CHAT_API_KEY=
AI_TIMEOUT_SECONDS=45
AI_MAX_CONCURRENT_REQUESTS=1
```

这是用户指定的微信兼容接口，模型大小写按原样保留。小米密钥不可用于它。
采用json_object并保留完整本地结构/证据校验，不启用未验证的thinking/tools。
填好后重启启动器。待核对故事须先听原音、保存核对文字并明确确认云端处理；
已经核对但处理失败的故事才使用“重试处理”。不必重新上传已保存的原音。
只用本目录的专用测试故事验收，不能默认发送私人日记或真实病史。

## 新机器安装

- 安装 Python 3.12+ 和 backend、ai-core 各自 pyproject 中的运行依赖；
  另安装 backend 的 retrieval 依赖。服务都在自己的目录运行，避免两个 `app` 包互相覆盖。
- 安装 ffmpeg 用于音频格式转换；本轮不需要下载 Whisper 程序或本地语音模型。
- Backend `.env` 参考 `.env.example` 的 Groq 配置。`.env.workbench.example` 保留早期本地 STT 示例，不应用到当前云端验证路线。
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
本轮ANDROID_MIC也强制等待核对；工作台使用IMPORT，手机不伪装成iOS。
Android运行adb reverse tcp:8877 tcp:8877，输入http://127.0.0.1:8877。

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
- 已有 API35 模拟器的安装、登录、原音播放及录音权限/后台保存检查；
  真实云模型已有本机技术闭环实测；暂无真人麦克风、实体手机或目标用户验收。详见本轮验收记录。


## 融合后的入口

本机API35模拟器名`remember-me-integration`，AVD目录`D:/codex_work/remember-me-toolchain/avds`，SDK目录`D:/codex_work/remember-me-toolchain/sdk`。当前使用WHPX和swiftshader，验证会话`emulator-5554`。
安装最终APK后执行`adb -s emulator-5554 reverse tcp:8877 tcp:8877`，APP后端地址为`http://127.0.0.1:8877`。
需要重新启动该模拟器时，设置`ANDROID_HOME`和`ANDROID_AVD_HOME`为上述目录，使用SDK的`emulator/emulator.exe -avd remember-me-integration -no-snapshot -gpu swiftshader`。实体设备另行授权USB调试并使用其实际serial，不与模拟器验证混记。
月度材料的六个身份存于`services/backend/var/monthly-eval/identities.json`，不是旧双身份文件；三个故事已核对并完成云端整理；测试曾授权读者并在收尾撤权，当前需要Owner在界面再次主动授权。

新增0009人物候选和0010答案来源版本迁移；迁移前备份SQLite及objects，本机已用数据库副本检查完整性。人物页可排队归纳、确认/拒绝，读者不能取得所有者私人候选。新依据到来后旧候选显示过期。

月度素材见evaluations/monthly-integration-v1/README.md。独立六个测试Actor在services/backend/var/monthly-eval/identities.json；三个owner各自管理一个虚构人物空间，三个reader分别授权。不要把身份凭据或云端密钥放进Git。

原音、raw ASR、product ASR分别留存。微信密钥已配置，三个样本已完成实际提取、保存和问答。最新技术闭环见LIVE_LOOP_2026-10-07.md；sample-gate.json的人工听读条件尚未通过，不把技术运行改写为质量通过。

网页花园采用PR85资产，入口只绑定后端有效故事/记忆ID。最新验证状态以INTEGRATION_ACCEPTANCE.md为准，旧ACCEPTANCE.md保留上一批历史证据。

简体转写：Whisper 指定 zh 并提供简体提示；OpenCC t2s 生成简体核对草稿，原始 ASR 单独保留。已确认文字不自动转换。详见 [本次补验](STT_SIMPLIFIED_2026-10-07.md)。


## 本轮真实运行补充

启动仍用services/backend目录的 `python run_workbench.py`。微信密钥保存在AI Core被忽略的.env中，启动器映射WEIXIN_CHAT_API_KEY，不进前端。当前8877为后端，8878为STT，8879为AI Core，仅本机访问。
后续STT使用 `D:/codex_work/remember-me-toolchain/whisper/ggml-large-v3-turbo-q5_0.bin`，下载文件已核对官方SHA1 e050f7970618a659205450ad97eb95a18d69c9ee；原有三段base转写不自动重写。
独立技术循环身份在 `services/backend/var/monthly-eval/state-loop/identities.json`，与月度六身份分开。该空间最后做过删除并发测试，不是完整初始故事快照。
整理成功却0条记忆时可按“未提取到记忆，重新整理”；服务端校验只有从未产生记忆行的录音可使用此入口。

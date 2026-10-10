# 团队接手：运行、配置与验收

不用构建源码、只想体验 App 时，先看 [简明使用说明与专用公开演示账号](ANDROID_QUICK_START_2026-10-10.md)。原四组独立内测账号仍私下交接；公开演示账号不能保存私人材料。

对应 `codex/team-handoff-20261010`。先阅读 [当前交接](TEAM_HANDOFF_2026-10-10.md)，不要以旧 RUNBOOK 的 Groq/电脑接力描述推断本次 ECS 状态。

## 路线 A：使用已部署 ECS 演示（会议优先）

1. [下载当前签名内测 APK](ANDROID_QUICK_START_2026-10-10.md)，或按照下节从本分支构建。服务地址 `https://39.108.183.47`，包名 `me.remember.app.internal`，当前版本 `0.8.1-internal`；旧包留作历史记录。
2. App IPv4 HTTPS 已经所有者批准开放，网络无需固定 Wi-Fi；注册仍关闭。管理员分别提供两个普通内测账号；凭据通过私下受控方式交接，不发到 PR/仓库。
3. 登录 → 今天录音并试听 → 同意云端转写并上传 → 档案核对机器稿 → 确认云端整理 → 故事/记忆/原音 → 对话 → 人物待核对建议。
4. 本人预览完整录音分享范围 → 创建邀请 → 亲友登录领取 → 本人核对账号并批准 → 亲友进入授权空间、播放、提问。
5. 问没有材料的问题，提交补问；本人补录后另行分享。最后撤权，检查原音和派生内容不能继续读取。

APP 不需要模型密钥、`actor_id`、SSH 隧道、ADB reverse 或电脑 ASR。ADB 可用于安装和截图，不能把它当会议业务链路的必要条件。服务器端 ASR 是 Paraformer V2，文字模型是微信 `Deepseek-v4-flash`。

IP HTTPS 使用范围受限的测试证书，有效期截至 2027-01-07；不能关闭 TLS 校验解决连接失败。自助注册关闭，由管理员运行 `python -m app.account_admin create 用户名 --name 昵称`（密码交互输入）创建账号。管理员须加载现有服务配置和正确数据库，不直接改数据库行。重置使用 `reset 用户名`，会撤销已有设备会话。

**APK 与截图版本分开**：19 张截图对应当天首次实跑包，SHA-256 `3b09e67db50572933451ca7d0c7a7bedd21a526b8f7425ecdede9424cb35cec6`。本交接目录的重新构建包及复验结果见 [验证清单](HANDOFF_VALIDATION_2026-10-10.md)，不要要求不同构建产物哈希相同。

## 路线 B：从干净源码构建 Android

前提：JDK 17、Android SDK 35、Node（契约测试可选）、Git；设置 `JAVA_HOME` 和 `ANDROID_HOME`。不需要 Android 本机 ASR 权重；仓库保留的旧 sherpa AAR 使 APK 约 149 MB，后续需要单独评估移除历史依赖，不能在本次交接中贸然删库。

```powershell
git fetch origin
git switch --track origin/codex/team-handoff-20261010
cd apps/android
.\gradlew.bat testDebugUnitTest assembleDebug -PrememberServiceUrl=https://39.108.183.47
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n me.remember.app/.MainActivity
```

这会构建独立开发包 `me.remember.app`；默认 debug 地址是本机 8877，所以上面的 `rememberServiceUrl` 参数不能省。非 Windows 使用 `./gradlew`。首次构建需访问依赖仓库；本次本机验收使用已有依赖缓存，不能宣称全新离线电脑也能直接构建。

构建固定签名内测包：管理员在进程环境安全设置 `REMEMBER_INTERNAL_KEYSTORE`、`REMEMBER_INTERNAL_STORE_PASSWORD`，签名别名 `remember-internal`。然后运行：

```powershell
.\gradlew.bat assembleInternal assembleInternalAndroidTest -PrememberTestBuildType=internal
adb install -r app/build/outputs/apk/internal/app-internal.apk
```

`internal` 构建已固定 ECS 地址并保留该 IP 证书验证，非 debuggable。私钥和口令不进仓库，也不要求每位队友获得管理员签名私钥。同包名安装更新需要同一签名；新签名不要覆盖用户已有录音。签名安装包作为 GitHub 预发布附件交付，不把 149 MB 二进制提交到 Git。PR 的 Android CI 附件另为默认连接 ECS 的 debug 包，包名和签名不同，不能拿它更新内测包。

## 路线 C：本地真实后端开发（与 ECS 数据隔离）

不要复制 ECS 或个人数据库到 Git。Python 3.12+、uv；Paraformer 和微信密钥由有授权的管理员在忽略的 `.env` 配置。比赛 ASR 协议不同需编写适配器，不能保证只改 URL 和 key 就兼容。

分别安装锁定依赖：

```powershell
cd services/backend
uv sync --locked --extra retrieval
New-Item -ItemType Directory -Force var
Copy-Item .env.cloud-demo.example .env
# 在本机编辑 .env 中的工作空间主机与密钥，不粘贴到命令行或聊天。
uv run alembic upgrade head
uv run python -m app.account_admin create owner-demo --name 记录者
uv run python -m app.account_admin create reader-demo --name 亲友
```

```powershell
cd services/ai-core
uv sync --locked
Copy-Item .env.cloud-demo.example .env
# 在本机编辑微信密钥；保持模型和端点不变。
uv run uvicorn app.main:app --host 127.0.0.1 --port 8879
```

另开三个终端，工作目录都为 `services/backend`（各自读取该目录 `.env`）：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8877
uv run python -m app.worker
uv run python -m app.profile_worker
```

这三条是三个持续进程，不是在同一终端依次等待完成。中文检索依赖 `BAAI/bge-small-zh-v1.5` 的固定版本 `7999e1d3359715c523056ef9478215996d62a620`，首次使用需取得相应模型；这是服务端检索嵌入，不是本地 ASR。下载不可用时应按错误提示补模型，不伪造检索结果。

本地开发包连接可以显式使用 `adb reverse tcp:8877 tcp:8877` 与默认 debug 地址，但这只是开发路线，不能拿它证明无电脑 ECS 演示。浏览器工作台 `http://127.0.0.1:8877/workbench/` 仍是辅助调试界面；会议以 Android 原生普通账号流程为准。

`.env.cloud-demo.example` 的 ASR 地址必须是 `https://llm-工作空间标识.cn-beijing.maas.aliyuncs.com` 主机，**不含 `/compatible-mode/v1`**。真实适配器使用文件上传及异步识别协议，不是 Chat Completions。未填密钥应明确失败，不能切到 fixture。

## 自动测试与实跑的区别

```powershell
# 在 services/backend
uv run pytest
# 在 services/ai-core
uv run pytest
# 在 packages/contracts
npm ci
npm test
# 在 apps/android
.\gradlew.bat testDebugUnitTest
```

上述确定性测试会使用隔离数据库和外部请求替身；它们不能代替真实模型、ECS、手机测试。PostgreSQL 专项测试需按 [双角色验收记录](PAIRED_DELIVERY_RECOVERY_2026-10-10.md)准备明确的隔离测试库，不得给测试配置正式数据库。

`MeetingDemoLiveTest.kt` 是显式实跑测试，会产生真实故事、调用和问题单，不属于日常单元测试。现场 19 图由该测试实际操作产生。复跑需要专用虚构语音、普通账号和受 token 保护的模拟器音频注入，不能直接把忽略目录复制给别人：

- 构建/安装 matching 的 internal 应用和测试 APK。
- 将运行者自行配置的 JSON 写入设备 `/data/local/tmp/remember-meeting.json`：`account` 和 `reader` 各含 `username/password/actor_id`，另含 `phase` 与 `question`；真实值不能放仓库。
- `record` 需要在测试的 `mic-start` 标记后注入合成音频，完成后写 `mic-done`；收到 `audio-ready` 后必须校验保存音频确有信号再写 `audio-checked`，不能跳过信号检查。主机自动注入脚本目前仍为本地工具，不宣称已提供一键可移植版本。
- 已保存检查点后可使用 `resume` 复查故事/原音/问答，`portraits` 请求人物整理，`share` 执行完整邀请链，`reader` 从已批准邀请继续。没有前序检查点的设备不能用 resume。
- 执行 `adb shell am instrument -w -r -e class me.remember.app.MeetingDemoLiveTest me.remember.app.internal.test/androidx.test.runner.AndroidJUnitRunner`。测试后删除设备临时凭据，不删除故事原音或失败历史。

直接手动操作 APP 完成真实录音不需要以上注入工具；仿真音频步骤只是自动验收方法，不是产品使用条件。

持续主机测试时需保留 `am instrument` 进程及其输入连接。本轮遇到宿主 ADB shell 退出导致 UiAutomation 截图 Binder 断开的失败；改为设备端 `nohup sh -c 'am instrument ... > /data/local/tmp/run.log 2>&1; echo $? > /data/local/tmp/run.done' </dev/null >/dev/null 2>&1 &` 后轮询完成标记、拉取日志，并要求明确 `OK (1 test)` 与状态码 `[1, 0]`。不能只凭存在旧截图判通过。

## 后端升级与回退

原交接没有部署应用变更；随后为队友下载体验，经所有者明确批准开放 App HTTPS，并创建普通内测账号。网络配置备份、范围和回退见 [下载说明](ANDROID_TEAM_DELIVERY_2026-10-10.md)。后台应用仍为 `c2e17fc`，没有同步未验收语义实验。需要升级时仍按 [ECS 操作说明](ANDROID_PAIRED_OPERATIONS_2026-10-09.md)执行：隔离测试库 → 备份并实际恢复验证 → 新发布目录和锁定依赖 → 增量迁移 → 四服务就绪 → 实际网络冒烟 → 切换 → 失败回退应用。不得以清空数据库、删除原音、开放注册或关闭证书校验解决失败。

当前本机工具中的 SSH 别名、服务器目录和部分历史测试路径属于既有环境。队友可按以上标准入口启动自己的开发环境，不能假定他们拥有原电脑的私钥、缓存、密钥或已建账号。

随后晚间转写排查：ECS 在 `c2e17fc` 基础上仅启用 ASR 失败提示补丁，当前目录为 `paired-c2e17fc-asr-hint-f3bff5de`；原目录保留，数据库、供应商、网络和 APK 均不变。具体原音完整性、上游错误、测试及回退记录见 [晚间 ASR 排查](ASR_FAILURE_DIAGNOSIS_2026-10-10.md)。旧的“任务未成功，原音保留”不表示上传丢失；成功转写仍须本人确认文字后才整理记忆。

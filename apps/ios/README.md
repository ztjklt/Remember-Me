2026-10-16 最新源码快照：**1.17.0 / 2026101614**，包含采集草稿／一次保存、Android 风格原生记忆花园、现有实时语音与游客能力，以及录音豆扫描 UUID 过滤修正。GitHub 上传范围、SDK 准备与本次实际检查见[快照记录](../../docs/verification/IOS_GITHUB_SNAPSHOT_2026_10_16.md)。源码上传不代表已更新手机或线上后端；此前各版本的安装记录保留在下方。

2026-10-16 游客暗号托付：本地已实现亲友免账号、具体私密暗号对应专属记忆库；Twin 内本机录入与核对、完整来源预览、游客文字／语音命中及范围锁定已接通。Backend 913项通过（6跳过）、Contract 59项、iOS 78项单元和3项UI检查通过。本轮未部署或安装本人手机，见[验证记录](../../docs/verification/IOS_GUEST_ENTRUSTMENT_2026_10_16.md)。

2026-10-16 记忆花园源码更新：AI 故事／事件自动展示，时间线与图谱合并，右侧复用已有素材；详情支持原音、手动编辑与删除（保留原音）。70 项模拟器逻辑／界面检查通过；尚未安装实体手机。见[本轮验证](../../docs/verification/IOS_GARDEN_EVENT_STORIES_2026_10_16.md)。

2026-10-16 切页弹窗修复：**1.13.3 / 2026101601** 已覆盖安装到「黑幕」。正常取消刷新／旧聊天加载不再显示“需要留意／已取消”；62 项相关测试通过，9 个原音文件保留。安装后手机锁屏，待解锁打开。见[修复记录](../../docs/verification/IOS_CANCELLED_REFRESH_2026_10_16.md)。

2026-10-16 已统一部署：通话绿色声纹姓名与默认手机外放已覆盖安装到「黑幕」，版本 **1.13.2 / 2026101508**；CloudBase045 与原语音 Agent 已更新。合成声纹姓名匹配／撤销检查通过；长静默后第三轮回归超时，解锁后已确认新版启动。详见[发布与限制](../../docs/verification/IOS_SPEAKER_DISPLAY_DEPLOYMENT_2026_10_16.md)。

2026-10-15 通话外放适配：默认手机扬声器＋内置麦克风，无需绑定蓝牙；可切换听筒／耳机，扬声器模式不因无关蓝牙断开而挂断。23 项通话逻辑及 2 项 UI 检查、签名构建通过；尚未安装真机，待统一发布。[验证记录](../../docs/verification/IOS_VOICE_SPEAKER_OUTPUT_2026_10_15.md)。

2026-10-15 自然采集修订：iOS **1.11.0 / 2026101503** 已安装到「黑幕」，CloudBase039 / `796591a` 与原语音Worker已更新。点击开始确认用途，去掉固定同意句及重复开关；名字没听清也继续记录。正常语音聊天自动留原话，并累积短句后台准备音色，无需另录一遍。真实三轮通话／自动采集与无口令双人ASR通过，见[验证记录](../../docs/verification/IOS_NATURAL_CAPTURE_2026_10_15.md)。

2026-10-15 多人录音：**1.10.0 / 2026101502** 已安装到「黑幕」，CloudBase037 / `4e78742` 已上线。入口「录音 → 我的录音 → 多人录音」；依次语音自我介绍后自动关联本段发言，无手动确认姓名。后端完整及删除终态定向回归、34 项契约与 8 项 iOS 检查通过；公网合成双人完整流程通过，原有四段本机原音保留。仅同段识别，真人／相近声音准确率仍需实际录音验证。见[交付与限制](../../docs/verification/IOS_SPEAKER_INTRODUCTIONS_2026_10_15.md)。

2026-10-15：**1.9.1 / 2026101501** 已覆盖安装到「黑幕」并正常启动。录音首页只保留勿忘我、开始录音与「我的录音」入口；「记忆」直接进入记忆花园，去掉搜索并增加已有事实到原文的图谱展示；本人音色改为照读给定文案、试听确认后复刻，无需重复打字。键盘支持明确收起与离开输入区收起，文字草稿保留。79 项定向检查、签名构建及设备版本核对通过，四段既有原音及档案的文件元数据一致。[修改与验证记录](../../docs/verification/IOS_CAPTURE_GARDEN_VOICE_FEEDBACK_2026_10_15.md)。

2026-10-15：按本人要求，从当前工作区重新构建 **1.9.0 / 2026101410** Release，包含勿忘我原生 UI。已覆盖安装到「黑幕」，独立核对设备版本并正常启动；未卸载或清空应用，旧本机录音文件仍在。[安装记录](../../docs/verification/IOS_DEVICE_INSTALL_2026_10_15.md)。

2026-10-14：**1.9.0 / 2026101410** Release 包版本与签名已核对，新增「孪生 → 复刻验证」入口；15 项单元与 3 个不同 UI 场景通过。个人训练候选与当前孪生一致率验证分别显示，资料不足时不显示虚构百分比。本次「黑幕」设备查询为 unavailable，尚未覆盖安装或确认真机启动。

2026-10-14：**1.8.2 / 2026101405** 已安装。默认声音可先通话，本人音色复刻显示进度并可试听；完整结果见 [验证记录](../../docs/verification/IOS_DEFAULT_VOICE_AND_READINESS_2026_10_14.md)。

2026-10-14：当前真机 UI 版本 **1.8.3 / 2026101408**。孪生／通话／旧聊天界面与 9 项不同 UI 验证见[记录](../../docs/verification/IOS_TWIN_UI_2026_10_14.md)。

> **当前入口：** iOS 日常流程已改为「录音 / 记忆 / 孪生 / 我的」四个中文入口。旧 Android 风格页面保留在源码，以下旧版记录只说明历史实现。

> **记忆花园交付：** 1.8.0 / 2026101402（2026-10-14）。「黑幕」覆盖安装、设备版本核对与启动成功。入口为「记忆 → 进入记忆花园」，支持故事／人物浏览、搜索、来源、本机移出与恢复；本人真实内容体验待本人操作。[本次交付记录](../../docs/verification/IOS_MEMORY_GARDEN_2026_10_14.md)。前台实时语音的本人音色与耳机验收另见[语音交付记录](../../docs/verification/IOS_VOICE_COMPLETION_2026_10_14.md)。

> **2026-10-08 Android 原型复刻：** 五个入口改为 Portrait / Graphs / Memories / Agents / Me，复用队友 #81 的画像卡片与关系图布局。已有 iOS 录音、证据问答、五维校准和独立声音授权保留；可先保存本地录音，再连接服务。范围与本地验证见 [复刻记录](../../docs/verification/IOS_ANDROID_PARITY_2026_10_08.md)。

# iOS 记忆服务与本机录音

## 2026-10-13 中文简明流程

**Remember Me iOS 1.3.0 / 2026101303** 使用四个中文入口：

- **录音**：开始录音，完成后在同页确认原音转写用途；识别完成后核对文字，点「确认文字并整理记忆」，完成后直接「查看记忆」。允许暂不上传、离线保留原音；本机和云端的同一段录音只显示一次。
- **记忆**：显示全部有效记忆，可搜索、回听来源、纠正或删除；来源详情仍保留。
- **对话**：直接进入 Twin，支持文字／语音问题、授权用途说明以及有证据的回答。隐藏日常流程中的声音生成和校准入口。
- **我的**：账号／服务连接、麦克风设置、撤销 Twin 授权。已实现的人物审核放到「更多：核对人物理解」。

图谱示意、Agent 仪表盘、尚未接入的环境／声音状态分析、云端声音克隆等不再作为日常入口。既有本机录音、账号连接、服务端记忆和审核能力保留；本机连接也仍可在账号页切换。本次没有修改共享 Backend Contract、重新提交既有录音或自动生成新授权。

本轮验证：LocalRecordingTests 13 项、ECSConnectionTests 9 项、SimpleFlowUITests 3 项通过，共 25 项。界面测试覆盖中文四入口、隐藏未完成入口、录音确认的取消路径、账号连接和收起的人物审核入口；四个主页面及录音页截图已检查。首次录音确认的取消按钮测试失败，改成带明确取消的原生 alert 后复验通过。截图检查后还修正了未登录时误提示 Mac 的文字；最终签名真机构建通过，App 包核对为 1.3.0 / 2026101303，已覆盖安装到 iPhone 15 Pro Max「黑幕」并由 devicectl 确认启动；没有卸载或清空既有容器。自动化使用隔离的测试数据，没有替本人录音、确认转写或发起模型请求。真人的新录音到阅读／问答体验仍由使用者在新版设备上验证。

## 2026-10-13 录音完成状态修复

**Remember Me iOS 1.2.2 / 2026101302** 修复 Agents 把非空的完成状态误显示为“有处理任务”，并在读取当前本人空间的云端录音时同步同一使用者、同一服务的本机档案状态。回到 App 时重新刷新并恢复当前录音状态查询；本机详情也支持刷新。原音与已核对文字保持保留，其他账号／空间的本机记录不更新。

本次只读查询看到内测账号一段约 11 秒 IOS_MIC 录音为 ready、3 条 Memory，模型为 DeepSeek Flash；用户仍报告页面显示处理，因此不把服务端完成冒称为手机显示已验收。LocalRecordingTests 13 项及 ECSConnectionTests 9 项通过（共 22 项），新增覆盖跨空间隔离、原音／核对文字保留、完成与待核对／失败状态区分。签名真机构建通过，实际 App 包版本核对为 1.2.2 / 2026101302，已覆盖安装到 iPhone 15 Pro Max「黑幕」并由 devicectl 确认启动；尚未读取实体手机页面来验证显示。没有改 Backend Contract、重新提交录音或替本人确认新授权。

## 2026-10-13 独立云端内测版

**Remember Me iOS 1.2.1 / 2026101301** 已签名安装到 iPhone 15 Pro Max「黑幕」并确认启动。云端入口改为独立 CloudBase 的 `https://remember-ios-api-327435-12-1411199312.sh.run.tcloudbase.com`，使用系统 HTTPS 证书验证且拒绝重定向；已保存的 Mac／旧 ECS 配对继续使用原 pin。当前工作区已有的人物审核代码保留，未改共享 Backend Contract。

打开 **Me → 连接服务 → 云端服务 → 检查连接 → 登录云端服务**。独立账号为 `jitian`，初始密码在本次后端 worktree 的 ignored `build/private/ios-internal-account.json`，仅私下交接。新空间为空，本人录音／CLOUD_TWIN／VOICE 权限由手机自行确认。

云端采用普通百炼 `paraformer-v2` 转写、DeepSeek Flash 整理和回答；provider Key 只在后端。一次使用流程为 **保存录音 → 同意云端转写 → 核对文字 → 确认整理 → Agents / Twin 提问**。每分钟私有 Event 函数推进任务，手机退出后仍能处理。原音单段上限 18 MiB。

真实云端合成语音已经通过上传、转写、待核对、1 条 Memory、带来源的 ORIGINAL Twin、原音读取与匿名拒绝；语音提问和 iOS 使用的 AAC M4A 类型也通过。定时器实际推进 queued 人物候选任务到 complete、候选仍待本人确认。iOS 连接测试 9 项通过，真机构建／安装／启动通过；本人真机录音到 Twin 的体验尚待实测，云端声音克隆／本人声纹朗读未部署。详细报告在后端 worktree 的 `docs/verification/IOS_CLOUDBASE_BACKEND_2026_10_12.md`。

## 2026-10-12 人物审核版

新增 **Portrait → 核对我的理解**：查看支持原文和反例、确认／拒绝人物理解、修改整理内容与八类归属、把重复讲述归为同一故事、关联新旧理解，以及确认本人原话作为 Twin 表达范例。保存和模型整理都先进入待核对；修改后重新确认。停用理解保留录音和原文，相关旧 Twin 回答会清除。

iOS 1.2.0 / 2026101201 直接使用已批准的 `profile-candidates` 和 `narrative` Backend 接口。需要包含这些接口的新服务；旧服务会显示明确提示。模拟器与隔离 Backend 的结果、运行方法及仍待实测的部分见 [审核版验证记录](../../docs/verification/IOS_PERSON_REVIEW_2026_10_12.md)。

## 2026-10-11 ECS 接入版

当前 iOS 已新增和 Android 0.9.2 共用的 ECS 登录入口，保留 Mac 配对和本机录音。真机显示名为 **Remember Me ECS**（1.1.0 / 2026101101），本次独立安装，不覆盖原 QA App。

打开 **Me → 连接服务 → 云端服务 → 检查连接 → 登录云端服务**。使用独立内测账号，密码直接在 App 输入；注册暂未开放。首次上传前单独确认原音云端转写用途，识别后核对文字再整理。随后从 Agents 打开 Twin 并单独授权文字处理。单个本人空间自动进入，多个需选择；亲友空间和云端个人声音生成在此版暂未接入。

手机本地录音仍可离线保存、试听和本机转写。原 Mac 的录音、Episode 与旧 QA App 数据不自动迁入 ECS；Mac 配对仍在同一连接页的另一个入口。供应商密钥不进入 App。

真实 Swift 只读 ECS 接口验证、20 项自动测试、签名构建与真机安装已完成；本人新录音到 Twin 的完整真机旅程尚待使用者完成。详情见 [验证记录](../../docs/verification/IOS_ECS_CONNECTION_2026_10_11.md)。

## 2026-10-10 当前项目测试版

当前 `RememberMe.xcodeproj` 已补齐五个 Android 风格入口、多段本机录音档案、离线回放、设备支持时的本机中文转写与独立核对文字保存。原有 Mac 服务、Memory、Twin、校准和个人声音流程保留。具体差异、14 项自动测试结果及真机检查步骤见 [本次验证记录](../../docs/verification/IOS_ANDROID_PARITY_SYNC_2026_10_10.md)。

## Twin 与个人声音

现有 Mac 服务及迁移启动后，执行 `cd services/backend && uv sync --extra retrieval` 安装本机中文检索依赖；另开终端执行 `cd services/voice && uv sync && uv run uvicorn local_voice:app --host 127.0.0.1 --port 8300`。首次检索会下载 BGE 中文向量模型，首次点播会下载 Qwen3-TTS Base 权重；它们只留在 Mac 的模型缓存。AI Core 和 Voice 仍只监听本机，iPhone 只连接已配对的 HTTPS Backend。DeepSeek 密钥仍只在 AI Core 的本机环境中。

iPhone 的 Twin 页先单独询问云端推理授权，说明问题和少量相关记忆文字会发给 DeepSeek。可输入或录下问题、核对识别文字，再查看标注为原话、推测或无法确定的回答及原始 Episode 录音。个人声音需要另一项 VOICE 授权，和 5–15 秒专用样本、核对后的原话及本人声音确认；撤销会删除样本和生成的声音。App 只传保存过的回答 ID 请求朗读，不能要求合成任意文字。

校准页位于 Twin 回答下方：先锁定一条有证据的回答，再录下本人回答、核对转写并等 Episode 更新 Person Model。完成后可比较做决定、理由、价值、情绪和表达五方面，查看真实回答中的短引文和下一条建议问题。比较结果本身不作为新记忆；只有本人 Episode 会更新模型。比较失败可从同一条已完成 Episode 重试，无需重录。真机步骤仍按使用者安排延期。

这个 SwiftUI 客户端把自由录音或智能追问回答交给 Mac 上的 Backend。Backend 先保存 Episode 和原音，由本机 Whisper 转写；iOS 随即显示文字并允许修改，用户确认后才由 DeepSeek V4 Flash 提取可在确认版文字中定位的 Memory，最后更新七领域 Person Model。当前配置会把确认后的转写文本发往 DeepSeek；原音、机器原始转写、数据库和密钥仍保存在本机。客户端可播放原音、查看证据、纠正或删除 Memory。Android 仍走原有自动处理流程。

## 需要的本机环境

- macOS 上安装 Xcode、`xcodegen`、`uv`、`ffmpeg`、`whisper-cli` 与多语言 Whisper 模型（例如 `~/.cache/remember-me/ggml-base.bin`）。`ggml-base.en.bin` 不能用于中文。
- DeepSeek API key 仅通过 AI Core 进程环境变量 `AI_API_KEY` 加载；不要写进仓库、命令历史、PR 或 App。需要完全本机运行时，仍可配置 Ollama Qwen 适配器。
- iPhone 与 Mac 在同一局域网；iPhone 已信任 Mac。首次真机安装需 Xcode 的 Apple Accounts 能创建这个 App 的签名配置文件。

## 启动四个本机进程

在 Mac 选择一个私有数据目录，并确认当前局域网 IP：

```bash
export REMEMBER_LOCAL_DATA_DIR="$HOME/.cache/remember-me/live"
export REMEMBER_LAN_IP="$(ipconfig getifaddr en0)"
umask 077
mkdir -p "$REMEMBER_LOCAL_DATA_DIR/audio" "$REMEMBER_LOCAL_DATA_DIR/tls"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout "$REMEMBER_LOCAL_DATA_DIR/tls/local.key" \
  -out "$REMEMBER_LOCAL_DATA_DIR/tls/local.crt" -days 30 \
  -subj '/CN=Remember Me Local' -addext "subjectAltName=IP:$REMEMBER_LAN_IP"
```

证书和私钥只放在本机数据目录。若 IP 改变，重新生成证书并重新配对 iPhone。不要把 `local.key` 提交到仓库。

在 `services/backend` 执行迁移，并且只在空数据库里创建一次 Subject、Actor 和录音同意记录：

```bash
export REMEMBER_DATABASE_URL="sqlite:///$REMEMBER_LOCAL_DATA_DIR/remember.db"
export REMEMBER_OBJECT_STORE_ROOT="$REMEMBER_LOCAL_DATA_DIR/audio"
uv run alembic upgrade head
uv run python -m app.seed --subject-name "你的名字" --actor-name "你的名字"
```

`seed` 输出的 Actor token 不要放入仓库或聊天记录。第一次配对会另发一个只在这台 iPhone 使用的 token。

分别打开四个终端：

```bash
# 终端 1：services/backend，Whisper 仅监听 loopback
WHISPER_MODEL_PATH="$HOME/.cache/remember-me/ggml-base.bin" \
  uv run uvicorn app.local_stt:app --host 127.0.0.1 --port 8200

# 终端 2：services/ai-core；先在本终端从本机私有密钥文件加载 AI_API_KEY
AI_PROVIDER=deepseek AI_MODEL=deepseek-v4-flash \
  AI_BASE_URL=https://api.deepseek.com AI_TIMEOUT_SECONDS=120 \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8100

# 终端 3：services/backend，唯一面向 iPhone 的 HTTPS 接口
REMEMBER_DATABASE_URL="sqlite:///$REMEMBER_LOCAL_DATA_DIR/remember.db" \
REMEMBER_OBJECT_STORE_ROOT="$REMEMBER_LOCAL_DATA_DIR/audio" \
REMEMBER_STT_BACKEND=http REMEMBER_AI_BACKEND=http \
REMEMBER_STT_TIMEOUT_SECONDS=300 REMEMBER_AI_TIMEOUT_SECONDS=150 \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --ssl-keyfile "$REMEMBER_LOCAL_DATA_DIR/tls/local.key" \
    --ssl-certfile "$REMEMBER_LOCAL_DATA_DIR/tls/local.crt"

# 终端 4：services/backend
REMEMBER_DATABASE_URL="sqlite:///$REMEMBER_LOCAL_DATA_DIR/remember.db" \
REMEMBER_OBJECT_STORE_ROOT="$REMEMBER_LOCAL_DATA_DIR/audio" \
REMEMBER_STT_BACKEND=http REMEMBER_AI_BACKEND=http \
REMEMBER_STT_TIMEOUT_SECONDS=300 REMEMBER_AI_TIMEOUT_SECONDS=150 \
  uv run python -m app.worker
```

AI Core 从 DeepSeek 的 API 返回读取模型标识并写入 Memory 和 Episode，不依赖手填标签。每个新终端需要重新设置 `REMEMBER_LOCAL_DATA_DIR`，例如 `export REMEMBER_LOCAL_DATA_DIR="$HOME/.cache/remember-me/live"`。STT 和 AI Core 只监听 `127.0.0.1`；iPhone 只连 Backend 的 HTTPS 端口。启动后可用 `curl --cacert "$REMEMBER_LOCAL_DATA_DIR/tls/local.crt" "https://$REMEMBER_LAN_IP:8000/health"` 检查连通。

## 一次性配对与运行

在 `services/backend`，使用同一个数据库 URL 运行：

```bash
uv run python -m app.local_pair \
  --cert "$REMEMBER_LOCAL_DATA_DIR/tls/local.crt" \
  --url "https://$REMEMBER_LAN_IP:8000"
```

在 iPhone 上打开输出的 `rememberme://pair?...` 链接，或手动输入 HTTPS 地址、一次性配对码和证书 SHA-256 指纹。配对码 10 分钟后失效且只能用一次；长期设备 token 只保存在 iPhone Keychain。服务端只存 token 摘要。录音同意记录由本机 Subject 初始化；iOS 在每次开始录音前展示本次录音确认，并在首次使用时请求系统麦克风授权。确认时间写入该 Episode 的捕获元数据。

`xcodegen generate` 后用 `RememberMe.xcodeproj` 选择已配对 iPhone 运行。模拟器构建命令：

```bash
xcodebuild -project RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro Max' \
  CODE_SIGNING_ALLOWED=NO build
```

## 这一次的真机记录

只需完整跑一次：自由录一段中文并提交；核对和修改转写文字，确认后看到 Episode 到 `ready`、记忆原文证据和七领域模型；回答 App 给出的一条追问并再次确认转写，再检查模型版本和领域内容更新。再单独同意云端 Twin 文字处理，提一个新问题，检查原话／推测／无法确定的标记和录音证据。单独录 5–15 秒只有本人说话的声音样本，核对样本文字并授权，在有证据的 Twin 回答上点播本机合成声音。最后纠正或删除一条错误记忆，确认 trait、下一条追问及旧 Twin 回答的失效。断网时同一段录音仍在 App 内，重新提交会用相同幂等键。把设备型号、iOS 版本、Episode ID、STT／AI／Voice 模型版本和实际观察写进 PR 的 “How it was tested”。

实测的合成音频联调可以证明服务链和数据流，不应写成本人真机录音。真机录音必须由使用者在设备上亲自完成。


### 原文查找（2026-10-13）

iOS 1.3.1 / 2026101304 在「记忆」页直接显示「关键词或想找的事」输入框及「查找相关记忆」。仍提供即时文字匹配；提交后调用现有 memory-search，按内容含义查找核对后的原文。没有 MemoryItem 的命中可以打开原文与来源录音，不把原文伪装成已整理的卡片。界面显示等待、没有相关原文及失败状态；改变问题、账号或人物理解会清掉旧结果。文字修正和删除也清理旧搜索。Twin 允许已整理完成但没有抽取出卡片的录音参与提问。

本轮 API 测试验证包含 &、?、+、# 的问题完整编码，以及原文命中解码。24 项单元测试、4 项 SimpleFlow 界面测试通过。第一次导航栏搜索框未在界面测试中显示，最终改成页面内常驻输入框；最终界面测试及截图检查通过。签名真机构建通过；安装结果另记下方。自动化使用隔离数据，没有替本人核对录音或确认人物候选。

设备安装：devicectl 已覆盖安装 iOS 1.3.1 / 2026101304；没有卸载或清空容器。自动启动被设备锁屏阻止，待本人解锁或自行打开。

最终查询编码修正：服务器表单解码中的字面 + 已转义，ECSConnectionTests 11 项复验通过；随后再次完成签名真机构建和覆盖安装。其余 LocalRecordingTests 13 项及 SimpleFlowUITests 4 项的结果仍适用。


### 本人反馈与表达（2026-10-13）

iOS 1.3.2 / 2026101305 对话页新增「纠正这条回答，让 Twin 更了解我」：先锁定有证据的回答，再录本人真实答案、核对转写、比较五个维度。比较完成后可进入「整理并核对我的新理解」，继续使用已有候选生成和本人确认；差异诊断不自动确认成性格。对话页可以直接进入人物与表达审核。

iOS 现在消费后端已有 expression 字段，仅显示有效 SIMULATION / available 的核对措辞，并保留内容依据；原话、过期、拒绝、不可用和空表达不会被改写。表达使用本人逐字选择并确认的范例，仍需明确启用。

本轮 ECSConnectionTests 13 项及 SimpleFlowUITests 6 项通过。新增测试覆盖表达回退、只提交已存答案 ID 的锁定请求、简化路线上的反馈入口和比较后的人物审核入口。两项新界面测试使用隔离的 Debug 状态，不冒充真实模型或本人确认。截图检查、签名真机构建及 1.3.2 / 2026101305 覆盖安装完成；没有卸载或清空容器。手机锁屏阻止了自动启动。云端真实合成音频与实际模型的检查记在独立后端 worktree 的 docs/architecture/twin-fidelity-feedback.md；尚没有本人的相似度盲评结果。


### 孪生聊天入口（2026-10-13）

iOS 1.4.0 / 2026101306 将日常「对话」入口改为「孪生」。手机当前会话显示多条左右消息：本人问题在右、孪生回答在左，输入栏固定在聊天底部并随键盘抬起。「＋」集中语音提问、最新回答依据／本人纠正、比较结果、理解与表达审核。云端声音生成、图片上传和其他未接通能力不进入菜单。语音仍单独确认转写用途，识别只填入输入栏，由本人核对发送。

保留原话／推测／不知道的标识、原文与原音入口、表达改写前内容和模型来源详情；纠正仍先锁定已保存的答案再录本人回答。来源变化使旧聊天回答失效；更换账号／空间、撤销授权和人物审核变动会清理当前聊天。失败问题留有提示并可重新编辑，不丢掉已输入的下一条问题。

聊天历史只是当前客户端会话的显示记录，没有作为人物证据写回或自动确认画像。重新启动目前只恢复服务器中最新一条回答；后台 query 契约仍逐条处理当前问题，没有新增多轮上下文参数。本轮不修改共享 Backend Contract 或云端部署。

本轮 ECSConnectionTests 16 项、SimpleFlowUITests 7 项通过。新增检查覆盖消息次序与刷新去重、请求失败、来源过期、账号切换清除历史与草稿、左右气泡位置、键盘下输入栏／加号可达、菜单隐藏未接通能力。比较与审核入口继续通过。界面测试全部使用隔离 Debug 状态，不代表真实模型或本人评审；多轮气泡、键盘和加号截图已检查。

1.4.0 已通过签名真机构建，但无线设备通道 unavailable，覆盖安装未成功；本人随后明确暂缓安装，并要求继续完善。

### 孪生与录音流程完善（2026-10-13）

1.4.1 / 2026101307 在当前账号及本人空间中恢复最近 20 组聊天。本机受保护、排除备份的索引只存问题和答案编号；重新打开时先检查授权，再重新读取服务端答案。不会离线复用缓存回答、原文或表达推断。原话／推测／不知道仍明确标识。恢复中和失败状态可见，缺失答案可重新加载；重试同一个失败问题不会复制消息或覆盖下一条草稿。

每条有效回答都能查看对应依据、复制及发起本人纠正，较早消息也可以操作。纠正前重新检查所选答案，再提交该答案的保存编号用于锁定。「＋」新增开始新聊天，明确确认和取消；只清理手机聊天索引及草稿，录音、记忆和比较结果保留。已有草稿时重新编辑失败问题也允许保留当前文字。

比较页可直接继续核对已经提交的本人回答，只有当前空间里对应的录音可以打开。本机有原音时使用原音，没有本机档案时使用已授权的服务端原音。开始新的本人回答前先保留既有录音草稿；完成后返回回答比较。重试录音的旧逻辑曾只等 ready，而转写进入 reviewing 后需要本人确认；现改为当前录音进入待核对状态即结束等待，其他录音异步刷新。

ECSConnectionTests 23 项、LocalRecordingTests 13 项通过。10 项不同的 SimpleFlow 界面用例在修正复验后均通过（不是一次全绿运行）；修复了新聊天取消按钮及依据弹窗未绑定答案编号的问题。最后一轮依据／逐条操作截图已检查。签名真机构建通过，App 包核对为 1.4.1 / 2026101307；按本人要求暂未安装。没有替本人录音、确认转写、提交画像、触发真实模型生成或改变 Backend Contract。

当前聊天历史用于显示和恢复，服务端仍对每条完整问题独立检索记忆。连续追问中的省略指代和多轮上下文尚未新增；聊天记录不会自动训练人物理解或成为原始证据。

### 连续会话与本人文字记忆（2026-10-13）

1.5.0 / 2026101308 接入兼容的 v0.5 会话能力，替代上一节“服务端逐条独立处理”的限制。服务端依据当前账号／空间的 previous_answer_id 读取前文；手机不拼装或伪造 assistant 消息。恢复最近 20 组索引后继续承接最后的有效保存编号。新聊天不带 parent，开启新的会话。实际模型窗口保留最多 20 轮完整交换和 24000 字，溢出时界面提示；这不代表无限上下文。

没有录音也能在云端授权后普通交流。人物理解变化保留本人问题及会话链，旧回答失效并由服务端排除；切换账号／空间及撤销云端授权仍清理本机聊天。网络失败重试保留消息及幂等编号；依据变化导致的 409 重试更新请求编号，避免反复取回失效答案。

「＋」里的「从聊天留下记忆」让本人选择实际发出的消息；也可以长按本人消息选择「记住这句话」。确认真实描述后，保存为带来源的本人文字记忆，不生成虚构录音，不将孪生回复转成人物事实。新的文字可以参与 RAG，再排队整理待核对的人物候选；新的理解与表达范例仍需本人审核和启用。普通 CONVERSATION 回应不进入人格预测校准。

本轮原生验证、独立 CloudBase 发布和合成账号结果见 [连续会话验证记录](../../docs/verification/IOS_TWIN_CONVERSATION_2026_10_13.md)。没有替真实用户保存聊天、确认画像或开展相似度评审；按本人暂缓使用的要求不安装到 iPhone。

### 一键录音与自动转字（2026-10-13）

1.6.1 / 2026101310 的录音首页点击即开录，原有草稿保留并单独继续查看。结束后自动转字；云端用途只在首次或用途／授权变化时确认，绑定当前服务、账号和本人空间，撤销后不会自动重新创建采集授权。未连接时尝试设备本机识别；原音始终保留。识别后的文字仍需要本人核对，确认后才整理记忆。「我的」可关闭自动转写。

验证和安装记录见 [一键录音记录](../../docs/verification/IOS_ONE_TAP_RECORDING_2026_10_13.md)。没有代替本人录音或核对文字，没有修改共享接口或Voice授权。


### 旧聊天长期记忆（2026-10-13）

1.7.0 / 2026101313 接入旧聊天检索和来源查看。孪生加号菜单的“旧聊天与长期记忆”可查看原消息及摘要、搜索以前聊过的内容、关闭参考或清除聊天记忆。清除设置时间界限，旧消息不再重新索引；已经单独确认保存的本人文字记忆沿用记忆页删除。聊天摘要不自动确认成人物理解。

后端基于独立 codex/twin-chat-memory 工作区，包含当前实时 Voice 基线。迁移与发布、设备交付和实际验证见 docs/verification/IOS_CHAT_MEMORY_2026_10_13.md；构建成功不等于本人相似度提高。

### 勿忘我原生设计系统（2026-10-14）

`RememberMe/RememberMeDesignSystem` 统一管理颜色、字体、间距、组件和五瓣勿忘我矢量动效。首页、记忆库与详情、录音、孪生文字与通话页已接入；原有四个 Tab、授权、来源、纠正和音频状态逻辑保留。记忆原文与纠正收进独立详情入口，通话对话详情从顶部图标打开。

Debug 的「我的 → 组件预览」可查看组件与状态；Xcode 预览覆盖明暗、大字号和关闭动效。录音花朵接入真实音量，实时通话暂为状态动效，不伪造音量驱动。可选密码保护仍需独立安全实现，不以视觉锁冒充加密。

组件接入与维护见 [Design System 说明](RememberMe/RememberMeDesignSystem/README.md)，实际构建、119 项单元测试、两种尺寸 UI 检查及未验证项见 [验收记录](../../docs/verification/IOS_DESIGN_SYSTEM_2026_10_14.md)。本轮未安装到实体 iPhone。

## 后台录音与 Soundcore D3200

2026-10-16 源码增量（尚未部署）：按本人确认的[重点区间规则](../../docs/architecture/wearable-priority-capture-2026-10-16.md)，已在录音的设备连接后自动订阅实时音频，约每一分钟封存一段并交现有后台整理；完整文件同步按相同 OPUS 包与来源位置补齐，避免重复导入，删除后的未知子片重放须等完整源核对。设备标记按开启／关闭配对，跨分段仍保护；App 也提供「开始重点／结束重点」，缺失可靠标记时保守保护整段。普通完全相同条目可归并全部证据，独立重点保留完整原话，结构化理解不代替原话。

官方 SDK 返回的裸 OPUS 由系统解码器转换为可播放 WAV，原始包另行保存。解码器在已验证系统上固定裁去前 2.5 ms，保留原包时钟并明确记录此偏移，不按比例缩放、不填造音频。显式删除清理手机归档与传输副本，内容校验回执保留以防重新导入；不删硬件原文件。成功整理后清理重复机器稿，仍用于来源和声纹校验的内部 canonical 原文保留，状态为 `evidence_required`。

公开 SDK 没有佩戴检测、从 idle 开录或重映射实体按键的接口，本人也确认尚未实机核对；这些硬件能力仍未完成。App 只在真实录音状态／音频事件后显示接收，不用暂停恢复指令假装支持自动开录。最终验证与限制见[本轮记录](../../docs/verification/WEARABLE_PRIORITY_CAPTURE_2026_10_16.md)。

2026-10-16 入口调整：「录音」首页的「我的录音」「蓝牙连接」并排显示。「蓝牙连接」查看 Anker soundcore 录音豆、黑色耳机图示和实际连接／音频路线；顶部统一白色背景，两张设备图直接展示，不单独加框。新耳机在系统蓝牙设置配对，已配对耳机可由页面的系统音频选择器切换。设备图片不代表已有连接。

「我的录音」包含往期录音、另行保存的原话和主用户的文字／语音 TwinAgent 问答，支持左滑露出删除按钮并确认。问答按时间分页读取，不随关闭旧聊天检索而消失；失败保留重试，声音清理待完成时仅显示无原文的重试行。独立保存的录音和问答分别管理。游客问答及提问音频只在当前会话内存处理，不进入历史、录音或学习资料。接口与授权见[本轮说明](../../docs/architecture/recording-device-and-owner-history-2026-10-16.md)。

本切片由 2026-10-15 产品负责人直接批准，见 [授权与边界](../../docs/architecture/background-wearable-capture-2026-10-15.md)。手机前台开始后允许切到后台；实时活动显示录制、暂停或状态过期，并可返回录音页。系统强制结束进程后不能承诺继续录音，重新打开时恢复尚未归档的有效音频。

官方 SDK 属于用户提供的工具包，不在 Git 分发。准备硬件版：

```sh
./apps/ios/scripts/prepare-soundcore.sh '/path/to/iosFrameworkExport-v1.3.01'
```

此脚本只复制两个 xcframework 到 ignored `apps/ios/Vendor/Soundcore/` 并生成 `project.hardware.yml`。普通 `project.yml` 保留无 SDK 的可用手机录音回退。不要在 App 中加入厂商 app_key；后端以 `REMEMBER_SOUNDCORE_APP_ID` / `REMEMBER_SOUNDCORE_APP_KEY` 换取 Owner 作用域临时 token / 签名 license，固定官方 CI 环境，与 SDK `.development` 对应。

SDK 支持扫描、用户选择连接、实体确认绑定、状态、暂停／继续、文件读取；开始／停止仍使用录音豆实体按键。文件按账号空间去重并拆成不超过 5 分钟／12 MB 的 WAV 段，保留设备来源和时间范围。未知或其他人的声音不能自动更新本人人物模型。文件传输、持续佩戴与锁屏录制仍须用实际设备验证，不以模拟器测试替代。

[设备图示及完整生成提示](../../docs/verification/DEVICE_ASSETS_2026_10_15.md)。

## 火山国内模块化实时语音（2026-10-16）

Android 队友复用现有后端时，直接使用[跨端接入与交接说明](../../docs/api/ANDROID_VOLCENGINE_HANDOFF.md)：包含后端地址、账号条件、通话时序、共享契约及 Android SDK 官方入口。iOS SDK 由准备脚本下载，厂商长期密钥保留在后端。

1.15.0 / 2026101605 已覆盖安装，CloudBase050／`ios-volcengine-parity-178c912` 已上线。客户端以 `features=2` 连接火山 RTC，实时 ASR 与默认 TTS 使用火山；本人音色复用原 CosyVoice profile，经本后端提供当前核验答案 PCM，由 SDK 本地播放器播放。声纹姓名、本人原话记忆、自然取样和复刻入口已恢复，独立许可与删除语义保留。保活与答案轮询分开，短暂故障有限重试，过期及撤权不可续租。

「孪生 → 电话图标」查看音色与声纹状态；已有音色可直接试听并选择“本人音色”，无需删除重录。未设置时可展开“声音复刻 · 录制本人声音”，也可在授权后正常聊天累积清晰本人样本。声纹尚未登记时用本人声音介绍姓名一次，之后以独立声学匹配显示姓名。

构建先执行 `scripts/prepare-volcengine.sh` 安装固定官方 SDK，再按需要以 `project.yml` 或含硬件 SDK 的 `project.hardware.yml` 生成工程。所有长期厂商密钥只在后端。线上隔离合成验证、长保活、原生定向测试与真人设备尚待确认项见 [完整记录](../../docs/verification/VOLCENGINE_FEATURE_PARITY_2026_10_16.md)；开通说明见 [步骤](../../docs/verification/VOLCENGINE_VOICE_SETUP_2026_10_16.md)。

## 主用户与本机亲友模式（2026-10-16）

本人可在「记忆花园 → 亲友开放范围」或「我的 → 访问模式」选择已核对的完整录音来源，预览整段原音、全文与连带记忆后保存。新来源不自动开放；本人音色需单独选择且原声音许可有效。进入亲友模式前先结束录音、通话和资料处理。

亲友模式只提供「记忆花园」「TwinAgent」，通过独立短期游客凭据浏览和连续文字／语音问答，不持有 AppModel 的本人连接，不写入本人的资料或训练。原账号恢复凭据与本机入口分别存 Keychain；重启仍为亲友模式，聊天与临时录音不恢复。返回主用户须重新验证原账号密码，原登录到期时可展开重新登录原账号，仍须匹配同一账号与本人空间。结束访问清理当前会话与临时声音；每两秒及播放前核验开放范围，撤权或无法核验时隐藏旧内容并停止播放。

定向验证与尚未执行的真机项目统一记录在 `docs/verification/IOS_GUEST_MODES_2026_10_16.md`。隔离 UI 样例仅在 Debug 的 `--uitest-offline --uitest-guest` 下启用，不包含真实账号或网络能力。
# 2026-10-16 采集与 Android 花园对齐

本地源码 **1.17.0 / 2026101614**：持久自动转写队列、可编辑草稿／补充、一次保存后的累计人物分析、原稿与自动校对对照；花园以原生 SwiftUI 重构花田／列表／时间线、五片花瓣阅读器、六景、八侧面和四个人物视图。沿用现有后台录音、重点区间、实时活动及游客权限。新共享服务代码尚未发布，未覆盖安装实体 iPhone。见[验证与预览](../../docs/verification/IOS_ANDROID_CAPTURE_GARDEN_2026_10_16.md)。

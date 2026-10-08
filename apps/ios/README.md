> **2026-10-08 Android 原型复刻：** 五个入口改为 Portrait / Graphs / Memories / Agents / Me，复用队友 #81 的画像卡片与关系图布局。已有 iOS 录音、证据问答、五维校准和独立声音授权保留；可先保存本地录音，再连接服务。范围与本地验证见 [复刻记录](../../docs/verification/IOS_ANDROID_PARITY_2026_10_08.md)。

# iOS 本机语音 → Person Model

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

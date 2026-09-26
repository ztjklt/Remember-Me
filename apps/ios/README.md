# iOS 本机语音 → Person Model

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

只需完整跑一次：自由录一段中文并提交；核对和修改转写文字，确认后看到 Episode 到 `ready`、记忆原文证据和七领域模型；回答 App 给出的一条追问并再次确认转写，再检查模型版本和领域内容更新；纠正或删除一条错误记忆，确认 trait 与下一条追问重算。断网时同一段录音仍在 App 内，重新提交会用相同幂等键；模型超时到达失败状态后可从同一个 Episode 重试处理。把设备型号、iOS 版本、两段 Episode ID、STT/AI 模型版本和观察到的结果写进 PR 的 “How it was tested” 即可。

实测的合成音频联调可以证明服务链和数据流，不应写成本人真机录音。真机录音必须由使用者在设备上亲自完成。

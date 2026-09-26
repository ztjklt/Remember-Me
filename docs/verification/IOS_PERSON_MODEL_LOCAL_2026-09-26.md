# iOS 语音到 Person Model：本机验证记录（2026-09-26）

本记录区分自动检查、Mac 合成语音联调和本人 iPhone 真机录音。合成样例由 macOS 中文系统语音生成，不代表真人录音。2026-09-27 起，AI Core 切换为 DeepSeek V4 Flash；转写文本会发送到 DeepSeek，原音与数据库仍保存在 Mac 本机。

## 已运行

| 检查 | 结果 |
| --- | --- |
| `packages/contracts`: `npm test` | v0.1 与 v0.2 共 10 项通过；`IOS_MIC`、七领域快照、问题及类型化证据通过 JSON Schema 校验 |
| `services/backend`: `uv run pytest -q` | 全部通过；覆盖迁移、Subject 隔离、一次性 HTTPS 配对、IOS_MIC 上传幂等、失败 Episode 原音保留与重试、矛盾并存、纠错/删除重算、录音文件权限 |
| `services/ai-core`: `uv run pytest -q` | 128 项通过；覆盖中文原话定位、无法定位时丢弃、Ollama 实际模型 digest、DeepSeek JSON 输出及禁用思考、返回模型版本、密钥目标限制 |
| iOS 模拟器与 `generic/platform=iOS` 无签名构建 | 通过；配对页已在模拟器启动并截图检查 |
| iPhone 15 Pro Max 签名构建 | 2026-09-27 通过；Apple Accounts 连接恢复后，真机签名构建成功。 |

## Mac 本机真实模型联调

在单独的合成样例数据库中，HTTPS Backend、Loopback STT、Loopback AI Core 与 Ollama Qwen 同时运行。FFmpeg 将 `.m4a` 转成 16 kHz 单声道 WAV；多语言 Whisper `ggml-base.bin` 用 `-l zh` 转写。使用的 STT 模型版本为 `whisper-ggml-base-60ed5bc3dd14`，Qwen 模型 digest 为 `6488c96fa5fa`。模型版本随后改为每次从 Ollama `/api/tags` 自动读取，已另用真实服务调用确认 `qwen3.5:latest-6488c96fa5fa`。

1. 第一段合成中文音频上传为 `ep_6d6abb214bb8478a`，状态 `ready`，转写为「我喜歡周末去公園散步,因為那時候很安靜。」。AI Core 抽出 1 条偏好 Memory，证据是这段原始转写的 `0–20` 位置。Person Model v1 的 `PREFERENCES` 域有 1 条 trait，生成 `IDENTITY` 追问。
2. 第二段合成中文音频携带该追问 ID 上传为 `ep_0189fe07c5904918`，状态 `ready`。原问题被标记 `answered`，Person Model 到 v2，`IDENTITY` 域新增 1 条 trait，下一条问题指向缺失的 `EPISODIC_MEMORY` 域。两段原音、转写和证据均保存在同一 Subject 下。
3. 将第二段中错误的人名 Memory 手动纠正后，v3 的对应 trait 使用 `CALIBRATION` 来源与审计证据；删除该 Memory 后，v4 不再包含该身份 trait，下一条追问重新指向身份域。原始 Episode 和音频仍保留。

以上样例已归档到本机 `~/.cache/remember-me/live/synthetic-probe.db` 和 `synthetic-probe-audio/`，临时配对凭证已删除。设备准备使用的 `remember.db` 是新建的干净数据库：1 个 Subject、0 个 Episode；数据库权限为 `0600`，音频目录为 `0700`。

## 2026-09-27 真机安装与配对

新 bundle ID 的安装被免费 Personal Team 的每台设备 3 个 App 名额限制拒绝。经用户选择，将同一新版构建签为现有 `me.remember.ios.qa`，作为 QA App 更新安装；正式版 `me.remember.ios` 和其他 App 未改动。更新前将 QA 数据容器备份到 Mac 私有目录；旧 QA 的 Documents 目录没有录音文件。更新包的签名和 embedded profile 的 App ID 均已核对，安装与启动成功。

Mac 切换到新局域网地址后，重新签发本机 TLS 证书，启动 loopback STT、AI Core、HTTPS Backend 和 worker。iPhone 上的一次性 HTTPS 配对成功，服务端已建立设备凭证。配对时数据库为 0 Episode，后续本人真机录音结果见下节。

## 2026-09-27 本人真机录音进展

1. iPhone 15 Pro Max 自由录音上传为 `ep_185a8be998e24832`，时长 16.6 秒，保留原始音频，由 `whisper-ggml-base-60ed5bc3dd14` 转写为中文。最初本机 Qwen 提取为 0 Memory；切换 DeepSeek 后，先备份数据库，再仅对这条尚无 Memory、证据或纠错审计的 Episode 重新排队执行提取和建模。原始 Episode ID、音频和转写未变。最终状态 `ready`，`deepseek-flash` 提取出 3 条 Memory、3 条逐字可定位的证据，Person Model 新增 3 条 `IDENTITY` trait。
2. 第二段真机录音上传为 `ep_76d717f59e0b4058`，时长 9.4 秒，状态 `ready`，同一 Whisper 与 DeepSeek 模型。新增 1 条带证据的 Memory 和 1 条 `EPISODIC_MEMORY` trait，Person Model 到 v3。该 Episode 的元数据未含追问 ID，因此暂记为第二段自由录音；尚不能记为“回答 App 追问”。当前生成了下一条 `RELATIONSHIPS` 追问。

密钥只从 Mac 本机私有环境文件加载，未写入仓库、App 或本记录。DeepSeek 返回模型标识为 `deepseek-flash`。真机资料不复制到仓库。

## 2026-09-27 转写核对更新

用户指出真机 Whisper base 转写有多处错字，选择保留现有 STT 模型，改为“转写后先显示、可编辑，再生成记忆”。新增 Backend 迁移 `0005_transcript_review`，新 iOS Episode 的 worker 在 STT 后等待录音 Actor 确认；这之前不调用 AI。数据库分别保存机器原文、确认版文字、确认 Actor 与时间。Android 自动处理不变。Mac 真实数据库迁移前已备份，迁移后完整性检查为 `ok`，原有两条 Episode 仍为 `ready`。

Backend 全量 `uv run pytest -q`、AI Core 128 项测试及 wheel 冒烟检查通过；GitHub PR #76 的 ai-core 3.12/3.13、backend、contract、endpoint、Android test 均通过。iOS 无签名构建和针对 iPhone 15 Pro Max 的签名构建通过；新版已作为现有 QA App 的更新安装并启动。此时新核对步骤**尚未得到本人真机操作结果**，不能把自动测试写成真机通过。

## 尚需完成的真机步骤

在新版 App 中点生成追问的“录下回答”，保存后核对并修改转写文字再确认，确认上传元数据含对应问题 ID、问题状态变为 `answered` 且模型更新。然后在 iOS 上纠正或删除一条 Memory，确认 trait 与问题重算。另检查拒绝麦克风、断网与模型超时的可恢复界面，并记录设备 iOS 版本及观察结果。不设重复交叉验收清单。

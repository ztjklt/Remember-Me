# iOS 语音到 Person Model：本机验证记录（2026-09-26）

本记录区分自动检查、Mac 本机真实模型联调、iOS 构建，以及尚未完成的本人真机录音。联调音频由 macOS 中文系统语音生成，不代表真人在 iPhone 上录音。

## 已运行

| 检查 | 结果 |
| --- | --- |
| `packages/contracts`: `npm test` | v0.1 与 v0.2 共 10 项通过；`IOS_MIC`、七领域快照、问题及类型化证据通过 JSON Schema 校验 |
| `services/backend`: `uv run pytest -q` | 全部通过；覆盖迁移、Subject 隔离、一次性 HTTPS 配对、IOS_MIC 上传幂等、失败 Episode 原音保留与重试、矛盾并存、纠错/删除重算、录音文件权限 |
| `services/ai-core`: `uv run pytest -q` | 全部通过；覆盖中文原话定位、无法定位时丢弃、Ollama 实际模型 digest、旧版提取边界 |
| iOS 模拟器与 `generic/platform=iOS` 无签名构建 | 通过；配对页已在模拟器启动并截图检查 |
| iPhone 15 Pro Max 签名构建 | 未完成；Xcode Apple Accounts 无法读取开发团队（登录错误 -1200），新 bundle ID 无配置文件。设备上已有两个旧版 App，未覆盖。 |

## Mac 本机真实模型联调

在单独的合成样例数据库中，HTTPS Backend、Loopback STT、Loopback AI Core 与 Ollama Qwen 同时运行。FFmpeg 将 `.m4a` 转成 16 kHz 单声道 WAV；多语言 Whisper `ggml-base.bin` 用 `-l zh` 转写。使用的 STT 模型版本为 `whisper-ggml-base-60ed5bc3dd14`，Qwen 模型 digest 为 `6488c96fa5fa`。模型版本随后改为每次从 Ollama `/api/tags` 自动读取，已另用真实服务调用确认 `qwen3.5:latest-6488c96fa5fa`。

1. 第一段合成中文音频上传为 `ep_6d6abb214bb8478a`，状态 `ready`，转写为「我喜歡周末去公園散步,因為那時候很安靜。」。AI Core 抽出 1 条偏好 Memory，证据是这段原始转写的 `0–20` 位置。Person Model v1 的 `PREFERENCES` 域有 1 条 trait，生成 `IDENTITY` 追问。
2. 第二段合成中文音频携带该追问 ID 上传为 `ep_0189fe07c5904918`，状态 `ready`。原问题被标记 `answered`，Person Model 到 v2，`IDENTITY` 域新增 1 条 trait，下一条问题指向缺失的 `EPISODIC_MEMORY` 域。两段原音、转写和证据均保存在同一 Subject 下。
3. 将第二段中错误的人名 Memory 手动纠正后，v3 的对应 trait 使用 `CALIBRATION` 来源与审计证据；删除该 Memory 后，v4 不再包含该身份 trait，下一条追问重新指向身份域。原始 Episode 和音频仍保留。

以上样例已归档到本机 `~/.cache/remember-me/live/synthetic-probe.db` 和 `synthetic-probe-audio/`，临时配对凭证已删除。设备准备使用的 `remember.db` 是新建的干净数据库：1 个 Subject、0 个 Episode；数据库权限为 `0600`，音频目录为 `0700`。

## 尚需一次本人真机记录

在新 bundle ID 签名配置可用后，将 App 安装到已配对的 iPhone 15 Pro Max。本人在设备上录一段中文自由叙述，再回答 App 生成的一条问题，核对两段原音/转写、真实 Memory、七领域模型更新；然后在 iOS 上纠正或删除一条 Memory，并看 trait 与问题重算。另检查拒绝麦克风、断网与模型超时的可恢复界面。记录设备 iOS 版本、两个 Episode ID 和实测结果即可，不设重复交叉验收清单。

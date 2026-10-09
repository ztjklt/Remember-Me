# Android 客户端转写接力与 ECS：实现和验收

2026-10-09，北京时间。基线 `71fe55e`，分支 `codex/agent-integration`。ECS 业务版本仍为 `b2f827b`。不改饮食项目，不 push/merge，不新建云资源。

## 本批结论

**一段有效 Android 原生录音已完成：保存/播放 → 电脑实际 Groq 转写 → App 取回机器稿 → ECS 等待核对 → App 确认 → 微信提取 → 保存记忆 → App 来源问答和原音播放。**

这是分阶段恢复完成的真实流程，不是每次模拟器收音都稳定通过。音源是已有小米虚构 TTS，经虚拟麦克风进入 MediaRecorder；不是实体手机或真人测试。有效原音与已有真实 ASR 检查点通过 SHA256 复用，没有用创作文本替换 ASR，也没有伪称人工听读通过。

本批没有重新跑 30 段/60 问、双角色全循环或校准。已有四视角页面可读；没有把单条新观察确认为稳定人格。

## 无域名的连接方案

APP 可以通过 IP 和端口访问服务器，域名不是自用 Demo 的前提。目前实测路线：

```text
Android https://localhost:18843
  → USB/ADB reverse → 本机 SSH 隧道 remember-me-ecs
  → ECS 内部 HTTPS :18443 → API / AI / PostgreSQL / 原音存储
```

这仍需要电脑保持连接，不能写成手机已经脱离电脑直连公网。

另已准备 `https://39.108.183.47:8443`：服务器内部携带对应证书访问 `/ready` 返回 200，但本机外部直连超时。Nginx 与主机防火墙仅允许当前测试出口 `183.6.9.111`；原有博客 80/443、SSH 未改动。

下一步核查云安全组/网络路径，允许实际演示网络出口访问 TCP 8443。换 Wi-Fi/蜂窝网络后来源地址可能变化。尚无云安全组实读证据，因此不能断言超时一定由某条安全组规则造成，也没有开放所有来源。

仅 debug APK 对指定 IP 和 localhost 信任专用公开证书；仍验证证书与主机名，没有 trust-all，release 不包含 debug 信任配置。IP 证书为生成起 90 天，到期/换证需更新测试 APK。依据：[Android 官方网络安全配置](https://developer.android.com/privacy-and-security/security-config)。

## 运行方式

APK：`apps/android/app/build/outputs/apk/debug/app-debug.apk`，约 148 MiB；仍含旧原型资源，本批没有拆除旧功能来减包。

固定交付副本：`output/remember-me-android-ecs-demo-20261009.apk`；SHA256 `e16af1e666f0f9dc16b52ec9727330f6630f6d85b27e12920bd1b7db31832a43`。已扫描本次文件及 APK，未发现现有模型密钥、测试密码或身份令牌的明文匹配；这不是完整安全审计。

在仓库根目录，只连接一个模拟器或 USB Android：

```powershell
./tools/start_android_ecs_demo.ps1 -Install
```

脚本复用已配置的 SSH 密钥，建立仅本机监听的转发、设置 ADB reverse 并安装 APK。应用本次默认地址为 `https://localhost:18843`，连接设置可修改。模型密钥不会写进 APK。

使用既有测试账号登录。本机受限配置位于 `services/backend/var/android-client-relay-resume2/config.json`，不得随 APK 分发。自用演示无需公众注册，但仍保留所有者/读者权限。

1. 在“今天”录音、保存、播放，然后“导出这段原音”。
2. 在已有 backend Python 环境运行：`python tools/client_asr_capture.py transcribe --audio <原始M4A> --out <机器稿JSON> --confirm-audio-export`。不要改变用于匹配的原始 M4A。
3. 将 JSON 传回手机，选择“取回机器转写”，App 校验音频哈希。
4. 同意上传原音和机器稿，在“档案”核对文字。可改字、另加书面说明，再明确确认云端整理。
5. 查看记忆、问答与来源原音。

**电脑转写接力仍需人工搬文件，不是一键手机 ASR。** 比赛方服务接入后替换这一环节，不能让普通用户长期操作 JSON。

## 接口与恢复约束

- 沿用 `/api/v1/episodes/client-transcribed`，原生录音保留 `ANDROID_MIC`；不伪装文件导入来源。
- JSON 包含 text、audio_sha256、provider、model、audio_export_confirmed；限制大小、严格校验类型和原始文件 SHA256。哈希匹配不证明转写准确。
- 当前接受 Groq / whisper-large-v3，服务端记录 `client-reported`。手机不持有 Groq、微信或小米共享密钥。
- 首次上传前保存机器稿、幂等键和上传方式；开始上传后不能换稿。配置变化后重试仍使用原方式，不悄悄丢掉机器稿。
- 原始机器稿、简体核对稿、书面补充分开。导入不等于确认，确认前不提取记忆。
- 文件选择回调绑定身份与空间，退出或换空间后旧回调无效；取消保留原音，Activity 重建保留稿件。
- 保留失败和来源校验，不以 HTTP 200 或界面流程完成代替语义验收。

## 换比赛方 API 的边界

| 新服务情况 | 实施工作 |
|---|---|
| 与已实现适配器的请求、音频和返回格式一致 | 修改 endpoint、模型、鉴权配置，再实测 |
| 异步任务或不同 multipart/base64/返回格式 | 新增适配器，归一化文字、真实模型信息、哈希和处理记录 |
| 替换当前客户端 Groq 路线 | 同步扩展后端和 Android 当前白名单，更新外发说明；不得谎报成 Groq |
| 手机直接访问模型 | 使用比赛方允许的客户端认证或受控网关，不能内置共享长期密钥 |

录音、核对、记忆、授权、修订、问答无需因此重写；**并非任何接口都只换 key 就能用**。TTS 当前用于虚构测试素材，不等于产品已经具有真人声音克隆。

## 验收与失败记录

| 检查 | 本批实测结果 |
|---|---|
| 单元测试 | 39 项通过，0 failed/error/skipped；含哈希、边界、幂等和模式切换恢复 |
| 构建及 lint | APK/测试 APK 通过；lint 0 errors、34 warnings |
| 有效原生音频的 ECS 链路 | 恢复后真实 UI/网络测试 1 项通过；ASR 与微信均真实调用 |
| 暂停/继续 | 按钮执行过，但相应虚拟收音不稳定；不能据此验收音频质量 |
| 持久化 | Activity 重建后机器稿保留；加密登录恢复；退出清空资料与会话 |
| 文件选择器 | 打开/取消实测 1 项通过，原音保留；选中文件的系统回调尚未单独自动验收，实际读写方法在核心实跑中验证 |
| 原音 | 有效故事完整原音播放、暂停和定位通过，无伪造片段时间 |
| 设备 | 仅模拟器，实体 Android 和 iOS 未在本批验收 |

有效 Episode：`ep_56e310d155244fed`。原生 M4A SHA256：`a3589f8b3ce69eb2dc95545d5d4b668c3b457da8200314ae27695e2742edf3a3`，本机记录 19.622 秒。

讲述内容是“工作收入与家人安全冲突时优先安全，但不代表所有情况下都不挣钱”。微信提取 1 条 VALUE，保留情境和否定限定。问答为 ORIGINAL，逐字引用同一来源。本例没有用书面补充代替音频完成记忆。

被忽略的原始证据目录：

- `services/backend/var/android-client-relay-probe/`：有效原生采集、实际 Groq `machine-check.json` 和调用记录。
- `services/backend/var/android-client-relay-resume2/`：匹配的原音/稿件、ECS 记忆/回答、截图、通过日志、选择器日志。
- `services/backend/var/android-client-relay-20261009/`：首轮近静音、ASR 无关文字及 Twin 来源类型校验失败。测试产生的当前记忆已通过 Owner API 撤回，失败原件保留。
- `android-client-relay-attempt3/`：UI 机械流程曾通过，但 ASR 仍为无关文字；质量失败，不计完整验收。产生的记忆同样撤回。
- `android-client-relay-attempt4/`：近静音被检查拦截，未调用 ASR 或整理；明确停止了等待中的测试。
- 另保留测试脚本选择禁用按钮、登录等待不当的失败日志；修复后通过。

能量阈值和虚构故事关键词只用于防止测试误报，不是通用语音质量模型。没有伪称已人工听读。

## 复核与剩余工作

独立复核发现并修正：公开证书被忽略规则排除、配置变化破坏旧请求重试、测试错误要求核对稿等于原机器稿。保留失败到通过的证据。

优先剩余事项：替换人工 ASR 文件接力；确认 IP 对手机网络可达；真机录音及模拟器注入稳定性。无需先购买域名、建设公众注册或增加 Agent 数量。

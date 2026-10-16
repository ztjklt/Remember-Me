# 自动转写、一次保存与累计分析验收 · 0.16.0

## 已验证的行为

新音频接收后自动加入持久队列；上传沿用稳定幂等键。机器文字由服务器保存，并在 App 中形成可编辑、本机保存的草稿。用户保存文字/补充后，原子确认转写并恢复 EXTRACT/MODEL 作业。MODEL 成功提交时，同一数据库事务排队累计人物分析；已有 queued 任务合并材料，running 任务有后继作业。累计分析继续校验授权、来源版本和引用，保持 AI 候选属性。

界面隐藏设备技术参数、下载副本列表及调试解释，保留设备入口；草稿出现时压缩录音卡片。试听可选。一次保存后展示刚保存的录音，避免较早录制、较晚导入的录音被其他日期较新的记录挤掉。

## 验证记录

- Android JVM：140 项，0 failure / 0 error。
- Android Debug 构建、测试 APK 构建及 lint 通过；lint 0 error / 21 既有 warning。
- 服务器候选版本在独立测试数据库执行 115 项回归，0 failure / 0 error。覆盖原音导入、转写确认、记忆 worker、重点、自动累计任务、材料变化、授权失效和人物引用。
- 模拟器 Debug：自动上传响应丢失后重试、身份/空间隔离、草稿恢复、一次保存；另含真实 SDK 文件路径/写入/解码、控制器事件及前台服务。6 项通过。首次运行有 1 项旧 UI 文案断言失败，更新为新首页标题后通过。
- 真实云端 Debug：虚构 E01 合成语音经 Android MediaCodec 解码，自动上传、实际 ASR/纠错、首页草稿、一次 UI 保存、10 条记忆、累计分析 complete。整个测试 96.353 秒（包含登录/准备/上传/模型等待，不是纯转写耗时）。测试 Episode `ep_2222c560bbcc443f`；此轮没有实物录音豆连接证据。
- 最终签名 APK 真实云端：同一虚构语音素材在签名版本中完成一轮新的自动上传、ASR、草稿与一次 UI 保存，生成 11 条记忆，累计分析 complete。Episode `ep_bc7e5f7cccb4471a`；完整测试 64.434 秒，`signed-cloud-proof/result.json` 记录 `saved_once_from_ui=true`。这不是硬件连接测试，也不是转写速度基准。
- 最终签名 APK：控制器事件 3 项、前台服务 1 项、真实 SDK 文件路径/写入/解码 1 项通过；视觉脚本 1 项通过，检查录音状态、同步进度及切页保持会话。SDK 事件由测试模拟；截图已人工检查。组合回归中的另 1 项 HTTP 假后端测试失败原因见下，不能称为整组通过。
- 服务部署：`/opt/remember-me/releases/paired-auto-capture-20261016`，源提交 `bcc2758995e96b4584213f9e3f9d63fede6fb5c2`。逐文件基线 hash 匹配后复制新 release，隔离测试后切换；api、worker、profile readiness 通过。没有修改运行凭据或迁移生产数据库。

## 包与证据位置

最终签名候选：`D:/JOB/hack/delivery/automatic-capture-0.16.0/remember-me-0.16.0-device-internal.apk`。

- source commit：`08c39294dde6e13086bbdb715929f228c590a20c`
- versionCode：`20261030`；保留 `me.remember.app.internal` 与原签名。
- SHA256：`018996221f9cac13e66bd8d843816fc94c316720cf33764df2357789a42f38c3`
- non-debuggable；包含私有 Soundcore 1.3.02。
- 该包最终模拟器/云端结果以同目录 `signed-*-tests.log` 及 `acceptance.json` 为准。

最终包测试过程保留失败记录：第一次组合回归被后续测试启动强制结束，系统 exit-info/logcat 的原因是 `start instr`，没有 AndroidRuntime 崩溃记录。重跑时，AutomaticCaptureFlowTest 使用的本地 HTTP 假后端被签名版本的明文禁用策略拒绝，登录断言超时；该测试的通过范围是 Debug，不应记为签名包通过。签名包实际云端走 HTTPS，已完成上述完整验证。其余控制器/解码/前台服务和视觉验收分别记录。

截图标注模拟设备事件、模拟后端或真实云端的虚构音频，不能扩大为 vivo 真机验收。实物录音/下载已由用户在 0.15.2 反馈确认；0.16.0 的自动后半段仍需在该手机上进行一次录音 → 自动文字 → 保存 → 记忆的实测。

进程被完全结束时，本机未上传任务下次打开继续；已交给服务器的任务独立继续。累计观察保持候选状态，不自动声称本人确认。旧版若干选择性云端演示脚本仍描述手动上传/确认的历史界面；本版流程以 AutomaticCaptureFlowTest、AutomaticCaptureCloudTest 和 RecorderHomeVisualTest 验收。

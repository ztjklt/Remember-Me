# 实时 Twin 超时诊断 — 2026-10-13

## 当前结论

四次启动失败已定位到 **LiveKit Cloud Mumbai Agent 建立上海 CloudBase 后端连接** 的阶段。两次独立空房间诊断、共四次连接尝试，均在DNS预查询成功后出现HTTPX `connect_tcp` 约八秒超时；没有进入 TLS 或发送 HTTP 请求。HTTPX内部还会解析域名，因此预查询不能证明每次实际连接的目标IP，也不能单独排除客户端内部DNS等待。对这些样本，声音复刻、ASR、模型计算和业务授权都尚未开始。

后续同一地区、同一 Agent 的新部署实例能够直连四个入口，并通过正常 HTTPX 域名请求。因此这是已观测到的间歇性连接故障，不能称为“国内后端一直不可用”“DNS 错误”“HTTPX 固定故障”或“LiveKit RTC 不支持”。实例在排查中发生过滚动更新；不能从恢复结果独断具体路由、源地址、防火墙或哪一云平台负责。要证明具体网络设备的细因，需要平台侧出口/入口或丢包取证。

另确认了初始监听状态早于Backend ASR真正就绪的代码问题，已修正并部署到原Agent。修正后的Cloud复测完成前两轮识别、回答及自动/手动打断；65秒静默后的第三轮仍未返回识别结果，因此完整Cloud验收仍失败。全程数字证明本轮收到和发送过语音，但不具备第三句分阶段计数，不能宣称该句已到达供应商或已经定位其丢失层级。没有为了诊断删除Agent或切换服务。

## 对照证据

时间均为 Asia/Singapore（UTC+8）。安全结构化材料保存在该后端工作树的 ignored `build/`，原始日志与凭据位于 0700/0600 私密目录。

| 对照 | 实际结果 | 意义 |
| --- | --- | --- |
| 本机新建连接的 `/health`、`/ready`、`/api/v1/service-info`，各三次 | 9/9 HTTP 200；health 0.14–0.315 秒，ready 0.878–1.127 秒 | 当时后端与就绪检查可响应 |
| 本机对两组共四个公网入口，保持原 Host/SNI 和证书校验 | 全部 health 200 | 未证明 DNS 地址本身错误或节点永久失效 |
| 18:26 云端标准 HTTPX 请求，两空房间四次尝试 | DNS 预查询成功；connect_tcp 约 8 秒失败；无 TLS/HTTP 阶段 | 这四次启动失败发生在业务处理前的连接阶段 |
| 18:36 云端逐地址探测 | 四入口全部 TCP/TLS/health 200；TCP 374–473 毫秒，完整响应 1.54–3.66 秒 | 云端路径也能恢复；固定地址只用于无凭据诊断 |
| 18:53 与 19:01 同一后续部署的标准 HTTPX 请求 | 三个任务 TCP/TLS/HTTP 完成，1.48–1.88 秒；返回不存在诊断 call 的预期404 | 常规客户端能够恢复，不能将固定IP作为永久修复 |
| 同一业务代码、本机 Worker、独立 dispatch | 三轮真实RTC非零音频、自动和手动打断、65秒静默后恢复均通过 | LiveKit媒体及现有Twin/CosyVoice业务链路具备工作能力 |

本机 Worker 对照使用虚构 QA 账号和系统预置音色 `longxiaochun_v3`，并非本人声纹。所有397帧测试输入都发出，旧轮无重启，自动打断间隙和手动打断后静默期的非零音频均为0帧，结束HTTP200。本机 Worker 已停止，QA预置音色引用先清空后撤销VOICE授权，样本profile为missing；没有删除系统预置音色、上传真人录音或生成真人克隆。

## 服务端、数据库与实现核对

取证时当前 CloudBase 版本016、100%流量、一个Running实例。规格1 CPU/2 GiB，MinNum=0/MaxNum=1。README的“网关并发1”有另一处明确注明尚未验证，不能将文档意图当平台实值。

PostgreSQL快照5连接、0阻塞、0空闲事务；这排除取证当刻的耗尽，不能排除历史瞬时负载。服务器授权样本85条（80成功、5不存在），平均23.27毫秒、最大34.7毫秒；三次答案请求约2秒。应用没有全局HTTP锁；ASR WebSocket与REST在本机完整对照中并行工作。AI单槽仅约束模型，不能解释尚未建立TCP的四次启动故障。async路由中的同步SQL仍是后续实现风险，未被证明为本次根因。

另发现结束通话请求曾在服务器耗时34.13秒和75.74秒。部署代码先提交持久化结束，再等待LiveKit远端删房；多次SDK请求/failover等待可能让测试的清理DELETE再次超时并掩盖主错误。QA报告已修正为保存主错误、分阶段结果与独立有界清理。分支已添加整个远端删房操作3秒上限，保持先结束落库、worker立即拒绝的语义；真实ASGI并行测试验证清理挂起期间授权已404，超时会取消远端协程并返回ended。该Backend小修正尚未部署，不能将源代码测试视为线上已修复。

17:08:43服务端栈是peer断开后关闭WebSocket的`WebSocketDisconnect(1006)`清理异常，不是模型或数据库超时证据。分支清理路径已兼容已断开1006，Backend定向suite共25项通过、2个上游弃用警告；这项同样尚未部署。

## 国内备用路线

优先保留已经完成的iOS LiveKit媒体接入，将同一Worker部署到与Backend网络实测通过的位置。LiveKit官方支持Cloud媒体与自托管Worker分开；无需为了这条路线删除现有云Agent或更换整个RTC客户端。[官方自托管说明](https://docs.livekit.io/deploy/custom/deployments/)

若后续国内设备的媒体连接也持续失败，完整国内RTC替换可比较阿里IMS/ARTC、腾讯TRTC及火山RTC。当前百炼`cosyvoice-v3-flash`与阿里IMS的官方声音复刻接入最直接；仍需iOS SDK与现有证据Twin/授权/UNKNOWN静音策略的协议适配。[阿里CosyVoice v3复刻](https://help.aliyun.com/zh/ims/user-guide/create-custom-timbre-based-on-the-refined-cosyvoice)、[iOS自动与手动打断](https://help.aliyun.com/zh/ims/user-guide/ios-usage-guide-1)、[自有LLM与地域](https://help.aliyun.com/zh/ims/user-guide/create-agents-for-audio-and-video-calls)

腾讯支持自定义LLM、流式TTS及打断；若采用自定义TTS通道，现有CosyVoice WebSocket须适配为其HTTP流式协议。[腾讯自定义TTS](https://cloud.tencent.com/document/product/647/112476)、[腾讯打断机制](https://cloud.tencent.com/document/product/647/112472)。火山支持自定义ASR/TTS与打断，须遵守其网关规范。[火山接入说明](https://docs.volcengine.com/docs/real_time_communication/IntegratedAIaudiovideointeractivesolution?lang=zh&redirect=1)

本轮只研究备用路线，未开通、购买或切换国内RTC服务。没有删除现有LiveKit Agent。国内/邻近位置本身不保证连通性；迁移前应先做TCP/TLS/health对照并确认常驻进程运行条件。

## 恢复后的完整RTC复测

一次正常Cloud ticket复测在7.686秒收到listening，但首问119帧送出后60秒内没有question/answer。清理均完成，结束与VOICE撤销HTTP200，测试profile missing。该次ASR摘要显示PCM 1,996,800字节（62.4秒）、墙钟57.8秒、56心跳、最大send等待3毫秒、compression15、final0。因此该次不是“WSS没有连上”，也不能只凭listening宣布语音就绪。该次测试使用的部署代码在Backend ASR ready前发布listening，这是确认的状态准确性问题。那次没有麦克风能量计数，无法回溯是否收到有效语音，不能证明过早状态是final0的唯一原因。

Worker修正`eeefe5d`仅在Backend ASR `ready`后发布首次listening，同时race识别结束和20秒startup deadline；提前注册watchdog/幂等shutdown，失败关闭Backend client。诊断默认关闭，开启时仅增加阶段及RMS>200的帧/包数字，不保存语音或转写。Worker完整46项测试通过。

原Cloud Agent的新复测使用正常后端ticket，没有本机Worker或dispatch替换。ASR握手connecting0ms、connected2310ms、ready2488ms；通话整体9.657秒listening。首问16.978/首答21.383秒，第二问35.878/第二答38.862秒。自动打断gap非零音频0帧、无旧轮重启；手动打断经数据库确认，后续65秒静默非零音频0帧。这些项目通过，但107.805秒第三次注入后40秒内无新question/answer，整轮`third_answer`超时，**不得标记全套通过**。

同job累计麦克风14,088帧、其中504语音帧；成功发送PCM4,630,400字节（144.7秒audio/138.5秒wall）、58语音包、135心跳、final2、最大send等待3ms。它证明本轮并非一直静音或识别从未连接；累计值不能证明第三句本身经过了哪个阶段。客户端397帧注入全部送出、captureerrors0，只证明客户端送入RTC，没有服务端逐句确认。关闭码1006出现在测试结束清理时，不能单凭该码认定长静默超时原因。

同连接的mic和ASR汇总均在ready后138.48秒生成，覆盖第三注入后约40秒。识别停止日志`Microphone recognition ended`出现在QA主动RTC断开收尾时，不能称为第三轮前已经断线。最后通过同Agent配置更新将`REMEMBER_REALTIME_NETWORK_DIAGNOSTICS`明确设为0；更新exit0，诊断关闭，生产域名/SNI/证书校验保持正常，没有固定IP替换。

QA结束HTTP200、VOICE撤销HTTP200；先清空预置音色引用再撤销grant，profile missing且无active call。没有真人音色、录音或克隆。安全数字报告：`build/realtime-cloud-ready-control-report.json`；此前本机完整对照：`build/realtime-local-worker-control-report.json`。单次健康检查、恢复的TCP请求或两轮成功均不能代替完整RTC验收，第三轮识别故障和间歇性连接的底层原因仍需进一步取证。

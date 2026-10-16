# 火山模块化语音上线与联调

2026-10-16，Asia/Singapore。本人在账号配置完成后明确要求「开始」，授权继续常驻后端部署、iOS 覆盖安装与真实线路联调。

## 上线结果

- Backend 源码 `63a1808`，release `ios-volcengine-63a1808`，CloudBase `remember-ios-api-046`，发布任务 `2371063` finished。以原线上 045 固定镜像 digest 为基础，仅覆盖提案中新增路线和已有通话等待修正所需的 12 个文件。原 LiveKit 客户端接口保留，未另行发布旧 Agent。
- PostgreSQL 迁移从 `0024_voiceprint_entrust` 升至 `0025_volcengine_voice`。执行 Alembic 生成的 PostgreSQL SQL，事务内检查旧版本；只新增独立通话审计表及索引，读回版本核对通过。
- 四项火山凭据注入服务端环境，`REMEMBER_VOLCENGINE_ENABLED=true`。逐项比对线上环境与预备发布配置一致；长期凭据不进镜像、移动端或 Git。本机私有凭据文件仍保留 `ENABLED=false`，不代表线上未启用。
- 后端最小副本数已读回为 1，最大仍为 1，CPU 1 核／内存 2 GB、公网、VPC、端口均保留。首次请求沿用了旧脚本的字符串 Value，未实际改变 MinNum；发现后按官方 DiffConfigItem 的 IntValue 修正，配置任务 0 表示同步完成，随后读回确认。常驻副本会持续使用运行资源。
- 公网 `/api/v1/service-info` 返回上述 release；`/ready` 的 database、object_store 均为 ok。
- iOS **1.14.0 / 2026101602** Release 构建与 `codesign --verify --deep --strict` 通过，已覆盖安装到 iPhone 15 Pro Max「黑幕」并成功启动，进程号 36669。安装清单读回新版本。未卸载；安装前 10 个 m4a（含 tmp 中已有文件）的大小、修改时间等 metadata 全部一致。安装后没有主动切换用户账号。
- 真正的 listening 仍以火山 conv 消息确认。实测零输入时未收到首个 listening，发送语音后才收到；iOS 麦克风接通但尚未确认 listening 时改为提示「麦克风已连接，请开始说话…」，避免一直显示泛化连接文案。此版仍保留 25 秒未就绪超时；后续真人失败及修正见下节。

## 实际网络验证

仅使用既有 `ios-synthetic-demo` 隔离账号、已有两段系统合成 PCM 和默认 TTS。测试客户端使用火山官方 npm Web SDK 4.69.3，通过自定义音轨发送合成 PCM；不申请 Mac 麦克风、不使用本人声音，不创建音色／声纹模板。Backend 使用真实火山 Start/Update/Stop 和现有 DeepSeek Twin 的完整生成与复核，不用测试答案代替。

- 三轮完整播放通过，包含第二轮「刚才说了什么」追问，以及第二轮结束后静默超过 65 秒再说话。三轮均收到对应 thinking、回答、非零下行音频及 answerFinish。数据库核对第二轮有前一答案关联，回答包含首句问候／打招呼内容。
- 自动插话检测通过；手动 interrupt 通过。在各自 1.2 秒宽限后、下一答案开始前，未再收到旧回答的非零音频样本。没有放宽原有宽限窗口。
- 撤销本轮 VOICE 后，3.5 秒复核通话心跳 HTTP 404；持久状态及远端停止完成。
- 独立场景停止心跳 20 秒后，心跳 HTTP 404；持久状态 ended，remote_stop_pending=false。此场景仍保持 RTC 客户端在房，验证服务端租约清理。
- 六个本轮 QA 通话全部终结，待停止任务 0，12 项本轮临时许可全部撤销。仅删除本轮 7 个合成答案及其聊天检索向量，已读回剩余 0；通话审计保留。本人资料、原音和原音色未用于探针或清理。

### 耗时样本

同一场景三个合成输入的客户端观测，单位秒；首声指 SDK 报告的首个非零远端音频，不能替代真人听感。

| 轮次 | 停说→thinking 事件 | thinking→观察到已存答案 | 停说→首个有声音频 |
| --- | ---: | ---: | ---: |
| 1 | 0.166 | 3.244 | 3.759 |
| 2 | 0.357 | 3.108 | 3.920 |
| 3 | 0.195 | 2.649 | 3.319 |

此前首轮诊断曾出现 10.510 秒才有声音，主要时间处于 Twin 等待阶段；不能称固定低延迟或保证三秒内响应。只有三个完整场景样本，不计算 P95。探针旧 heartbeat question 时间指标会在下一轮读到上一问题，出现负数，已排除，表中使用每轮独立的厂商 thinking 事件；原始报告保留。

首两份探针等待“全零音轨的初始 listening”超时，第三份已实际收到首轮完整音频，但探针错误等待 answerFinish 之后再次出现 listening；没有将它们算作全场景通过。修正合成端显式发布音轨及按官方 code=5 判断播放完成后执行上述通过场景。iOS 原本就处理 code=5。

## 边界与待本人体验

本次只提供公共 ASR＋现有 Evidence Twin＋默认 TTS。本人音色、绿色声纹姓名、自动记忆／自然取样尚未迁移，能力明确为 false；原功能资料保留。

本轮真实媒体检查使用 Web SDK；iOS 官方 SDK 的先前 25 项模拟器测试保留，本次没有冒充重跑。新增原生 SDK 的真机麦克风、外放回声、静音、输出切换、锁屏／断网行为和本人连续体验仍需手机实际通话验证。本人随后反馈：已经对手机说话，仍出现服务未就绪并结束。该反馈证明当前原生真机通话未通过；安装、启动和 Web 合成检查不能代替手机通话通过。

## 证据

后端工作区 `build/`：`volcengine-deployment-20261016.json`、`volcengine-three-rounds-20261016.json`、`volcengine-interrupt-revoke-20261016.json`、`volcengine-heartbeat-loss-20261016.json`、`volcengine-context-proof-20261016.json`、`volcengine-latency-20261016.json`、`volcengine-cleanup-proof-20261016.json`。早期失败探针另存；原始控制面、配置和脚本位于 ignored `build/private/`，不提交。

主工作区 `build/`：`volc-device-deployment-20261016.json`、`volc-ios-source-manifest-20261016.json`、`volc-research/ios-deploy-release-20261016.log`；原始设备安装和文件清单位于 `build/private/`。iOS 主工作区原有大量未提交功能保持，未将其批量提交或重置。

官方参考：[AI 状态与 conv 状态码](https://docs.volcengine.com/docs/real_time_communication/GetAIstatus?lang=zh)、[CloudBase 配置字段类型](https://cloud.tencent.com/document/api/1243/75713)。

## 原生真机失败与 1.14.1 修正候选

本人反馈已经说话仍报错。后端审计显示本次通话已请求远端启动、持续约 42.6 秒，但没有 ASR 问题、没有回答，随后已结束且无待停止任务。设备 SDK 日志可见初始采集静音、capture enabled=false，硬件录音设备启动成功；这些证据尚不足以确认完整根因。

候选版 1.14.1 / 2026101603 删除进房前的预先采集静音，在后端激活后启动采集、取消静音并显式发布音频。已识别 bot 入房、但尚未收到首个 conv 时显示「已接通，请开始说话」，避免将无初始 conv 误判为云服务未就绪；没有 bot 入房仍保留连接超时。首个 thinking 也可确认助手可用，不依赖先收到 listening。

加入仅覆盖最近一通的本机诊断 `Library/Application Support/VoiceDiagnostics/latest.json`，记录 SDK 本地音量报告计数、发送码率、入房、bot 出现、状态和错误数字。没有音频、识别文本、身份、房间号或凭据；文件受系统完整文件保护、目录不备份，不上传后端。

已实际执行 27 项模拟器通话测试，0 失败；包括新增静默已接通不超时、缺失 bot 仍超时两项回归。Release 构建与深度签名验证通过。手机连接后已覆盖安装并成功启动；设备清单读回 1.14.1 / 2026101603，安装前后原有 10 个 m4a 文件的元数据完全一致。真人采集与连续两轮验证待完成。记录 `build/volc-native-ready-fix-20261016.json`。不能将该候选记作真机问题已解决。


覆盖安装后的真实手机诊断已收到 48 次本地音量报告，4 次超过近似静音阈值、最高音量 116，最高音频发送码率 59 kbps。roomState=0、audioError=0、bot 入房确认、8 个有效 conv 事件，最新 stage=5。后端独立读回 last_round=2、存在当前回答且 failure=false，证明本次真实原生麦克风已采集、上行发送并完成至少两轮云端回答处理。该时点通话仍在进行；本人是否实际听清两轮、结束后远端清理，仍待确认。


本人最终明确确认「两轮都能正常回应」。通话结束后，本机诊断 ended=true、音频错误 0、17 个有效状态事件、11 次有声音量报告；后端 last_round=5、ended=true、remote_stop_pending=false、failure=false，确认本次通话和远端任务均已停止。结合两轮真人听感确认，1.14.1 的手机采集、发送、ASR→Twin→TTS 回答及第二轮上下文通话验证通过。最后一轮在 thinking 阶段结束，未将其记作完整播放；也未据此宣称低于三秒响应或验证其他原生场景。

本次修正同时调整初始静音、显式发布与首轮就绪判断；现有证据确认组合修正有效，未通过单因素实验将故障唯一归因于其中一项。其他锁屏、网络切换、耳机与长期延迟体验仍不在本次两轮验收范围。

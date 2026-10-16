2026-10-16 iOS 最新源码快照：**1.17.0 / 2026101614**，包含采集／花园重构及录音豆扫描修正。GitHub 分支为 `codex/ios-latest-20261016`；范围、构建方法与验证边界见[快照记录](docs/verification/IOS_GITHUB_SNAPSHOT_2026_10_16.md)。

2026-10-16 本人音色电流声修复已安装：**1.16.3 / 2026101613** 已覆盖安装到「黑幕」并独立读回版本。以已安装1.16.2为基线，仅叠加 PCM 播放时钟／缓冲修复；34项冻结版本检查及签名构建通过。原9段录音、3段声音样本和相关22个文件的信息核对一致；实际通话听感待本人验证。见[安装记录](docs/verification/IOS_VOICE_NOISE_DEVICE_2026_10_16.md)与[排查原因](docs/verification/IOS_PERSONAL_VOICE_NOISE_2026_10_16.md)。

2026-10-16 通话状态修复已安装：iOS **1.16.2 / 2026101612** 已覆盖安装到「黑幕」，设备版本读回确认；取消／刷新不再覆盖实际挂断原因。冻结源码155项定向检查、Release构建和签名校验通过，9段原音路径、大小与修改时间保留（1项系统数据保护扩展属性新增）。手机锁屏，普通自动启动被拒；本轮未部署后端，也不代表数据库持锁问题已修复。见[安装与验证](docs/verification/IOS_VOICE_FIX_DEVICE_2026_10_16.md)。

2026-10-16 最新修改已统一部署：iOS **1.16.1 / 2026101611** 已覆盖安装到「黑幕」并正常启动，原有7个录音文件 metadata 完整保留；**CloudBase054 / `ios-latest-f54e295dc7d4`** 已上线。包含录音页蓝牙入口、白色背景与黑色设备展示、本人文字／语音对话归档及左滑删除、游客对话不留存，以及最新托付／暗号保护修复。隔离账号的归档删除、游客连续对话零落库、暗号解锁与撤销检查通过；见[部署与验证](docs/verification/IOS_LATEST_DEVICE_DEPLOYMENT_2026_10_16.md)。

2026-10-16 游客暗号托付审查修复：限流匹配信号、句中完整暗号泄露、跨库披露及上锁／音频竞态已在本地修复；旧计划保留并支持本人私下重核验原暗号。最终Backend 126项专项、Contract 60项、iOS 94项单元和3项UI检查通过。原检查轮未部署，现已纳入上述统一部署，见[追加修复验证](docs/verification/GUEST_ENTRUSTMENT_FIX_2026_10_16.md)。

2026-10-16 孪生宣传片界面与音量动效：iOS **1.16.0 / 2026101610** 已覆盖安装到「黑幕」并正常启动。深蓝夜色、勿忘我光环与真实音量驱动的环形光条已接入；安装前后 7 个原有录音文件 metadata 一致。签名硬件版与版本读回通过，真人通话动效待本人查看。见[真机交付记录](docs/verification/IOS_TWIN_MOTION_DEVICE_2026_10_16.md)。

2026-10-16 记忆花园源码更新：AI 故事／事件自动展示，时间线与图谱合并，右侧复用已有素材；详情支持原音、手动编辑与删除（保留原音）。70 项模拟器逻辑／界面检查通过；尚未安装实体手机。见[本轮验证](docs/verification/IOS_GARDEN_EVENT_STORIES_2026_10_16.md)。

2026-10-16 主用户／亲友游客双模式已在本地实现：本人密码登录，游客免密使用已开放花园和范围内文字／语音 Twin；整段原音预览后开放，返回本人须复验密码，访客不写本人模型。Backend 876项通过（6跳过）、Contract 55项、iOS 49项单元与2项UI检查通过。本轮未部署或安装真机，见[验证记录](docs/verification/IOS_GUEST_MODES_2026_10_16.md)。

2026-10-16 声音复刻正式流程：CloudBase053 / `ios-voice-normal-flow-b3292be` 已上线。原音保留，供应商副本自动校正低电平；正式提交→供应商复刻→合成试听及临时资源清理已用隔离合成账号实跑通过。86 项定向、830 项 Backend 回归通过（6 跳过）。本人音色仍待试听确认。见[验证记录](docs/verification/VOICE_CLONE_NORMAL_FLOW_2026_10_16.md)。

2026-10-16 通话音色选择修正：iOS **1.15.4 / 2026101609** 已覆盖安装到「黑幕」，11 个原录音 metadata 保持一致。已确认的本人音色默认用于通话，手动选择按本人空间／音色保存；未确认提示、拨号与通话中声音模式明确显示。48 项定向测试及 2 项 UI 检查通过；手机锁屏导致自动启动被拒，实际听感待本人解锁验证。见[验证记录](docs/verification/IOS_VOICE_SELECTION_2026_10_16.md)。

2026-10-16 审核首批修复：删除队列、国内 RTC 有界恢复、资料不足回执、本人音色验收／重录及完整源码基线已修复。iOS **1.15.2 / 2026101607** 已签名构建；手机不可连接，尚未覆盖安装或切换 Backend，线上仍为051。验证结果与后续边界见[修复记录](docs/verification/VOICE_AUDIT_FIXES_2026_10_16.md)。

2026-10-16 本人音色启动修正：CloudBase051／`ios-volcengine-parity-cb8967c` 已发布，iOS **1.15.1 / 2026101606** 已覆盖安装，11 个原录音保持完整。真实 RTC 对照定位并修正关闭 TTS 后仍传合成参数导致的 1000002；App 联网验证已恢复。本人暂时无法通话，真人试听与持续通话待验；修正后浏览器语音探针未取得答案，未记为端到端通过。见[实跑记录](docs/verification/VOLCENGINE_PERSONAL_STARTUP_FIX_2026_10_16.md)。

2026-10-16 语音等待／停播排查：误打断恢复及可选模型等待已在服务端源码修正，本地回归和单轮整段播放通过；完整多轮复核遇到识别连接中断，**本轮尚未发布**。见[验证与限制](docs/verification/IOS_VOICE_CONTINUITY_2026_10_16.md)。

2026-10-16 切页弹窗修复：**1.13.3 / 2026101601** 已覆盖安装到「黑幕」。页面加载正常取消不再显示“需要留意／已取消”，也不清空当前内容；真实登录失效仍提示。62 项相关测试通过，9 个已有原音文件大小与修改时间保留；安装后手机锁屏，待解锁打开。[修复记录](docs/verification/IOS_CANCELLED_REFRESH_2026_10_16.md)。

2026-10-16 已统一部署：通话绿色声纹姓名与默认手机外放已覆盖安装到「黑幕」，版本 **1.13.2 / 2026101508**；CloudBase045 与原语音 Agent 已更新。合成声纹姓名匹配／撤销检查通过；通话前两轮音频和打断通过，静默65秒后的第三轮超时，完整回归未通过。解锁后已确认新版启动；真人体验待确认。[发布与限制](docs/verification/IOS_SPEAKER_DISPLAY_DEPLOYMENT_2026_10_16.md)。

2026-10-15 通话外放适配：已改为默认手机扬声器＋内置麦克风，无需绑定蓝牙，支持切换听筒／耳机；23 项通话逻辑及 2 项 UI 检查、签名构建通过。真机未连接，尚未安装，待统一发布；[验证与限制](docs/verification/IOS_VOICE_SPEAKER_OUTPUT_2026_10_15.md)。

2026-10-15 实时活动样式：1.13.1 / 2026101507 已覆盖安装到「黑幕」，锁屏和灵动岛复用 App 的勿忘我、配色及字体，浅／深色与大字号共享组件预览检查通过。详见 [样式验证](docs/verification/RECORDING_ACTIVITY_STYLE_2026_10_15.md)。

2026-10-15 后台／录音豆切片：已接入官方 D3200 SDK、后台录音与实时活动、“我的”设备图示及本人声纹限定的自动记忆；后端 `ios-wearable-capture-fcb7aa0` 已部署。iOS 1.13.0 / 2026101506 已完成主 App／实时活动扩展签名并覆盖安装到「黑幕」，真实硬件长期佩戴／锁屏仍待验证。详见 [验证记录](docs/verification/BACKGROUND_WEARABLE_CAPTURE_2026_10_15.md)。

# Remember Me

2026-10-16 录音豆持续接收与重点规则：源码已接通录音中的实时音频分段、重点开关、后台完整重点保护及普通记忆归并，原音保留。Backend 212 项、AI Core 323 项、Contract 62 项，以及 iOS 50 项单元／1 项界面检查通过；**尚未部署或安装手机版本**。佩戴自动开录、物理按键语义和长时后台蓝牙仍待实机确认；见[交付与边界](docs/verification/WEARABLE_PRIORITY_CAPTURE_2026_10_16.md)。

> **2026-09-27 双端集成：** Android 的 #78／#79 和随后提交的 #81 界面与 iOS 的 #76／#77／#80 已接合。Android 单元测试、APK 构建与 lint 通过；iOS UI v6 在 Mac 的 Xcode 27 模拟器目标构建通过。真机运行结果另记，不能由构建结果推断。

Remember Me is a consent-first system that turns recorded life episodes into traceable memories, an evolving person model, and evidence-backed Twin responses. The existing Android client and the authorized iOS track share one Backend Contract and processing path.

## Current status

2026-10-15 我的录音：iOS **1.12.1 / 2026101505** 已覆盖安装并启动到「黑幕」。右滑删除覆盖本机／云端／对话原话／多人录音；CloudBase043 删除来源及派生记忆并重算人物模型，失败可重试。见 [验证记录](docs/verification/IOS_RECORDING_SWIPE_DELETE_2026_10_15.md)。

2026-10-15 声纹与人物模型：iOS **1.12.0 / 2026101504** 已覆盖安装到「黑幕」（锁屏，自动启动未通过）；CloudBase042 / `1e8369e` 与原语音Agent已更新。真实声学模板用于录音／多人录音／同手机多人Twin，本人匹配原话自动更新并保留原音；托付按账号＋密语＋限定范围解锁，访客不训练主人。新增人物模型人体填色和资料覆盖。见 [交付与验证](docs/verification/IOS_VOICEPRINT_PERSONAL_MODEL_2026_10_15.md)。

2026-10-15 自然采集修订：iOS **1.11.0 / 2026101503** 已安装到「黑幕」，CloudBase039 / `796591a` 与原语音Worker已更新。点击开始确认用途，去掉固定同意句及重复开关；名字没听清也继续记录。正常语音聊天自动留原话，并累积短句后台准备音色，无需另录一遍。真实三轮通话／自动采集与无口令双人ASR通过，见[验证记录](docs/verification/IOS_NATURAL_CAPTURE_2026_10_15.md)。

2026-10-15 多人录音：**1.10.0 / 2026101502** 已安装到「黑幕」，CloudBase037 / `4e78742` 已上线。入口「录音 → 我的录音 → 多人录音」；依次语音自我介绍后自动关联本段发言，无手动确认姓名。后端完整及删除终态定向回归、34 项契约与 8 项 iOS 检查通过；公网合成双人完整流程通过，原有四段本机原音保留。仅同段识别，真人／相近声音准确率仍需实际录音验证。见[交付与限制](docs/verification/IOS_SPEAKER_INTRODUCTIONS_2026_10_15.md)。

2026-10-15 iOS 界面反馈：**1.9.1 / 2026101501** 已覆盖安装到「黑幕」并启动。录音列表收进「我的录音」，记忆入口直达花园／图谱并删除搜索，音色设置支持照读后直接确认，补齐键盘收起操作。79 项定向检查与签名构建通过；本人朗读与试听体验待实际使用。见[验证记录](docs/verification/IOS_CAPTURE_GARDEN_VOICE_FEEDBACK_2026_10_15.md)。

2026-10-14 共享通话记忆与个人学习：CloudBase034 / `25b8e81` 已发布，新电话自动承接最近会话并检索旧电话／文字原消息，具体主题查询已在线核对。Mac 自动训练器已常驻；独立 MODEL_TRAINING 许可、候选状态与60题本人一致率验证上线，候选尚未接入生产推理或专属盲测。iOS **1.9.0 / 2026101410** 已签名构建，15项单元与3个 UI 场景通过；「黑幕」未连接、尚未覆盖安装。见[交付与边界](docs/verification/IOS_PERSONAL_LEARNING_2026_10_14.md)。

2026-10-14 通话上下文隔离：CloudBase026 / **3719a0b** 已上线，新call不自动召回旧call／文字聊天；同call较早消息和文字旧聊天检索保留，相同turn跨call不复用旧答案，挂断／插话后的晚到答案不落库。432项自动回归、发布后完整三轮／65秒／两种打断及隔离API验证通过；原数据与iOS1.8.3保留。见[验证记录](docs/verification/IOS_VOICE_CALL_SCOPE_2026_10_14.md)。

2026-10-14 当前语音完整复测：默认声音／第一人称版本的三轮、打断、65秒静默、结束及撤权在本机staging和原Cloud重试通过；首个Cloud第二轮502仍保留，根因未证实。数字失败阶段诊断已发布原Worker，默认关闭，60项Worker／测试票据用例及发布后单轮RTC通过。见[复测与发布记录](docs/verification/IOS_VOICE_CURRENT_REGRESSION_2026_10_14.md)，不代替本人音色和自然体验。

2026-10-14 会议事项逐项落实：已补齐[全文覆盖与证据总表](docs/product/PRODUCT_COMPLETION_TRACKER_2026_10_14.md)、局部保护／底层删除、多人归属／声纹、指定对象托付、设备／唤醒的详细提案和[本人演示验收单](docs/verification/PRODUCT_DEMO_ACCEPTANCE_2026_10_14.md)。本轮当前基础能力91项自动检查通过；新增跨模块能力待批准实施，本人自然体验与耳机结果仍待实际操作。

2026-10-14 孪生 UI 精修：iOS **1.8.3 / 2026101408** 已覆盖安装到「黑幕」并核对启动。聊天页直达旧聊天记忆／本人理解，通话开始和结束固定在底部，本人音色设置可收起，已有样本自动展开，复刻阶段与试听更清楚。9 个不同 UI 用例通过，包含深色和极大字号；见[验证记录](docs/verification/IOS_TWIN_UI_2026_10_14.md)。

2026-10-14 Twin 本人视角：CloudBase025 / `54856ef` 已上线，依据核对录音和确认资料，以“我”表达本人身份、记忆、偏好及选择；普通身份问题简短回应，未知事实不补猜。保留来源与推测标签，语音不再机械朗读推测前缀。AI Core 296 项、Backend 54 项及真实模型／线上合成问答检查通过；首版真实 RTC 单轮通过。沿用已安装 iOS 1.8.2，无 Native 变更。见[验证记录](docs/verification/IOS_TWIN_FIRST_PERSON_2026_10_14.md)。

2026-10-14 默认声音通话与音色状态：iOS **1.8.2 / 2026101405** 已覆盖安装到「黑幕」并核对启动。未复刻时也可用明确标注的默认声音通话；本人音色显示录制／提交／就绪状态，支持合成试听与后续切换。CloudBase023 / `6cb7c17` 的默认模式真实 RTC 单轮及试听检查通过（隔离测试账号与系统音色）；本人复刻仍由本人提交并试听确认。见[验证记录](docs/verification/IOS_DEFAULT_VOICE_AND_READINESS_2026_10_14.md)。

2026-10-14 记忆花园基础版：iOS **1.8.0 / 2026101402** 已覆盖安装到「黑幕」并成功启动，入口为「记忆 → 进入记忆花园」。支持真实记忆及已核对故事／人物的二维浏览、搜索、来源查看、本机移出与恢复。100 项单元及 4 项不同 UI 用例、隔离云端联调通过；原音与原记忆保留，密码保护和身后开放仍待提案批准。见[验证记录](docs/verification/IOS_MEMORY_GARDEN_2026_10_14.md)。

2026-10-14 声音设置排查：iOS **1.8.0 / 2026101402** 修正个人声音入口，并明确区分录音保存在手机与提交音色复刻；样本文字可在同一账号空间恢复。当前 iOS 云端尚无非测试音色或有效 VOICE 授权，实际失败页面待本人回复；不能称真人通话已经修复。见[诊断与验证](docs/verification/IOS_VOICE_ENROLLMENT_DIAGNOSIS_2026_10_14.md)。

2026-10-14 前台实时语音完善：iOS **1.7.1 / 2026101401** 已覆盖安装到「黑幕」并成功启动。断线／耳机断开／锁屏结束通话，重新开始检查服务、用途和音色；保留连续追问与打断。CloudBase019 与新 Worker 的三轮／65秒静默合成验收通过，原数据保留；本人音色和真实耳机操作仍待本人验收。见[验证记录](docs/verification/IOS_VOICE_COMPLETION_2026_10_14.md)与[后续提案](docs/architecture/product-completion-proposals-2026-10-14.md)。

2026-10-13 旧聊天长期记忆：iOS **1.7.0 / 2026101313** 已覆盖安装并启动。孪生现在可检索近期20轮之外及其他会话的原消息，并整理带来源的摘要；加号菜单可查看、搜索、关闭和清除聊天记忆。独立iOS后端当前生产源码为 `codex/twin-chat-memory` / `df7b22b`（CloudRun018），包含既有实时Voice；主工作区的旧Backend源码不是当前部署基线。云端合成检查通过，不代表本人相似度已经提高，见[验证记录](docs/verification/IOS_CHAT_MEMORY_2026_10_13.md)。

The iOS voice-to-Person-Model slice was authorized in [Issue #75](https://github.com/ztjklt/Remember-Me/issues/75). The Product Owner subsequently authorized an iOS-first evidence Twin and separately consented local Voice loop in the [Twin proposal](docs/architecture/twin-voice-contract-proposal.md), followed by a locked-answer [calibration slice](docs/architecture/calibration-contract-proposal.md). This work uses the existing Phase 1 recording path. The authorized iOS cloud slice now has a separate CloudBase backend; the paired Mac path remains available.

The latest Android portrait UI from #81 opens the locally working recording and archive flow from #79. The graph and agent pages label unconnected preview content. Its real memory-processing adapter is not connected in the default build; the Android APK contains no provider credentials. The iOS SwiftUI project lives in [apps/ios](apps/ios/README.md); its paired Mac stack uses local Whisper and DeepSeek V4 Flash behind Backend and AI Core adapters. Audio remains local; confirmed transcript text is sent to DeepSeek. Local Qwen remains an adapter option. Feature readiness is tracked through the [roadmap](docs/roadmap/ROADMAP.md); physical iPhone evidence is recorded separately from simulator builds and synthetic audio probes.

2026-10-13 iOS：实时 Voice 修正版本 **1.6.2 / 2026101311** 已按本人要求覆盖安装到 iPhone 15 Pro Max「黑幕」，设备版本查询核对通过，devicectl 确认启动成功；未执行卸载或清空容器。Voice 10 项与 LocalRecording 20 项定向测试通过；本人音色和真机通话体验待本人操作。之前的一键录音 1.6.1 已由该版更新，见[一键录音验证记录](docs/verification/IOS_ONE_TAP_RECORDING_2026_10_13.md)及[实时 Voice 验证记录](docs/verification/IOS_REALTIME_VOICE_2026_10_13.md)。

实时 Voice 入口为 **孪生 → 右上角电话 → 确认用途 → 录制 5–15 秒本人声音 → 核对实际文字并确认只有本人声音 → 单独授权并复刻 → 检查音色就绪 → 开始语音通话**。通话支持静音、直接插话、手动打断及结束；云端问答需要另行授权。实现采用 LiveKit Cloud 与百炼 CosyVoice；本人音色复刻与新构建的真机通话仍待本人操作验证，云端合成音频探测不代表这两项已通过。详细结果见[实时 Voice 验证记录](docs/verification/IOS_REALTIME_VOICE_2026_10_13.md)。

实时启动超时已定位到云端 Worker 建立上海后端连接的阶段；后续连接恢复，另修正了识别尚未就绪时提前显示“正在监听”的问题。保留原 LiveKit Agent，未切换或开通其他 RTC。对照证据、复测结果与国内备用路线见[实时超时诊断](docs/verification/IOS_REALTIME_TIMEOUT_DIAGNOSIS_2026_10_13.md)。

| Phase | Status |
| --- | --- |
| Phase 1 — Golden Path | COMMITTED / NOW |
| Phase 2 — Core Twin | iOS-first slice AUTHORIZED / IN PROGRESS |
| Phase 3 — Calibration + Voice | iOS-first calibration and local Voice slices AUTHORIZED / IN PROGRESS |
| Phase 4 — Hardware + Legacy | BACKLOG / CONDITIONAL |

## Baseline documents

- [Remember Me PRD v3.0](docs/PRD/Remember_Me_PRD_v3.0.docx) — product behavior source of truth; the current delivery model amends its client scope to iOS and Android
- [PRD v3.0 Summary](docs/PRD/PRD_V3_SUMMARY.md) — agent-readable orientation
- [Current delivery model](docs/team/00_TEAM_OWNERSHIP.md) — 张天霁 leads iOS, 刘修贤 leads Android; other work is delegated only through small Issues
- [Team Development Guide v1.0](docs/team/Remember_Me_Team_Development_Guide_v1.0.docx) — historical engineering guide; fixed staffing assignments are superseded
- [Roadmap](docs/roadmap/ROADMAP.md) — phases and exit gates
- [Phase 1 Team Kickoff](docs/team/PHASE1_KICKOFF.md) — historical first assignments and PR context

PRD v2.0 is archived history in [`docs/PRD/archive/`](docs/PRD/archive/). The 2026-09-26 Product Owner decision in the current delivery model activates iOS alongside Android; it does not revive archived product behavior.

## Repository map

- `apps/android` — Android client (Kotlin, Jetpack Compose) and its build documentation
- `apps/ios` — iOS SwiftUI client, local pairing and device runbook
- `services/backend` — API, persistence, auth, jobs, and storage
- `services/ai-core` — memory extraction, person model, Twin, calibration, and capture planning
- `services/voice` — consent-gated voice dataset, clone, and TTS adapters
- `packages/contracts` — versioned cross-module schemas; the integration source of truth
- `infra` — environments, deployment, migrations, logging, and monitoring
- `docs/PRD` — current PRD and its agent-readable summary
- `docs/architecture` — system architecture baseline
- `docs/roadmap` — phase status, gates, and owners
- `docs/team` — current delivery model and historical task briefs
- `docs/api` — contract field and integration guidance

## Start here

All contributors and coding agents must read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), the [PRD v3.0 summary](docs/PRD/PRD_V3_SUMMARY.md), the [current delivery model](docs/team/00_TEAM_OWNERSHIP.md), the [roadmap](docs/roadmap/ROADMAP.md), and [shared contracts](packages/contracts/README.md) before changing code. A delegated contributor also reads the Issue that defines the task.

Android setup and build commands are in [apps/android/README.md](apps/android/README.md). The local verification command is:

```bash
cd apps/android
./gradlew test assembleDebug
```

For the local iOS voice-to-Person-Model path, follow [apps/ios/README.md](apps/ios/README.md).
2026-10-16 iOS 源码重构：**1.17.0 / 2026101614** 已对齐 Android 的自动转写草稿、一次保存／累计分析及原稿校对；记忆花园新增原生花田、花瓣全文阅读、八侧面和四个人物视图。iOS 247 项、Backend 337 项、AI Core 67 项、Contract 72 项通过，另 1 项设备检查在模拟器跳过。**新后端尚未部署，尚未安装实体手机**。见[验证与预览](docs/verification/IOS_ANDROID_CAPTURE_GARDEN_2026_10_16.md)。

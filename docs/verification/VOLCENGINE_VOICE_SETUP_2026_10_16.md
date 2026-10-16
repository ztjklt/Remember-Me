# 火山国内模块化语音：开通与联调

2026-10-16。本人已开通 AI 音视频互动方案并完成两次短信认证；已确认默认 AI 应用启用，创建专用 IAM 子用户和最小权限策略，并保存本机凭据。后续已完成上线及隔离合成通话，见[发布记录](VOLCENGINE_VOICE_DEPLOYMENT_2026_10_16.md)；未购买资源包。授权边界见 [重构提案](../architecture/volcengine-modular-voice-2026-10-16.md)。

## 本人操作

1. 登录 https://console.volcengine.com/rtc，开通实时音视频及「AI 音视频互动方案」。先用默认创建的 AI 应用；公共 ASR／默认 TTS 可以通过该方案的公共模型资源计费，首轮不需要购买声音复刻槽位或大资源包。控制台协议及按量计费以本人看到的实际页面为准。
2. 应用管理获取 AppID 和 AppKey。访问控制准备独立子用户 AK／SK，并授予所需 RTC API 权限；默认方案文档以 RTCFullAccess 为起步权限，生产可进一步限缩。不要把凭据填进 iOS、Git、聊天或截图。
3. 将四项填入主工作区 `build/private/volcengine.env`（0600，ignored）；文件字段为 `REMEMBER_VOLCENGINE_APP_ID`、`REMEMBER_VOLCENGINE_APP_KEY`、`REMEMBER_VOLCENGINE_ACCESS_KEY_ID`、`REMEMBER_VOLCENGINE_SECRET_ACCESS_KEY`。保持 ENABLED=false，告诉开发者“已开通／已填好”即可。

## 集成操作

Backend 工作区 `speaker-introductions/Remember Me` 的 `codex/volcengine-modular-voice-20261016` 基于当前语音修复基线。iOS 位于主工作区，原有未提交功能保留。

- 执行迁移 `0025_volcengine_voice`：只新增通话审计表，旧资料、音色、许可及数据库表不删除。
- 服务端保留既有 REALTIME_PUBLIC_URL 与至少 32 字节 WORKER_SECRET。自定义 LLM 地址必须能从火山通过 HTTPS 访问，反向代理关闭 SSE 缓冲。没有临时公网/测试凭据时，不假定云端已经可用。
- 必须将 Backend 部署为至少一个常驻副本，保证两秒轮询的清理进程可运行；不能依靠自动缩为零的进程或分钟级函数保证通话租约。服务停机期间不能把“稍后清理”说成立即停止。
- 在服务器秘密配置注入四项凭据。先用隔离的合成测试账号／默认声音做新线路联调，验证成功后再开启 VOLCENGINE_ENABLED，安装对应 iOS 构建。旧客户端仍用原版本接口，新客户端明确协商 transport=volcengine。
- 本机只读配置检查：`services/backend/.venv/bin/python tools/verification/volcengine_preflight.py --config /absolute/private/volcengine.env`；只输出字段名及布尔值，不调用收费 API。
- iOS 官方 SDK 固定 3.60.107.1100，执行 `apps/ios/scripts/prepare-volcengine.sh` 下载并校验固定 SHA-256，然后执行 XcodeGen。二进制不提交；服务器 AK/SK/AppKey 不进客户端。

## 新通话时序

POST calls 只登记通话、签发指定房间／用户的音频发布与订阅票据，不启动收费任务；iOS 先加入房间，再调用 activate。activate 以数据库标记保证只发送一次 Start，超时也不自动重复启动。原生 conv 事件确认实际 listening，不能用 HTTP 200 或进房成功替代就绪。

CustomLLM 的每轮 round_id 映射独立 turn，回调只有该通话的派生凭据。服务端只接收最后一条 user 识别文本，使用原后端管理上下文；模型完整校验后才把文字送 TTS，UNKNOWN 只显示文字。打断操作期间阻挡下一轮领取，防止迟到的远端 interrupt 取消新的回答。挂断先落库再 Stop，失败保持待清理状态供维护进程重试；手机每次 heartbeat 延长 15 秒租约，不能从过期租约复活。

## 当前能力与验收

首批为公共 ASR＋现有 Twin＋豆包默认 TTS。原本人音色与声音样本保留，**尚未迁移本人音色、绿色声纹姓名、自动记忆和自然取样**，对应能力明确为 false，不能将旧服务声音 ID 直接复用。配置不同服务商必须重新确认用途。

联调需要分别记录：停说→识别 final、final→Twin 校验完成、完成→首个可听声音，以及整体中位数／P95。实测连续多轮、第二轮带上下文追问、65 秒静默续聊、安静完整播放、自动／手动打断、静音／耳机切换／锁屏／断网／撤权。本人音色和真人听感单独记录，不能由合成测试或本地通过推断。

官方资料：[模块化方案](https://docs.volcengine.com/docs/real_time_communication/IntegratedAIaudiovideointeractivesolution?lang=zh&redirect=1)、[计费](https://docs.volcengine.com/docs/real_time_communication/AIaudiovideointeractivebilling?lang=zh&redirect=1)、[官方示例](https://github.com/volcengine/rtc-aigc-demo)、[RTC 鉴权](https://docs.volcengine.com/docs/real_time_communication/AuthenticationusingToken?lang=zh)。

## 本地验证结果

- Backend 全量回归：803 项收集，797 通过、6 跳过，退出 0；现有 Starlette／SQLite 弃用提示保留。此后补强打断控制条件更新的原子检查，新增路线 13 项定向复核通过。完整日志 `build/volc-backend-verified.log`，定向日志 `build/volc-controls-verified.log`。
- 契约包：46 项通过，包含新线路请求不能打开未授权采集／本人音色、票据不带长期凭据、心跳与 scoped turn。
- iOS：原通话 23 项＋火山票据／TLV 2 项，共 25 项模拟器测试通过；初次禁用代码签名导致 SDK 动态库无法加载，改用模拟器 ad-hoc 签名后通过。不是实际 RTC 网络、麦克风或播放测试。
- iPhone Release 签名构建通过；构建与 `codesign --verify --deep --strict` 的结果仅表示本地构建，不代表已安装或线上可用。
- RTC HTTP 签名与火山官方 Python SDK 1.0.229 的固定假凭据／日期样例完全一致；SDK 下载自官方源并校验 SHA-256。房间 token 权限及真实媒体仍需开通后的供应商验证。
- 私有配置预检查退出 0：六项检查全部为 true。公网回调地址和 worker secret 从已有后端部署记录复用到本机，部署前仍需核对线上当前值；记录中的 MinNum=0，尚不满足常驻副本要求。功能保持 enabled=false，因此该检查器按定义输出 configured=false。该脚本不枚举云资源，created_resources=false 不是控制台没有资源的证明。
- 本人明确确认后创建 `remember-me-rtc`，仅编程访问、无控制台登录，仅绑定 `RememberMeRTCVoiceCalls`：`rtc:StartVoiceChat`、`rtc:UpdateVoiceChat`、`rtc:StopVoiceChat`，资源限定为当前默认 AI 应用的 AppId。控制台用户详情已核对。
- 四项凭据存放在主工作区 `build/private/volcengine.env`，导出 CSV 移至同一私有目录；两者均为 0600、被 Git 忽略，未输出凭据。
- 使用真实 AK/SK 向官方固定端点签名发送一次 StopVoiceChat，RoomId/TaskId 为随机且从未创建的联调标识；返回 HTTP 200、有效 RequestId、无 ResponseMetadata.Error。只证明该请求的签名／停止权限可用，未启动任务，不证明 Start/Update、ASR/TTS、媒体或多轮通话可用。
- 必须完成公网回调、常驻服务部署及真实多轮测试后才能确认速度和稳定性。

早期回归暴露了迁移表清单需要新增表、机器人先启动会丢初始就绪事件等问题，均已修正；中途改动迁移时旧测试进程加载了旧模型，相关失败不计成功。上述 Backend 全量结果来自重新启动的干净测试进程。

## 上线补充

2026-10-16 本人要求「开始」后，已完成迁移、CloudBase046 常驻副本部署及 iOS 1.14.0 覆盖安装并启动。线上新线路已启用；本机密钥文件仍为关闭状态。默认声音的真实合成媒体检查通过，手机实际体验待本人确认。详见[完整发布与验证](VOLCENGINE_VOICE_DEPLOYMENT_2026_10_16.md)。

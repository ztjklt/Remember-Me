# 火山通话连续性与原有功能恢复

2026-10-16，Asia/Singapore。本人在当前会话要求排查亮屏、前台通话中断，并恢复声音复刻、声纹及既有语音功能。授权范围见 [功能恢复提案](../architecture/volcengine-feature-parity-2026-10-16.md)。

## 代码与安装

2026-10-16 后续真机反馈：本人模式仍无声并在约 2 秒结束，已定位异步初始化参数错误并另行修正，见[本人模式启动排查](VOLCENGINE_PERSONAL_STARTUP_FIX_2026_10_16.md)。下文 049 合成 API 结果不能代替本次真机验证。

Backend 已提交 `2e8ba70`（恢复个人音色、声纹、自然采集）、`97d79f4`（独立资料处理循环、输出授权检查节流）、`a6e36d1`（跨发布版本清理隔离、同用途版本控制锁）和 `178c912`（多项许可分别撤销时保持音色删除终态）。新增迁移 `0026_volcengine_features` 已从 0025 事务执行并读回，只有新增字段及外键，不删除原资料。

iOS 1.15.0 / 2026101605 Release 构建、深度签名核验、覆盖安装通过，设备版本清单读回一致。安装前后 11 个原有 m4a 文件元数据一致。主工作区原有未提交功能未批量提交或重置；源码摘要在 `build/volc-parity-ios-20261016.json`。安装后自动启动因手机锁屏被系统拒绝；已请本人解锁打开，尚未将新版真人连续通话或本人音色听感记作通过。

## 恢复路径

- 火山 RTC 与公共实时 ASR 保留；默认声音仍使用豆包 TTS。已有本人音色由原 CosyVoice profile 继续提供，复刻、状态查询及试听通过火山作用域别名使用同一后端资料。本人模式关闭默认 TTS，仅对有效、已保存、非 UNKNOWN 的当前答案提供 24k mono PCM，客户端在 RTC 的本地播放器播放。SDK 本地混音不发布到对端；插话、手动打断和结束取消本地播放及网络请求。
- 前台电话分别取得云端问答、声音、录音和声纹许可。只读 SDK 麦克风回调保留最多 30 秒的内存段，并按 RTC round 上传为 16k mono WAV；长段不以截断音频证明整轮身份。静音、挂断与切账号清空缓冲。连续短段可累积为 5–15 秒样本。
- 共享 VoiceCall 上下文标记 transport=volcengine，不创建 LiveKit 房间或派发旧 Agent；复用声纹登记、本人/亲友分段、绿色姓名、仅本人原话的自动记忆和单人清晰样本复刻。未知或亲友不会自动写成本人。原音色、原录音和原声纹资料保留。
- 保活与答案/声纹状态分开，租约仍为 15 秒；短暂超时或 5xx 在 8 秒窗口内重试，失效/撤权/过期不能续租。后台识别循环与保活清理独立，原每分钟 timer 保留恢复职责。
- 自动整理记忆或更正导致回答失效，只退休该轮并停止旧音频，可在下一轮使用新资料；停止旧音频失败则关闭通话。服务端清理按用途版本隔离，并对同用途版本的外部控制使用 PostgreSQL advisory lock，避免旧实例将另一个版本的用途视为撤权，或重复迟到的 interrupt。

## 已执行的本地验证

- 全 Backend 在第一版恢复代码阶段：810 项收集，804 通过、6 跳过；后续后台处理/声纹/原语音回归 71 通过，最终新路线定向 22 通过，跨版本和来源更新定向 16 通过，独立许可重复撤销及功能恢复定向 14 通过。均保留实际日志，未将较早全量结果称为最后提交的全量重跑。
- 契约 48 项通过，v1 保持不变，v2 明确新增本人音色和采集字段；厂商密钥、音色 ID、声纹向量不进入移动端形状。
- iOS 通话定向 34 项通过，包含临时保活故障重试、独立保活不受答案轮询失败影响、撤权立即停止、持续故障有界结束、静默不误判未就绪、超长采集不冒充完整原音。2 项复刻/试听界面用例通过，包含照读确认、免打字及编辑后重新确认；Xcode 收集模拟器诊断曾超时，用例及 test 命令结果成功。最新原生补丁还验证了已收到核验答案可建立就绪状态，并以服务端 round 补齐采集，避免依赖缺失的 RTC 会话事件。
- SDK 的播放器抽象类未导出具体 ObjC class symbol；避免对其 Optional 进行 NSObject Equatable 比较后，Debug 链接与测试、Release 构建及签名核验通过。不是通过移除模拟器库或关闭签名绕过。

## 线上诊断与验证状态

用户原前台失败通话约 76 秒，结束在租约到期约 1.57 秒后；原生 RTC 音频错误为 0，提示不能只把故障归为麦克风。原客户端一次心跳异常即结束，新版已拆分保活与轮询并加入有界重试。

功能恢复的第一批线上合成验证使用既有 ios-synthetic-demo 隔离账号及系统合成声音，已成功从真实 WAV 经云端分段与声学模型登记本人参考；后续通话约 2 秒即终止，仍在租约期限内。对照不带采集/带采集均被结束。实例列表发现 046、047、048 同时 Running，旧 046 清理逻辑会将 v2 policy 视为变化。下线旧 046／047 后，相同不采集／采集对照各连续 10 次保活 HTTP 200。随后发布 049 并下线 048，实例读回只剩 1 个 Running。保留这批失败探针，不能把最初失败阶段记为通过。

StopVersionInstance 返回 UnauthorizedOperation 的详细原因是「当前运行模式不支持该操作」，最初误述为权限不足，已向本人更正。浏览器工具另明确报告 Mac 锁定；后改用云托管支持的旧发布版本下线流程，保留镜像和私有配置备份。当前版本与旧配置已分别留存，旧发布记录清理不删除服务、数据库、对象存储或镜像。

完整 API 流程与长租约验证在 CloudBase049／`ios-volcengine-parity-a6e36d1` 执行。清理时另修复重复撤销会将已删音色改回 delete_pending 的终态回退；相关 14 项通过，CloudBase050／`ios-volcengine-parity-178c912` 发布任务 2371289 完成且 service-info 读回一致；旧 049 下线后仅 1 个 Running 实例。本次未把 049 的完整合成流程记作 050 全量重跑。046／047／048／049 仅移除旧发布记录与运行实例；`IsDeleteServer=false`、`IsDeleteImage=false`，配置备份权限 0600，镜像保留。

隔离 ios-synthetic-demo 账号 + 系统合成 WAV 的真实服务验证通过：原音分段、声学登记与姓名匹配（1 个姓名）、自然样本复刻就绪、试听非零 PCM（290880 bytes）、本人模式 StartVoiceChat、已保存答案个人 PCM（237120 bytes）、第二轮 Twin 与独立保活。个人 PCM 请求到首包 0.868 秒，只是已保存答案取音频的时间，不是停说到出声。Twin 请求由 call 绑定鉴权的 CustomLLM 回调主动驱动，未声称覆盖原生 RTC 上行媒体或真人听感。

另一次无媒体真实 call 连续 71.11 秒内 34 次保活全部 HTTP 200；停止续租 20 秒后 status 404、durable ended=true、remote_stop_pending=false，验证期限和远端停止，没有放宽租约。源变更后的续聊与授权失效停止由本地定向回归覆盖，未将其描述为本次线上真人实验。

合成 QA 的临时许可已撤销，调用已结束、远端停止已清理；本轮合成资料和回答已清理；读回临时 call 未结束数、待远端停止数、有效临时许可数、剩余回答数均为 0，临时音色状态 deleted。针对该临时音色的供应商前缀查询确认远端残留为 0；没有将 delete_pending 冒充删除通过。真实账号音色和原录音未用于这些试验。真人手机的本人音色、姓名与约两分钟持续通话仍待本次安装后的确认。

## 证据

Backend `build/`：`volc-parity-deployment-20261016.json`、`volc-parity-final-deployment-20261016.json`、`volc-parity-generation-deployment-20261016.json`、`volc-parity-api-proof-20261016.json`、`volc-parity-watchdog-control-20261016.json`、`volc-lease-soak-20261016.json`、`volc-parity-cleanup-proof-20261016.json`、`volc-parity-deletion-deployment-20261016.json`、`volc-parity-final-pod-proof-20261016.json` 及 attempt 记录；测试日志分别为 `volc-parity-full-backend-20261016.log`、`volc-parity-worker-tests-20261016.log`、`volc-parity-final-backend-tests-20261016.log`、`volc-generation-tests-20261016.log`、`volc-parity-contracts-20261016.log`、`volc-parity-deletion-tests-20261016.log`。私有凭据、平台原始响应、配置备份和 QA 状态只在 ignored build/private，未写入镜像或 Git。

主工作区 `build/`：`volc-parity-ios-20261016.json`、`volc-research/ios-volc-parity-tests-20261016.log`、`volc-research/ios-volc-parity-ui-tests-20261016.log`、`volc-research/ios-volc-parity-release-20261016.log`。

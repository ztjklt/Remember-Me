# 整体审核后的首批修复

2026-10-16，Asia/Singapore。对应 [整体审核](PRODUCT_FUNCTIONAL_AUDIT_2026_10_16.md) 中的五项优先问题；[批准范围及接口语义](../architecture/voice-audit-remediation-2026-10-16.md)。

## 交付状态

完整源码已保存于 `codex/volcengine-modular-voice-20261016`，首批实现提交 `2e558d2`；随后修复本人模式助手未接入，版本来源 `d7165ce`。Backend 已发布 CloudBase052 / `ios-voice-connect-d7165ce`，0027 / 0028 已执行并读回，新默认声音及本人模式两轮合成测试通过。详见 [助手接入修复与实际交付](VOLCENGINE_ASSISTANT_ACCESS_FIX_2026_10_16.md)。

iOS **1.15.3 / 2026101608** 已签名构建、覆盖安装并成功启动，设备应用列表已读回新版本。安装前后 11 个录音路径及 metadata 一致，未卸载 App。旧音色保留、新验收状态为 pending，需要先试听并确认使用；手机实际通话听感仍待验证。

本人已说明暂时无法通话；本次不要求即时真人操作，未宣称原先无声／中断已通过真实通话验收。

- [签名安装包](</Users/jitian/Documents/ChatGPT/Remember Me/build/releases/RememberMe-1.15.3-2026101608.app.zip>)，配套 [版本与 SHA256 清单](</Users/jitian/Documents/ChatGPT/Remember Me/build/releases/RememberMe-1.15.3-2026101608.manifest.json>)。1.15.2 为未安装的中间产物。
- 当前开发描述文件有效至 2026-10-17 22:37:56（Asia/Singapore）；实际安装时检查并按需重新签名。
- 已发布 Backend 源码包：服务端维护工作树 ignored `build/voice-connect-backend-20261016.zip`，168 个 Git 来源文件；清单为 `build/voice-connect-backend-manifest-20261016.json`。沿用固定摘要的 045 运行镜像，无私有环境配置。旧 voice-audit 包保留作历史。
- PostgreSQL 迁移 SQL：`build/voice-audit-migrations-20261016.sql`；0027 删除重试调度、0028 音色验收均已事务执行和读回。

## 已修复

1. **远端删除队列堵塞。** 每轮取两个到期任务，持久保存尝试次数及下次时间，指数退避；CAS 抢占、租约和 fencing 阻止并发／过期 worker 覆盖。永久未知的创建继续对账，但不再挡住后续已知音色。迟到的已知创建会即时唤醒精确任务；源许可异常分支不会重新打开已完成的删除。
2. **RTC 重连立即挂断。** 短暂 disconnected / reconnecting / lost 进入固定八秒恢复期，暂停麦克风、样本缓存及播放。恢复后主动确认 Backend lease，才按用户静音选择恢复输入；重复事件不延长截止时间。结束、撤权、终态 failed 与旧会话回调不能恢复采集。被中断的旧回答不重播。
3. **资料不足时无回执。** 默认和本人音色仅朗读固定服务反馈；UNKNOWN.answer 始终被忽略。仍校验当前保存答案、轮次、来源有效性和许可；客户端处理等待结束、去重及下一轮提示清理。服务反馈不进入本人人物证据。
4. **音色本人验收及重做。** 新增独立 review / retry 接口，原 profile JSON 保持兼容。成功试听后可“像我，确认使用”，或“不像我”。拒绝立即关闭该音色的通话；重做仅停用该音色并清理复刻样本，保留原录音、记忆、声纹和独立 VOICE 许可。旧音色迁移为 pending，不伪造本人确认；新就绪音色不自动选用。
5. **源码与依赖基线。** 119 个 iOS 源码输入已纳入版本管理；普通 XcodeGen 项目已独立构建，硬件项目另用本地授权 SDK。固定火山 SDK、SPM pins 及安全同步工具一并保存。主目录落后的 Backend／AI Core、缺失契约和必要部署／QA 工具已同步；原有用户改动保留，运行配置、密钥、用户原音与 Vendor 二进制没有进入普通提交。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| 权威 Backend 全量 | 833 项：827 通过，6 跳过；跳过需要独立 PostgreSQL 测试库 |
| 主目录同步后的 Backend | 全量同样 827 通过、6 跳过；新 review／删除／火山功能定向 26 通过 |
| 主目录同步后的 AI Core | 296 通过 |
| iOS 全部单元测试 | 175 项：174 通过，1 跳过；缺少短时硬件 QA receipt |
| 新 review 定向复验 | 3 通过，包含旧音色确认不能应用到后续新音色 |
| iOS 界面 | 2 通过：就绪音色确认／重做入口、未试听不能确认，以及大字号默认通话入口 |
| 契约 | 50 通过；主目录同步后同样 50 通过 |
| 安全源码同步工具 | 9 通过，含路径、symlink、私有目录、变化检测和摘要 |
| 独立普通 iOS 工程 | 使用本机固定 SDK／SPM 缓存，Simulator 构建通过；Soundcore 使用手机回退 |
| 硬件版 Release | 1.15.3 构建通过，deep / strict 签名校验通过；已覆盖安装、启动并读回版本，11 个录音 metadata 一致 |
| 真人通话／实体硬件 | 本轮未验收实际听感；云端默认及本人模式两轮合成测试已通过 |

整合回归还发现并修复：试听时间在 SQLite 读取后缺少 UTC offset；验收布尔值默认类型转换与严格契约不一致；迟到创建后的立即删除及 terminal 状态回退。未把这些失败记录当作通过。

日志位于 ignored build：权威工作树 `product-audit-fixed-backend-final-20261016.log`、`product-audit-fixed-contracts-20261016.log`、`voice-deletion-late-result-tests-20261016.log`、`voice-audit-repro-ios-build-20261016.log`、`ios-source-sync-tests-20261016.log`；主目录 `product-audit-synchronized-ai-tests-20261016.log`、`product-audit-synchronized-backend-tests-20261016.log`、`product-audit-synchronized-backend-final-20261016.log`、`product-audit-synchronized-contracts-20261016.log`，以及 `volc-research/voice-audit-fixed-ios-tests-20261016.log`、`voice-audit-review-ui-tests-20261016.log`、`voice-audit-fixed-release-build-20261016.log`。

## 尚未交付的功能缺口

个人训练候选仍缺独立成对盲测、候选推理运行时及回滚，不会仅翻转 activation_allowed。完整动态访谈仍需疲劳、时间和信息增益规划；全量导出／注销需要资产清理状态机。Marker 的官方毫秒回调已确认存在，但尚未接入；Android 新 RTC 与完整 Legacy 不在本轮语音修复交付范围。这些不能由当前回归或源码同步推断为已完成。

后续配套发布完成后，仍需验证本人试听、姓名、插话、静音、噪声／多人、持续通话和挂断清理；可在本人可用时进行一次有针对性的真机检查。

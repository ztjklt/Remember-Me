# 通话音色选择修正

2026-10-16，Asia/Singapore。本人反馈“本人音色已就绪”，但实际通话没有使用本人音色。

## 定位与修改

通话页原先以局部 `@State useDefaultVoice = true` 初始化；已确认的本人音色在重新打开页面后也会选回默认声音。此前“已就绪”只依赖供应商 profile.ready，没有区分本人试听确认和本次通话选择。这是已确认的客户端缺陷；本轮未以真人听感证明复刻相似度，也未推断用户最近一次电话的服务端实际模式。

- 本人试听并确认的当前 profile 默认选用本人音色。用户主动切换默认声音时，将选择按 Actor／Subject 存储空间和 profile ID 保存；重开页面或 App 不重置选择。新 profile 必须独立确认，旧选择不能替它通过审核。
- 复刻完成但未经本人确认，显示“本人音色待试听确认”；已确认则显示“本人音色已确认”，并说明本次是否选择默认声音。
- 拨号按钮明确写“用本人音色通话”或“用默认声音通话”；通话中从实际返回并校验的 ticket 展示声音模式，不从复刻就绪状态推断。
- 统一主 App／实时活动扩展的版本变量，版本为 1.15.4 / 2026101609。Backend、共享 Contract 和现有试听确认／撤权规则不变。

## 实际验证与交付

- VoiceReviewTests、TwinVoiceCallTests、VolcengineVoiceTests：48 项通过。新增覆盖确认后默认选本人、显式默认选择重建后保留、换 profile 和撤销确认不沿用确认；通话票证模式与结束后清理也已检查。
- 两项原生 UI 测试通过：就绪但未确认的提示与默认通话入口；极大字号下拨号入口可达。它们使用隔离 fixture，不采集真人声音。
- Release 真机构建通过，主 App 与扩展的版本均核对为 1.15.4 / 2026101609，描述文件设备授权／有效期及 deep / strict 签名检查通过。
- 已从签名归档解包后覆盖安装到「黑幕」，设备应用列表读回 1.15.4。安装前后 11 个 m4a 的相对路径与完整 metadata 一致，未卸载或清空容器。
- 自动启动被手机锁屏拒绝（CoreDevice 10002 / Locked），需本人解锁后打开。没有把启动失败记为通过；本轮尚未验收本人试听或真实通话的音色相似度。

产物在 ignored `build/releases/RememberMe-1.15.4-2026101609.app.zip` 与同名 manifest；安全摘要 `build/volc-research/voice-selection-delivery-20261016.json`。测试、UI、Release、签名日志为该目录下 `voice-selection-*-20261016.log`；设备安装与录音 metadata 回执在 `build/private/voice-selection-*-20261016.*`，不提交私有原始回执。

## 后续：本人确认试听也像默认声音

本人进一步明确“试听也不像我”“还是系统默认的声音”。这使本轮问题扩展到复刻音色本身；前述选择修复不能视为本人音色相似度修复。

仅做当前本人空间的诊断：线上仅有一个未撤销、非默认的复刻 profile。数据库使用独立 clone ID；官方 query_voice 返回 OK，target_model 与当前 cosyvoice-v3-flash 一致。认证后的火山作用域 profile 与该 profile 完全相同，试听返回 344684-byte、24 kHz 单声道 WAV。检查的服务端路径使用该 profile 的 provider_voice_id，没有发现把该试听改用默认音色 ID 的代码证据。这不证明手机听感像本人，也不将本人的反馈解释为误听。

在核对独立 VOICE 许可仍有效后，只读取当前 profile 已保存的参考音频作本机诊断，没有从其他录音另取样、创建新音色、更新供应商模型或删除旧样本。参考音频为 8.406 秒、44.1 kHz 单声道 AAC，16 kHz 解码后 RMS 0.00854（约 -41.4 dBFS），无削波。它短于供应商推荐的 10–20 秒，电平偏低；这些是质量风险，尚不能据此认定相似度差的原因。[官方音频要求](https://www.alibabacloud.com/help/zh/model-studio/voice-cloning-user-guide)也将至少五秒清晰连续人声与推荐总时长区分。

现有声学模型对参考／合成试听的诊断相似度不用于本人验收，也不推翻本人“不像我”的评价。尚需本人确认参考样本是否确实为自己的声音；如原始样本正确，后续应以更清晰、自然的本人材料重做并对照试听，不能只改 ready 标志。

已通过与该 profile 完全匹配的本人账号及正式 `POST .../volcengine/profile/review` 提交本人的明确否定反馈，HTTP 200、status=rejected。没有点击重做、删除录音／样本、撤销独立许可或把音色自动标为 accepted。原音与复刻参考继续保留。原始私密回执、音频与本机诊断只在 ignored `build/private/voice-*-20261016.*`；不提交身份、凭据、声纹向量或音频。

## 本人确认原声后：音量校正对照候选

本人试听原始参考后明确回复“是的”，确认该原声属于本人。本轮以原始参考的副本生成一次对照复刻，不改原文件、不变调、不变速、不拼接、不延长样本。线性增益 +15.348 dB，时长差 0，解码波形相关系数 0.999993，无削波；原始参考的低电平问题已在这个副本中校正，但不据此宣称音色相似度改善。

沿用同一百炼服务和 cosyvoice-v3-flash，按[官方复刻参数](https://www.alibabacloud.com/help/en/model-studio/voice-clone-design-http-api)关闭声音预处理、开启音量归一化。经本人账号认证、当前 profile、独立 VOICE 许可、Subject 所有权、无未结束本人通话检查后，建立独立 pending 候选。候选与旧 profile 属于同一 Actor／Subject 和原 VOICE 许可；参考文字沿用本人已确认的旧样本，副本保存在该 Subject 的独立对象路径。旧 rejected 音色及原样本保留，未复用 QA 账号、未覆盖旧 provider ID、未伪造本人确认。原始／副本摘要与新旧 profile 对应关系仅保存在 ignored 私密状态文件。

新候选通过现有有期限样本票据完成取样和供应商复刻；已持久保存 provider ID，并由正式 profile 查询接口核对目标模型、转为 ready。新 profile 的正式试听接口返回 333164-byte、24 kHz 单声道 WAV，6.94 秒，非静音、无削波。正式 review 仍为 pending，该候选通话数为 0。当前客户端刷新后可试听候选，只有本人另行确认才可用于通话；本轮未替本人接受音色。

私密运维工具在写入供应商结果后遇到 CLI UPDATE Rows=null 的解析异常；通过独立只读 SQL 核对已持久写入的 provider 结果后恢复，没有再次创建供应商音色。已修正本地工具的空 Rows 处理。没有把该异常记为成功的自动化检查。

安全摘要：`build/volc-research/voice-normalized-candidate-proof-20261016.json`。本机对照试听：`build/private/voice-normalized-preview-20261016.wav`。本轮没有改动或部署 Backend 源码、共享 Contract、模型配置或 iOS 安装包；属于当前本人空间的一次有记录的复刻对照操作。**是否像本人仍待本人试听评价，尚未修复／验收音色相似度。**

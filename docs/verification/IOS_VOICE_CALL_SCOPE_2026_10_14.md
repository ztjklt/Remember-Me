# 语音新通话上下文隔离与晚到答案修复

2026-10-14，Asia/Singapore。落实已批准计划中的「断线重开创建新通话，不默默继承上一通话上下文」和「过期轮次不得覆盖／重新播放」。不启动新增花园保护／多人／托付接口，本修复不需要新的客户端必填字段、Contract或迁移。

## 复现证据与行为

检查当前共享回答代码发现：VoiceCall重新创建时previous_answer_id为空，但调用文字共用回答后，全局旧聊天检索仍会把以前的通话／文字消息带进生成。修复前两个定向用例均失败，实际模型输入的conversation_recall含旧消息；不是仅凭“新call_id”推断隔离成功。

另一个修复前用例证明同一Worker turn_id在不同call复用时，全局request_id去重会返回上一call的answer_id。Worker正常生成随机编号，复用风险低，但边界必须在服务端保证。三个修复前失败保留于Backend工作区 build/voice-new-call-context-before-20261014.log 和 voice-cross-call-turn-before-20261014.log。

最终实现：

- 文字Twin的公开入口继续检索当前Actor／Subject的旧聊天，开关与数据保留不变。
- 语音使用服务端当前call的答案链，并把历史检索候选、索引快照和发布时复核限制在该conversation_id。新call首次生成新的conversation_id，因此没有旧call／旧文字上下文；当前通话超过20轮完整窗口时，仍可检索该通话较早的消息，不以“关闭所有历史检索”替代完整需求。
- 原来获准的Life Episode、记忆、人物理解及确认表达资料继续检索，来源／推测／UNKNOWN规则保留；通话不自动成为人物证据。
- Worker内部请求去重编号由call_id和turn_id共同派生为64字节范围内的不透明标识，不同call相同turn_id不复用旧答案。公有turn事件与请求形状不变，文字客户端原request_id语义不变。
- 在生成／可选表达和保存的短发布事务中检查当前call、登录、用途、许可及active_turn。挂断、过期、撤权或新轮接管后，旧结果不能保存为TwinAnswer，因而不能在后续上下文或声音播放中重新出现。
- 模型请求已经派出时，供应商工作可能仍在原有超时内结束；本修复保证停止后续发布／保存／播放，不宣称测量过远端计算即时停止。Worker现有异步任务取消与本机停播保留。

AI提示只澄清旧检索消息可能来自同一会话较早部分或另一会话，不能仅凭historical_recall标签声称另一通电话或刚才。没有更换模型／声音供应商，没有更新本人画像、删除原文／原音或复制授权。

## 定向与兼容检查

Backend当前通话／文字会话／旧聊天记忆／来源上下文共60项通过，包含6个新增不同场景：新call隔离、旧文字不进入新语音、相同turn跨call不复用答案、当前call超过20轮仍检索自己的旧消息、挂断期间回答返回不保存、新轮接管后旧回答不保存。当前call较早消息测试使用24条模拟已保存消息和Fake模型，仅证明实际API／数据库过滤及保存链，不代替25轮真人通话。

Backend人物／来源／故事／旧Voice兼容51项通过；AI Core全套296项通过；Contracts25项通过。Backend／AI各有2个已有依赖弃用警告。只统计本轮这些432个不同用例，不与先前Worker60、Native、云端样本混加为新总数。

一个新测试先误断言不存在的history_context_truncated，实际字段为context_truncated；修正后全套通过。发布包初次预检把平台字符串FlowRatio当整数，并遗漏旧归档的虚拟.dockerignore，分别在上传前停止；修正后构建包完成，不属于线上失败。

日志：build/voice-call-scope-regression-final2-20261014.log、voice-call-scope-compatible-20261014.log、voice-call-scope-ai-20261014.log；主工作区 build/voice-call-scope-contracts-20261014.log。数据归属、历史开关、来源有效性、Subject／Actor和Voice独立授权继续适用。

## 发布状态

业务源码3719a0b已推送codex/twin-chat-memory，基于原54856ef服务和已发布的0974506 Worker诊断。源包白名单168文件，SHA256 c4b62fa6ae0a291ed158a7cc6b44a4fdaeebb85ef9b37ad4b0d9ae31d0548876；逐成员0644和逐文件运行密钥扫描通过。复用原CloudBase025镜像依赖、模型缓存、配置和数据，仅更新源码；诊断继续关闭。

CloudBase026 / task2352931 的CreateVersion、ReleaseVersion均finished；实际HTTPS service-info为ios-voice-call-scope-3719a0b，ready HTTP200，database／object_store均ok。保留原Worker CA_tPrXyGHActp3 / JYedLVmAT6pV，诊断关闭。

发布后当前Backend＋当前Cloud Worker的完整合成场景通过：监听8.027秒；三轮question→answer约9.000、2.780、2.324秒；手动打断后静默65.001秒，97.622秒注入第三段，第三question101.096秒、answer103.420秒并有新音频。自动打断旧轮重启false，自动空档及手动打断后宽限1.2秒后的非零音频帧均0；397输入帧全送完、capture错误0、捕获216个非零输出帧。第二个保存答案parent指向第一答案。结束／VOICE撤销200、合成答案清理、持久化结束及个人profile仍missing均通过。报告 build/voice-call-scope-full-cloud-20261014.json；不是手机停说→可听时延或真人克隆。

真实Backend API边界另用同一个QA空间验证：先保存测试文字；两个新call用相同turn_id提出同样问题，各自HTTP200、parent为空、历史召回数0、answer_id不同；随后普通文字查询仍可找回该测试原消息，召回数6。清理两通话、测试消息及含其来源的摘要，撤销本次VOICE200，个人profile仍missing。报告 build/voice-call-scope-api-proof-retry-20261014.json；该检查未连接RTC，不另算完整语音场景。

第一次API边界检查的新call和相同turn隔离均通过，但“以前聊过什么颜色书签”的概括问句进入旧检索的广泛回顾路径，在12条结果中没有新测试句，使最终断言失败；未改产品检索代码，改为具体来源问句“之前说过偏好橙色书签吗”后上述复验通过。第一次结果保留于 build/voice-call-scope-api-proof-20261014.json，资源清理亦全部完成，不能删去失败或称任意概括问题都命中同一条记录。

本轮无Native改动，保留已安装1.8.3和原数据；本人音色、自然交互及耳机仍需本人验收。首次模型502根因仍未证实，不从这次边界修复和成功场景推断其永久消失。

发布前与全部QA清理后独立SQL计数一致：migration head=0020_chat_memory、Episode=5、Memory=9；报告 build/voice-call-scope-data-preservation-20261014.json。本次没有迁移、删除原记忆或替用户确认人物材料／音色。受保护花园、多视角、托付和设备／唤醒仍按已形成的提案与条件推进，不把当前自动验证当作这些功能完成。

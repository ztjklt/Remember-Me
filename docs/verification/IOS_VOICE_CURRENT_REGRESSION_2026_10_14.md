# 当前版本完整语音复测与失败阶段诊断

2026-10-14，Asia/Singapore。继续执行已批准的前台语音计划；花园保护／多人／托付的新 Contract 批准仍待用户明确回复。本轮不把自动 goal 续跑当作批准。

## 为什么再次复测

此前首批完整场景通过后，另一个授权任务上线了 default 声音和第一人称 Twin；其云端记录只有单轮RTC。本轮以当前公开 release `ios-first-person-54856ef`、现有 CloudBase 服务、现有 LiveKit Agent `CA_tPrXyGHActp3` 复测完整场景。

新增可重用 `tools/verification/public_voice_scenario.py`，使用既有白名单 `ios-synthetic-demo` QA 账号及合成PCM。公开 default 模式不需要克隆样本；本次不修改个人Profile、不注册本人声音。仅临时授予QA的VOICE，复用QA既有CLOUD_TWIN；结束后撤销本次VOICE并按Actor／Subject及本次turn request_id清理合成答案。

## 首次云端失败，不能算通过

首次：RTC连通、Worker就绪21.741秒、第一问25.509秒、第一答28.378秒并有音频；29.657秒注入第二段，第二个question事件34.322秒证明识别已经到达，37.468秒收到error。失败在第二轮答案请求，尚未到手动打断／65秒／第三轮阶段，不能以累计收音或第一轮声音宣称完整场景成功。

按该测试call限定的服务日志，第一 `/answers` 为200、第二为502，授权轮询仍为200。清理后authorize为404符合已结束状态，不作识别失败解释。相同时窗只有一条模型复核记录：supported／attribution／time_consistent／mode_correct=true，complete=false、unsupported_claim_count=1，但没有跨服务trace绑定，不能从相邻时间就认定唯一根因。

同样的两句合成内容通过公开文字会话接口对照，两轮均200／CONVERSATION，专用测试回答已清理。因此尚未证明是稳定的上下文实现故障，不能通过放宽来源／人物／模型校验把失败包装成通过。

首轮通话结束与VOICE撤销均200，持久化ended检查通过，本次合成答案已清理，个人profile仍missing。报告位于Backend工作区：build/public-voice-full-scenario-20261014.json；脱敏HTTP证明、文字对照和临近复核计数分别见 public-voice-scoped-http-proof-20261014.json、public-voice-context-diagnosis-20261014.json、public-voice-review-diagnosis-20261014.json。

日志读取使用官方 [SearchClsLog](https://cloud.tencent.com/document/api/1243/126754) 和 [运行日志接口](https://cloud.tencent.com/document/api/1243/126757)。首次CLS请求缺少必填Limit而失败，补齐后成功；部署运行日志只返回6条部署阶段日志，不能据此声称业务无错误。原始控制面输出仅在0600私人目录，工具及交付报告只输出状态、计数和复核布尔值，没有转写、原音、凭据或实际Actor／Subject。

## 内部诊断和本机对照

Worker增加默认关闭的失败阶段：twin_answer.failed、publish_answer.failed、playout.failed。只记录数字call关联号、轮次、耗时、HTTP status及受控failure_kind编号；编号1=AI_SCHEMA_INVALID、2=EVIDENCE_INVALID、3=AI_AUTH_FAILED、4=SOURCE_CHANGED、5=TWIN_FAILED、6=TWIN_UNAVAILABLE、7=NOT_FOUND、8=DATABASE_UNAVAILABLE，0=未知。不是新增客户端字段，不记录异常正文或完整响应。原有错误事件、事实校验及结束逻辑不变。

Worker现有回归和新诊断／QA票据校验共60项通过，build/public-voice-worker-diagnostic-tests-final-20261014.log。新增用例包括诊断开／关、非对象错误响应不会影响原错误提示、无问题／响应／凭据泄漏，以及篡改签名、room、participant、call或扩大媒体权限时拒绝测试票据。

本机controller第一次准备时未加载第二份既有Worker配置文件，尚未启动或创建通话即失败；补齐后第一次staging又因新测试调度辅助函数替换agents时丢失call metadata，在监听门槛前超时。本次均为测试工具问题，不算产品故障或成功。已将辅助函数改为只替换agentName，验证签名、call／room／participant绑定，保留metadata、权限、expiry全部其他字段；对应测试补齐真实metadata结构。首次staging通话与许可清理均200、Worker已停止。

修正后的本机Worker／真实Cloud媒体／当前Backend完整对照通过：三次独立question／answer及新音频，自动插话后旧轮不重启、宽限1.2秒后的中间音频帧0；手动打断由服务端active_turn清空确认，65.001秒静默期间宽限后音频帧0。第三段出现RTC／Worker接收burst、ASR发送burst、第三次识别final、Twin回答、SDK首帧及RTC非零输出。各阶段编号独立，不能仅凭编号或计数相同认定同一语句。

397个合成输入帧全部送完，capture错误0；第二个保存答案的parent确实指向第一答案。结束／撤销均200、合成答案清理和持久化结束检查通过，本机Worker实际停止。报告 build/public-default-staging-control-retry-20261014.json。该本机对照不是Cloud Worker发布验收。

## 原云端重试结果

保持首个失败报告不覆盖，原Cloud Agent完整重试通过：就绪7.518秒；三次question→answer约3.075、3.346、3.222秒。65.001秒静默后于92.004秒注入第三段，第三question95.464秒、answer98.686秒，实际捕获后续非零音频。它们不是用户手机停说到可听声音的时延。

自动插话后旧轮重启false、宽限后空档非零音频帧0；手动打断后至第三段注入的宽限后音频帧0。397个合成输入帧全送、capture错误0、捕获216个非零输出帧。三个独立问题／答案／音频通过，第二答案保存链检查通过；结束／撤销200，合成答案已清理、call已持久化结束、个人profile仍missing。报告 build/public-voice-full-scenario-retry-20261014.json。

本次成功不证明首次502或10月13日间歇识别故障永久修复。实际真人自然交互、本人音色及耳机操作仍待本人；不把默认声音、合成问答或成功重试替代它们。

## 源码与发布

0974506 已推送 codex/twin-chat-memory，含数字失败诊断、公开default完整回归工具和票据校验。Backend／AI Core业务未修改、无迁移／Contract变更，原服务、模型和声音供应商保留。Worker诊断补丁已向原Agent发布，明确设置 REMEMBER_REALTIME_NETWORK_DIAGNOSTICS=0，deploy CLI exit 0；独立status CLI exit 0，仍为CA_tPrXyGHActp3，版本JYedLVmAT6pV。

发布后新Worker真实RTC单轮检查通过：监听5.175秒、question8.761秒、CONVERSATION answer／speaking12.386秒，捕获6帧非零输出；结束和本次VOICE撤销均200，合成回答已按编号和空间清理、个人profile仍missing。报告 build/post-voice-diagnostic-worker-smoke-20261014.json。发布后只做了单轮检查，完整三轮结果分别来自发布前原Cloud Agent和同源码本机staging；没有把单轮重复计成一次新的完整场景。

本轮没有Native业务变更或重新安装，保留iOS1.8.3及原数据。确定修正的是测试调度metadata保留问题；增加了可定位的内部错误诊断和当前版本完整回归，尚未证明首次模型／答案502的唯一根因或永久修复。本人演示、设备资料和新增保护／多人／托付批准仍是全目标的未完成项。

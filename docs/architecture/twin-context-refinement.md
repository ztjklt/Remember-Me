# 第二轮续作：回答前保留证据上下文

基线 `87d88a4`；用户已批准第二轮计划及继续优化。只在本地集成分支验证，不部署 ECS。

## 问题与兼容提案

实际月度测试中出现转述对象不清、把早先待答当成永远未知、未经确认合并不同字形。后端已有来源录音、讲述时间和文字位置，但 Twin 内部请求丢弃了这些字段；关键词排序进一步打散来源上下文。

内部 TwinEvidence 可选增加 `episode_id`、`recorded_at`、`span_start`、`span_end`、`temporal_context`。旧调用可不传；公开手机 TwinOutput、数据库与六类记忆枚举不变。AI 先接收扩展，后端随后发送；独立部署时不能让旧的 extra=forbid AI 接收新字段。

只为已通过有效性与权限过滤的证据增加元数据，绝不重新读取整段文字作为补充上下文。位置是核对文字的字符位置，不是音频时间；书面补充没有口述位置。讲述日期不代表事件日期，较新的讲述不自动覆盖较旧事实。模型同样接收按录音及文字顺序组织的来源编号，排序只帮助查找。

## 实施与验证

1. 后端通过实际接口测试上下文、删除、授权过滤；AI 验证旧请求兼容、分组和顺序、边界与来源映射。
2. 复用原始失败问题，实际微信模型小批复测，再根据实测决定回答结构调整；保留旧答案与失败历史，不使用参考答案替换输入。
3. 运行确定性回归和真实开发问答，按语义逐项检查，不把 HTTP 成功当正确。
4. 最终独立审查；记录剩余缺口，保留本地分支。

## 执行账本

Pre-flight: 后端新增可选证据元数据 → AI 的 strict 输入需先扩展；公开客户端无需迁移。现有叙事来源指纹不能因新增传输元数据全部失效，因此仅在 Twin 边界构造扩展。

Ruling: 先修复证据组织再决定是否改变生成协议 — 避免根因未解决就追加模型循环；代价是仍需真实语义验收，元数据不会自动保证理解正确。

- Task 1: verified targeted — 后端15项、AI45项针对性回归通过；后续增加书面补充与错误元数据测试。
- Task 2: development checks complete / quality gate open — v8七问3返回4失败；逐项v1七问4返回3失败；v2完整60问49返回11失败。v3仅针对3问复测，2返回1失败。保留全部失败，不合并为一次成功率。
- Task 3: verified locally — 后端428通过/3跳过、AI233通过、Android41单元测试与APK构建通过；实际HTTP模拟器大字故事跳转、返回和原音通过。详细记录见下一文档。

Ruling: 增加开关控制的逐项问答协议 — 实测证明单补元数据不足；逐项回答、逐项引用、原字形锚点校验，并用第二次模型调用审查全部要点（包括原话路由）。旧协议仍兼容，默认不切换，独立工作台先实测。代价是第二次审查仍可能误判，需人工性质的逐项语义核对。

该协议只发送完整有效来源及已审核理解，不再发送未审核记忆摘要作为附加事实。输出仍是既有TwinOutput；单项原话保持200字符上限，组合回答使用既有500字符公共上限。confidence暂为协议固定0.8或未知0，未做概率校准，不作为人格或准确率分数。

Ruling: 调试只记录调用元数据，关闭完整材料日志 — “虚构”命名不能证明数据库没有个人材料；代价是今后诊断某一生成问题需要另行受控采集，不能靠常驻完整正文日志。

## 最终独立审查与一次修复

独立审查列出3项Important，均接受；没有Critical。仅一次修复，不安排重复审查。测试先复现7个失败，再修复，相关24项全部通过，AI全量233项通过。

- Final: fixed 原话复核看到空计划而非用户实际文字 — `test_review_receives_materialized_original_and_final_visible_answer`、`test_original_model_text_cannot_differ_from_what_will_be_reviewed` RED→GREEN。复核现在接收程序复制的原文和最终成文，不接受模型给ORIGINAL另写内容。
- Final: fixed 组合回答中第一人称原话失去引用标记 — `test_original_in_mixed_generated_response_remains_explicitly_quoted` 与第一人称回归 RED→GREEN。直接原话保留ORIGINAL；混合回答中的原话明确引用；常见未引用第一人称生成被拒绝。语言守卫不证明语义准确。
- Final: fixed 本地跟踪器只凭协议名便记录正文 — `test_diagnostic_trace_never_records_private_material_or_exception_text` RED→GREEN。新跟踪仅含提示词版本/哈希、时间、模型与状态，标准供应商日志保留usage；旧虚构实验日志留在忽略目录，不新增个人材料日志。
- Final: fixed 实跑发现未知原因却标SIMULATION — 增加 `mode_correct` 强制复核项，`test_evidence_about_an_unanswered_question_is_not_a_known_answer` RED→GREEN。v3旧工作本读者题正确UNKNOWN；消防员手机静音题仍因姓名证据不符失败，未宣称该题验收。
- Final: minor (deferred): 内部元数据允许不同UTC偏移，分组使用ISO字符串排序；本后端输出统一UTC，当前调用无此差异。以后接入其他内部调用者时应按时间点排序并补跨偏移测试。

手机截图补充：Compose空闲不代表原生Dialog淡入结束。截图等待原生窗口空闲后再采集，避免把过渡帧误判为常驻透明度问题；长文Surface也显式固定不透明。200%字号的实际故事与原音操作通过。临时界面验证观察已撤回，模拟器字体恢复100%，测试凭据配置已删除。

验收结果：[第二轮继续优化记录](../agent-loop/ROUND_TWO_CONTEXT_ACCEPTANCE_2026-10-09.md)。工作区与实验保留；语义门槛未通过，默认不启用新协议，不部署、不推送。

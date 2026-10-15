# 语音快速模式增量

依据用户本轮批准：保留原审阅基线，增加省去阻塞式大模型审阅的快速版本；之后再比较首句流式版本。权限、来源、纠正与版本复核继续执行。

- `/voice-capabilities` 增加 `response_speeds`，默认仅 `reviewed`。服务端明确启用后，对已有语音测试账号返回 `reviewed, fast`。
- 创建会话可选 `response_speed=reviewed|fast`，缺省仍为 reviewed。校准报告只使用 reviewed，未知值拒绝。
- 私有 AI 路由增加 `/twin/voice-fast`、`/persona/voice-fast`，要求 voice_response；结构和证据校验后返回结果，不执行独立语义审阅，不伪造审阅通过。
- 快速模式结果记录 `semantic_review=skipped`；人物回答不输出未评估的 coverage / omitted_points。仅用于运行诊断及结果记录，不给日常页面增加说明小字。
- 手机开始通话时可以选择标准或快速。旧服务器不支持快速时明确提示更新，不能静默降级并将基线当成快速结果。
- `ready` 和 `answer_ready` 携带实际模式；现有事件兼容。回答仍在短事务中完成来源复核与保存后才播放。
- 本批快速模式仍等待完整、合法的模型答案。不得称为自由 Twin 逐句生成；来源编号流实验保持单独标记。

不新增数据库迁移，保持原测试账号白名单、供应商、TLS、注册及分享规则。发布需记录具体版本及回退目录，延迟以手机输入结束至 AudioTrack 起播为准，服务端首块另列。

# Twin 本人视角发布与验证

2026-10-14，Asia/Singapore。Product / Integration Owner 直接要求 Twin 自称用户本人，依据录音提炼的内容回应。语义授权和边界见 docs/architecture/twin-first-person-proposal.md。

## 行为

Twin 以被建模的录音本人说“我”，有可定位的本人姓名来源时可自称该姓名。无姓名来源时简短回答“我是你在这里的数字版本”。普通身份问题不主动扩展身体、意识等说明；用户明确问到这些问题时如实回答。录音中他人的经历仍归属于他人。

个人事实、偏好与通常选择由有效核对录音及确认资料支持，表达范例只用于语气。来源不足时用第一人称承认无法确认，不把未提及的事实推成否定。原话逐字复制、来源、权限、SIMULATION / ORIGINAL / CONVERSATION / UNKNOWN 类型均保留。实时语音直接读核对后的回答，不再机械加“根据现有记录推测”前缀；已有界面标签保留。

派生回答基准升级为 t8p1，旧回答不作为新版有效人格依据，原消息和录音不删除。没有公开 JSON 字段或迁移变更，没有更换模型、声音供应商、Worker 或 Android ECS。

## 本地验证

AI Core 全套 296 项通过，两个上游弃用警告；Backend 针对实时声音、聊天、来源上下文和长期聊天记忆 54 项通过，两个上游弃用警告。新增后端用例验证旧 provider UNKNOWN 文字最终被统一成第一人称且保存内容一致。首次用例误用了内部 evidence_ids 字段而非公开 evidence，修正断言后通过。报告 build/twin-first-person-ai-final.log、build/twin-first-person-backend.log。

真实模型以虚构林禾、喝茶不加糖、同事父亲的职业和赶时间先做关键项作为合成资料，身份、偏好、人物归属、条件选择、表达五项检查通过。首轮模型将“未说父亲职业”误推成父亲没做该工作，并补了额外惯常动作；据此加强生成与复核规则，复验通过。此结果不是实际用户相似度评估，也没有上传或确认真人录音。

## 云端验证

代码提交 05241b7、54856ef 已推送 codex/twin-chat-memory。首版 CloudRun024 / task 2352813 已完成 CreateVersion、ReleaseVersion；实际 release 为 ios-first-person-05241b7。真实默认声音 RTC 单轮通过：获得 ticket、连接、监听、问答及 8 帧非零合成音频，结束和新增 VOICE 撤销均 HTTP 200，专用测试回答按 answer_id + Actor / Subject 删除，个人音色仍 missing。报告 build/first-person-voice-live-proof.json。

首版线上身份问答过长，UNKNOWN 又被 Backend 旧文案覆盖；后续修正普通身份简洁性及两个层次的 UNKNOWN 文字。修正版归档白名单 168 文件，全部 0644，解压逐文件密钥检查通过，SHA256 0e78f5aa2fe191c63e5e72af750c0ab6c09c8548db68b947c508c7a26f3cd8d4。CloudRun 后续任务 2352819 已提交，最终上线与问答验证待实际结果补记。

本轮没有 Native 变更，沿用已安装的 iOS 1.8.2 / 2026101405，不重复安装或声称新增真机验收。所有云端探针限定独立合成 QA，结果不等于本人音色克隆或真人复刻完成。

修正版 CloudRun025 / task 2352819 CreateVersion、ReleaseVersion 均 finished。真实 HTTPS service-info 为 ios-first-person-54856ef。正常 Twin API 的身份和未知两问通过，source_version 为 t8p1，身份回复简洁且没有未问的身体／意识说明，UNKNOWN 为第一人称；专用测试两条消息已精确清理。报告 build/first-person-live-proof.json。最终线上身份句为“我是你在这里的数字版本，会按你留下的录音和记忆来回应。”，未知句为“这件事，我还没有足够的记录可以确认。”；本轮没有将该合成测试账号的资料或回答写入真人画像。

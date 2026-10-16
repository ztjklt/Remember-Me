# iOS 孪生连续会话验证

日期：2026-10-13。本人授权连续聊天、承接前文并通过记忆和核对逐渐贴近用户。接口边界及授权在 [会话提案](../architecture/twin-conversation-contract-proposal.md)。Android 原请求继续兼容，部署只针对独立 remember-me-ios CloudBase。

后端源代码在 codex/ios-cloudbase-backend 的 7fa6712（会话与文字记忆）和 78574ea（会话优先级修正）；共享 v0.5 保留 v0.1–v0.4。加入同 actor / subject 的服务端链、请求幂等、20 轮 / 24000 字窗口与失效回答过滤。新增明确确认的本人文字保存，IOS_TEXT 的原音为空，不会被原音端点或校准冒充录音和人格预测。

本地 Backend 完整回归 525 passed / 6 skipped；AI Core 完整回归 291 passed，既有上游弃用提醒两条；Contracts 18 项通过。真实官方 DeepSeek 本地三轮合成测试通过，第三轮正确回忆两小时空闲、安静及步行要求；不是本人相似度测试。测试凭据与完整合成输出只保存在 ignored private 目录，发布包经过凭据扫描。

CloudBase 0017 -> 0018 使用 Alembic 生成的 PostgreSQL SQL，事务内校验当前 head。升级前后录音 / Episode 3、记忆 7，没有删除或替换原数据。最终 remember-ios-api-008 / ios-cloudbase-78574ea 已完成远端构建及 release task，100% 流量已切换。实际 /ready 200，database / object_store 均为 ok；源码镜像 digest 为 sha256:39166db0e3d33660629499ae0ed76cba23658a0c2432fa67f1c2bde22b49da6b。

iOS 27 模拟器最终验收 43 项通过（ECSConnectionTests 27、PersonReviewTests 15、连续聊天与文字确认界面 1）。截图已逐张检查：左右气泡、输入栏、选择正确本人消息、确认用途和无有效连接禁止写入均符合预期。中途两个不完整测试报告在测试调度停滞后清理，重启测试模拟器后生成独立完整通过报告；没有把中途未完成运行计为成功。签名真机构建成功，实际 App 包 1.5.0 / 2026101308。按本人“先不急着用”的指示，未安装 iPhone，未宣称完成真人真机连续聊天或人格相似度验收。

首次云端 probe 虽通过接口与存储检查，实际回答却把建议请求答成旧录音摘要，且对“偏好”与“喜欢”作不必要的字面争执。这是语义失败，不计为对话通过。已将连续会话生成和复核使用独立 conversation-v2 提示词，保留旧单轮证据提示词。修正后真实官方 DeepSeek 本地三轮测试包含无关旧录音，仍正确回顾橙色 / 九十分钟，并给出30+40+20分钟安排；最终云端三轮也通过：第一轮记录当前条件，第二轮回忆橙色书签及九十分钟，第三轮承接“这个时间”给出30+40+20分钟安排，没有用旧录音摘要替代建议。恢复读取保持 conversation_id；同 request_id 重试返回同 answer_id，未登录读取拒绝；开始新聊天 context_turn_count 为0。明确保存原始本人 question 后，新聊天检索回该 IOS_TEXT 的本人文字来源，has_audio=false，原音请求404。人物整理任务只生成 pending 候选，没有自动确认。

连续聊天窗口有明确上限。新话题、多样表达、长期画像相似度仍需要用户实际使用和本人新问题评审；上述合成小测试不证明所有语境准确或人格相似度已经提高。

## 后续真机安装

2026-10-13 本人随后授权“现在可以尝试安装了，就装在之前那个 app 里面”。已通过 devicectl 在 iPhone 15 Pro Max「黑幕」覆盖安装同一 bundle me.remember.personal.ios，原安装版本1.3.2 / 2026101305，新版本1.5.0 / 2026101308。安装后重新读取设备应用列表确认版本，并成功启动。没有卸载旧App或创建新bundle；未将安装／启动视为本人真机连续聊天或录音闭环验收。

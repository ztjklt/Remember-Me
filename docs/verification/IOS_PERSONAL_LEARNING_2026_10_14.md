# iOS 共享通话记忆、个人训练与本人一致性验证（2026-10-14）

## 当前交付

- Backend 已提交并推送 `25b8e81`，发布为 **CloudBase034 / `ios-twin-continuity-25b8e81`**；`/api/v1/service-info` 与 `/ready` 均200。旧聊天主题检索先在 CloudBase032 / `55b3970` 验证通过，后续补丁只恢复暂停后的撤权入口。
- iOS **1.9.0 / 2026101410** Release 签名构建及 codesign 验证通过；「黑幕」未连接，尚未安装。入口为 **孪生 → 复刻验证** 或加号中的个人模型训练与复刻验证。
- 只读核对本人账号：1 段已核对且 ready 的录音，0 次完成校准。没有替本人创建训练许可、训练真人资料、回答验证题或评价相似度。

## 行为与实际边界

开启旧聊天记忆时，新电话首轮优先带入同 Actor / Subject 最近一段会话末尾最多6条；每通电话保持自己的 call_id、parent chain、turn 去重和结束状态。当前电话近期窗口为20轮，更早的电话及文字记录按相关性补入，单次历史补充总预算为12条／10,000字。带具体主题、人名、日期的问题按相关性找原文，纯粹回顾全部聊天才采用跨时期覆盖；不能宣称全历史原文都放进每次模型上下文。关闭／清除／撤权和来源失效继续生效，助手话语不会自动变成人物事实。

个人模型使用单独 MODEL_TRAINING 许可。本人开启后，指定 Mac 的训练器自动检查材料并领取任务；原来源组固定分开 train / validation / test，重复原文跨测试划分会阻止训练。默认最低 40 个已核对样本、10 个原来源组，并分别满足 24 / 6 / 6 个训练／验证／测试样本。达标也不代表人格已经复刻。

Mac 已安装 LaunchAgent `me.remember.personal-training`，只读核对为 running，线上 `trainer_available=true`。本机出站领取任务，不向公网开放训练端口；Mac 关机／离线时训练暂停，手机原云端通话继续。关闭训练会停用并清理候选；仍有效的独立训练许可可在重开页面后找到并撤销，查找许可不会自动重新启用训练。已授权模型和运行时存放在当前后端 worktree 的 ignored 本机目录，不能归档这份仍被常驻 Worker 使用的 worktree。

MLX LoRA 在本机真实更新 Qwen3-0.6B 权重适配器。虚构语料 smoke 实跑 12 个 optimizer steps，360,448 个可训练参数产生非零变化（L2 1.703568），生成真实 safetensors，峰值约 500 MB。独立损失下降证明管线可训练，不证明更像本人。原始证明在 ignored 私有目录，安全日志为后端 worktree 的 `build/personal-training-smoke.log`。

当前手机推理仍使用原云端 Twin；个人候选尚未接入生产推理或候选专属盲评／A/B 发布。训练结果始终 `activation_allowed=false`。现有验证页明确测量 **当前使用的孪生**，不会把它的分数冒称为候选成绩。

评分采用 60 个固定不同情境题。先封存隐藏的 Twin 预测，再由本人独立回答和五维评审；自填题仅诊断，不计正式汇总。同题组、规范化后相同本人回答、旧版本及已经出现在模型输入中的参考答案均排除／合并。五维分别需要至少20个独立组且置信区间足够窄；数量达标仍可能不能评分。整体只在全部五维满足条件时显示，含 Wilson 区间与有限测试范围说明，称为「未见问题上的本人一致率」。没有总体人格复制完成度百分比，也没有音色相似度百分比。

## 实际验证

- Backend 完整测试：**726 passed, 6 skipped, 4 warnings**（`55b3970`），`build/twin-memory-final-backend-full.log`。后续许可恢复补丁相关 API／delivery／recovery：**32 passed, 2 warnings**（`25b8e81`），`build/personal-learning-grant-recovery-tests.log`。没有把完整测试冒称已重复运行于后续补丁；PostgreSQL线上迁移另验，不称 MySQL 已支持。
- 新电话最近会话承接：89项相关测试通过；主题回顾误判修正：42项相关测试通过。日志 `build/voice-latest-conversation-tests.log`、`build/chat-memory-targeted-overview-tests.log`。
- Contract v0.9：**31 passed**，保留 v0.1–v0.8 原形状；`build/personal-learning-contracts-final.log`。
- 私有 Worker 协议：**13 passed**，包括超过200个历史撤权清理记录仍可处理；`build/personal-worker-final-tests.log`。
- iOS：**15 单元 + 3 个不同 UI 场景通过**。正常、深色、AXXXL；修复父卡片标识覆盖和超大字题库裁切。一次共享模拟器深色启动进入普通录音页，原因未证实；专用模拟器复验通过，失败记录保留。UI 全为隔离预览，不代表真人评分或真机安装。
- iOS 记录：`build/ios-personal-learning-tests/verification.json`；截图 `reviewed-screenshots/`；签名构建 `build/ios-personal-learning-device-build.log`。
- 数据迁移 **0020 → 0021** 已在线事务执行，新增4个表及训练许可枚举。迁移前后录音、记忆、答案、声音档案和既有权限计数完全一致。记录 `build/personal-learning-migration.json`。
- CloudBase032 真实 Backend API 隔离验证：第一通电话带入最新文字，第二通带入上一通电话，跨电话同 turn_id 产生不同回答；具体书签问题找回原文字消息编号。结束测试电话、撤销新 VOICE 许可并删除本轮合成消息，清理错误为0。记录 `build/twin-memory-final-shared-history-live.json`。这是 API 边界验证，不冒称本次重新进行了真实 RTC／本人音色验证。
- 初次共享历史验证暴露语义排名未必带入最新通话，后续又暴露具体主题被误判为全历史回顾；失败证据保留，代码分别增加最近会话优先与明确主题检索，最终上述原消息检查通过。
- CloudBase034 独立训练 API 隔离验证9项检查均通过：默认关闭、训练器在线、60题、无虚构评分、匿名拒绝、独立训练许可、关闭、暂停后重开仍可撤销、撤权后不可用。本轮合成训练许可已撤销，未训练真人资料、未切换模型；记录 `build/twin-training-controls-learning-api-proof.json`。健康记录 `build/twin-training-controls-health.json`，发布／镜像记录 `build/twin-training-controls-deployment.json`。
- 本轮源码 ZIP 采用明确白名单、Unix0644 权限与运行时密钥扫描。CloudBase 源码任务曾在镜像推送成功后停留创建阶段；核对镜像推送／digest 后取消本轮暂存任务，再按同配置显式发布镜像，保留任务状态和失败记录。未清空数据库，未改 Android ECS，也未更换云端 Twin 提供商。

## 仍待完成

连接并解锁「黑幕」后覆盖安装 1.9.0。本人随后自行确认训练用途、继续核对原始材料，并完成独立情境题评审。个人候选的推理接入、晋级与全天云端部署需要确定部署方式，并取得足够独立验证证据；当前不把本机管线成功称为该整条闭环已经完成。

后端验证产物位于本机 `codex/twin-chat-memory` worktree 的 `build/`；iOS 产物位于主 checkout 的 `build/`。这些私有构建／数据目录不提交仓库，本文只记录安全元信息。

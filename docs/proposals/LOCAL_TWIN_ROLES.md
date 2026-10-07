# 三个数字孪生业务角色（本地实验）

2026-10-07 用户明确要求实现 Memory keeper、Portrait reader、Psychological learner，并确认保持单一 Agent 顺序循环。
基于已推送的 `feature/ai-agent-core` 增量实现；不更改 frozen integration schema 或 experimental 版本，不实现委派/工具/压缩。
这是现有 Android BYOK 实验的进一步业务验证，仍需刘修贤/康欣/张天霁 review，不能视为正式 Phase Gate 或项目边界追认。

## 实施拆分

1. Memory keeper：自愿开启的每日本机通知，时间可配，关闭/退出本地模式停止；清除本地资料清除提醒。
2. Portrait reader：现有七领域理解与原文形成多证据超边，提供真实关联图和可展开原文，保留 subject/revision。
3. Psychological learner：顺序 schema worker 提出情境化心理习惯候选，原文/本人校正可追溯，删除和撤除级联失效。

现有 shared Memory 是六类、Person Model 是七领域。“八大记忆/四大画像”尚无本轮可读的明确分类表；分类扩展需先确认，不能随意替换冻结枚举。
不承诺“完美复刻”。验证对象是具体事实、情境化倾向、问答/校正效果和证据，而不是人格完成百分比。
一次情绪不推成固定性格，重复来源也不当成独立印证；心理输出不是诊断。

## 录音提醒的实现与验证

使用平台 AlarmManager 的每日 inexact window，无新增依赖。通知不含记忆或人格细节，不调用模型、不启动录音。
时区/时间调整、重启、安装更新后重新排期；接收器重复投递同一天只通知一次。
Android 13+ 在用户开启时请求 POST_NOTIFICATIONS，拒绝后不保存为已启用。
平台可能受省电/Doze 延迟，不保证华为真机后台送达；实现依据 [官方定时任务文档](https://developer.android.com/develop/background-work/services/alarms) 和 [通知权限文档](https://developer.android.com/develop/ui/compose/notifications/notification-permission)。
确定性单元测试覆盖当天/翌日边界、夏令时和非法时间；Android 完整检查的结果将在提交前记录。真机通知未执行。
结果：`test assembleDebug assembleDebugAndroidTest lintDebug` 成功（1m9s），Debug/Release 各 46 项 JVM 测试通过；提醒送达、重启重排与系统权限交互未执行。

## Portrait reader 的关联模型

在既有 traits/materials 上做当前 revision 的投影，不创建另一套 Memory，也不伪造实体关系。
节点是 Subject、画像结论和原文/校正；每条超边包含一个 Subject、一个情境化结论和多个支持/反例 evidence_id。
原文撤除、删除或同意撤回后从投影排除。图中有限预览，领域列表保留完整关联及证据展开。
入口在“记忆与理解 → 查看我的画像与记忆关联”，由原有校正循环更新画像。
当前七领域保持原定义；不把未定义的四类展示当成正式 Person Model 语义。
结果：Android 完整检查成功（1m11s），Debug/Release 各 48 项 JVM 测试通过，lint 0 errors。多证据超边和撤除/第三方排除回归通过；图形真机交互未执行。

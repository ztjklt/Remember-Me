# Draft — Android single-loop digital twin roles

## What changed

用户要求的三个业务角色落实到已有手机独立循环：自愿开启的每日录音通知、画像/原文多证据超边、情境化心理习惯候选。
画像和心理 schema worker 使用同一文字模型顺序执行，阶段有检查点，完整成功才发布 revision；本人校正和来源删除/撤除作用于候选及回答。
APK 更新为 1.4-local；无自主子 Agent、委派、工具执行、检索、压缩或另一套 Memory。电脑模式保留原行为。

## How it was tested

完整命令、结果和安装包签名见 [验证记录](../verification/ANDROID_TWIN_ROLES_2026_10_07.md)。
Android test/build/设备测试包/lint/release 通过，Debug/Release 各 54 项 JVM 测试，lint 无错误。
真实 ASR + LLM 闭环、真实 LLM 单次/多来源心理候选及本人校正通过；临时输入均为合成资料。
CI 尚未为本批运行；设备测试未执行，手机通知、录音、存储及 UI 仍需 owner 真机验收，不以编译代替功能验证。

## Contract impact

- [x] No cross-module contract change
- [ ] Contract change has a linked Issue or proposal and approval

只扩展本地 journal 可选字段/投影；shared integration schema 和 experimental schema/version 均未改。
相关提案：[LOCAL_TWIN_ROLES](../proposals/LOCAL_TWIN_ROLES.md)。没有新增 Issue 或远程只读端点。

## Consent privacy migration and rollback impact

既有云端处理同意用于画像和情境候选，页面明确数据去向；密钥仅 Keystore 加密存储，未新增 SDK/预置凭证/自动历史发送。
提醒默认关闭，只发本机通用通知，不自动录音或调用模型。退出本地模式取消排期，清空资料清除提醒设置。
一次观察不代表固定性格或诊断；完全重复原文不增加来源计数，模型估计不是拟真度或测量准确率。
旧资料兼容读取；删除来源清除候选和未发布草稿。回滚不删除资料，但旧版不会使用候选，回滚前需关闭提醒。
涉及刘修贤 Android、康欣人物画像/Twin/Calibration，以及张天霁 UX/实验授权；既有 BYOK 待追认，合并前须相关 owner review。

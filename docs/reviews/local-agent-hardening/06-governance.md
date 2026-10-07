# PR 6 — 发布边界、中文文案与设计基线

## What / Why
BYOK 改为用户授权实验、待 Product/Integration 追认，张天霁确认后再合并。
补齐本地模式页面流、层级、仓库/任务/凭证与生命周期设计。Debug 默认本地；release 关闭实验本地入口并保留电脑模式。
本地设置/处理/录音库及共用 Agent 页静态文案收进 strings.xml，主要路径中文；技术协议/ID 保留原名。
APK 版本 1.3-local / code 4，同签名更新。旧 Demo/远程其他页面的完整国际化未纳入本轮。

## How / Testing
Android 完整 test/构建/设备测试编译/lint；追加 release 构建，检查两种 BuildConfig 开关。
本地核心使用真实 ASR/LLM 验证转写→理解→问答→校正→再次问答→重建引擎恢复，不作为真机验收。
最终命令、结果与 APK 校验记录见本目录 README。真机安装、旋转、dumpsys、播放、断网、SAF 未执行。

## Contract / Rollback / Review
共享契约和 experimental 版本不变。不开新远程端点，无供应商依赖或预置凭证。
回滚后恢复旧入口/文案，数据格式兼容；release 不删除 Debug 的已有资料。
本提交行数较多主要来自字符串机械外置和文档，属于工作单同一治理关注点，不混入 Agent 算法变更。
刘修贤、康欣及张天霁评审；本文件是未发布的 PR 草稿，推送不等于合并或评审通过。

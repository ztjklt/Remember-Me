# Android 本地 Agent 验证 — 2026-10-07

用户授权按 Memex 评审提案迁移为手机独立模式，明确排除多 Agent；复用 Kotlin/Compose，未复制 Memex 源码。
本次工作在既有 `feature/ai-agent-core` 分支增量进行，不修改共享契约、服务端 Memory 或电脑演示数据库。

## 本地基础与供应商适配器

- SQLite 原子保存本地日志；模型配置由 Android Keystore 的 AES-GCM 密钥加密，写入 no-backup 目录。
- 本地数据库排除自动备份及设备迁移。APK 不包含供应商凭证；错误信息不透出供应商响应正文。
- ASR 支持当前已联调的 DashScope 原生协议及 Chat Completions 音频输入，文字模型使用兼容接口。
- 阻止凭证 URL、非 HTTPS 远程地址和重定向；有录音大小、时长和响应体边界，不截断原文。
- 模型配置校验、凭证字符串隐藏、真实 HTTP 适配器的转写协议/回答/重定向测试通过。

构建工具现位于忽略目录 `build/android-tools`，不再依赖 `/tmp`。在 `apps/android` 执行：

```bash
export JAVA_HOME="$PWD/../../build/android-tools/java/usr/lib/jvm/java-17-openjdk-amd64"
export ANDROID_HOME="$PWD/../../build/android-tools/sdk"
export GRADLE_USER_HOME="$PWD/../../build/android-gradle"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew --no-daemon test assembleDebug assembleDebugAndroidTest lintDebug
```

基础版本结果：BUILD SUCCESSFUL（1m40s）。SQLite 关闭/重开测试已编译，尚未在设备执行。

## 单一 Agent 闭环

- 手机本地执行转写、理解、问答、校正；使用同一个文字模型，没有多 Agent、动态工具或压缩器。
- 原始转写、校正和历史 revision 分开保存；展示/校正绑定同一份已保存回答。
- 请求前持久化任务，转写成功后检查点保存；重启后显式继续任务，避免重复转写和重复提交。
- 输出校验领域、字段和引用；错误引用不会写入模型。撤除仅沿证据依赖失效，保留其他材料和历史。
- 三个新增回归测试覆盖校正后重启、失败后继续和录音去重、虚构引用拒绝、撤除与同意门控。

闭环及页面接入检查命令同上，BUILD SUCCESSFUL（1m29s）；Debug/Release 各 38 个测试通过。

# Android 三个数字孪生角色验证 — 2026-10-07

用户确认三个业务角色、单一 Agent 顺序循环。变更基于 `9f3a8d8`，在 `feature/ai-agent-core` 增量进行。
shared contract、experimental 版本、电脑 Backend 模式及服务端 Memory 未改；现有六类记忆/七领域保留。
实现范围与依据见 [角色提案](../proposals/LOCAL_TWIN_ROLES.md)，手机操作见 [本地模式说明](../../apps/android/docs/LOCAL_AGENT.md#三个数字孪生业务角色)。

## 完整 Android 检查

在 `apps/android` 执行：

```bash
export JAVA_HOME="$PWD/../../build/android-tools/java/usr/lib/jvm/java-17-openjdk-amd64"
export ANDROID_HOME="$PWD/../../build/android-tools/sdk"
export GRADLE_USER_HOME="$PWD/../../build/android-gradle"
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew --no-daemon test assembleDebug assembleDebugAndroidTest lintDebug assembleRelease
```

最终结果：BUILD SUCCESSFUL（1m23s），Debug/Release 各 54 项 JVM 测试，零失败、错误、跳过；lint 0 errors、28 个既有警告。
新增检查覆盖提醒当天/翌日/DST排期、多证据超边、撤除及第三方排除、心理步骤失败后复用 ASR/画像检查点、重复文本不增加独立计数、校正/重启、删除期间草稿失效、候选删除/撤除后不再参与回答、非法引用拒绝。
Debug 和设备测试 APK 构建成功；release 构建成功且 `LOCAL_AGENT_ENABLED=false`。设备测试仅编译，未执行。
本轮不修改 Backend/AI Core，没有重复执行其全量 pytest；基线加固验证分别为 Backend 261、AI Core 147 项通过，见 [加固记录](../reviews/local-agent-hardening/README.md)。

## 真实 API 验证

临时测试在忽略目录 `build/local-smoke`，凭证从既有 `.env` 仅传入进程环境，没有写入源码、报告或 APK。
经真实 Kotlin HTTP 适配器和引擎运行，不使用 Python Backend；存储为测试实现，不能替代真机 SQLite/Keystore 验证。

```bash
./gradlew --no-daemon -I ../../build/local-smoke/live.init.gradle testDebugUnitTest --tests me.remember.app.data.local.LocalProviderSmokeTest
./gradlew --no-daemon -I ../../build/local-smoke/live.init.gradle testDebugUnitTest --tests me.remember.app.data.local.RolesProviderSmokeTest
```

- 真实 ASR `qwen-audio-3.0-asr-flash` + LLM `deepseek-flash`：合成 AAC/M4A 转写 → 画像 → 心理空结果 → 队友问答 → 姓名校正 → 更新 → 重新加载后问答，34s 通过。两名队友分别为计算机科学/设计；Morgan 校正为 Jordan，revision 2，原文及锁定回答保留。
- 真实心理 worker：使用合成中文文本，单次散步观察 → 两段不同压力情境形成候选 → 校正为跑步并引用校正来源，21s 通过。这项没有验证中文录音识别质量，也不衡量人格拟真度。
- 第一次心理请求因未明确 JSON 输出而被文字服务返回 HTTP 400；修正格式要求后上述完整循环通过。格式依据见 [JSON 模式规范](https://api-docs.deepseek.com/guides/json_mode/)。

## APK 与安全

安装包：`build/releases/remember-me-1.4-local-debug.apk`，versionCode 5，10,286,105 字节。
SHA-256：`4c9788d3082dc359dd31d7935fae2f2b115763b4e1a792f530df290df9ced791`。
签名 SHA-256：`3a1a66daf4f19a9a86dc8d966694019297db72651d68956ee3bea9560478e92f`，与已交付的 1.3 相同，可覆盖更新并保留数据。
已扫描未推送历史、完整工作改动/新文件和 APK 全部条目，未发现已配置的两项供应商密钥；无已跟踪 `.env` 或 APK。提醒通知不带记忆/人物细节。

## 未执行及回滚影响

`adb devices -l` 无设备。手机麦克风、SQLite/Keystore、通知权限/送达/重启、后台省电和关联图操作均未真机验证。
人工验收：覆盖安装 → 设置每天提醒 → 录两段不同经历 → 查看画像/候选依据 → 问答校正 → 断网继续 → 删除来源检查候选排除。
日常提醒为系统非精确窗口，可能延迟；处理中需保持 App 打开，进程终止后显式继续任务。
旧 journal 缺少 habits 时按空列表读取；新增录音/校正才分析。回滚代码保留原资料但不使用新候选；回滚前关闭录音提醒。
本轮没有自动发布、创建 PR 或合并。正式合并仍需刘修贤/康欣/张天霁 review，以及既有 BYOK 实验追认。

# Android 八维记忆与四类画像验证 — 2026-10-08

## 改了什么与为什么

用户授权实施申请书的八类记忆与四种画像，继续单一 Agent 顺序循环。
基于已发布的 `feature/ai-agent-core` / `8627f03`，交付 `1.5-local`，不改写历史或合并 develop 的不同契约。
原文先存档，观察与人物理解分层更新；提问检索原文，校正和删除保留依赖关系。
固定底部入口让记忆、画像、问答和设置可直接找到；旧录音可显式重新提取，复用 ASR。

| 实现文件范围 | 行为 |
| --- | --- |
| `MemoryObservation.kt` / `LocalAgentEngine.kt` | 八维定义、启停、引用校验、Unicode 码点 span、观察检查点、独立材料版本、旧原文重提取队列 |
| `LocalEvidenceIndex.kt` / `LocalInference.kt` | 中文双字/英文词召回、完整原文片段、校正依赖补齐、增量属性更新及稳定 ID |
| `LocalPortrait.kt` / `PortraitViews.kt` / `LocalDeletion.kt` | 四图数据、事件/讲述时间区分、显式决策、表达独立样本、校正替代与来源删除级联 |
| `PortraitPanels.kt` / `LocalPortraitScreen.kt` / `MemoryObservationBrowser.kt` | 四图页签、八维筛选、来源展开、失败/待更新状态与重试 |
| `RememberMeApp.kt` / `MainScreens.kt` / `LocalAgentScreens.kt` / `LocalAgentSession.kt` | 固定导航、模式来源、维度设置、旧资料重提取；只读加载不再触发循环刷新 |
| `LocalModelClient.kt` / `ModelSettings.kt` | 可选普通文字模式、8192-token 输出预算、明确拒绝截断的 JSON；密钥仍经既有加密配置 |

没有子 Agent、委派、模型工具执行、内容压缩、供应商 SDK 或新增依赖。
保持单一 SQLite journal 写入源，使用附加字段兼容旧资料；结构化表迁移未实施。
电脑模式继续使用现有服务，仅增加已有七领域/原文的只读画像入口；不宣称服务端有八维明细。

## 自动检查

在 `apps/android` 执行：

```bash
export JAVA_HOME="$PWD/../../build/android-tools/java/usr/lib/jvm/java-17-openjdk-amd64"
export ANDROID_HOME="$PWD/../../build/android-tools/sdk"
export GRADLE_USER_HOME="$PWD/../../build/android-gradle"
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew --no-daemon test assembleDebug assembleDebugAndroidTest lintDebug assembleRelease
```

最终版：BUILD SUCCESSFUL（3m31s）。Debug/Release 各 76 项 JVM 测试，零失败、错误、跳过；lint 0 errors、28 个既有警告。Debug、设备测试 APK 及 release 均构建成功。
新增/更新测试覆盖：连续中文/emoji 原文 span、无依据日期/引用拒绝、姓名校正不覆盖教育、长材料不丢字、旧转写重提取不再调用 ASR、原文先发布、失败后版本校验、增量 trait ID、校正召回、枚举不取固定 top-k、超大相关集合明确拒绝、旧事件召回、四图语义和远程能力边界。
设备测试新增四页签及依据展开、失败页恢复入口用例；这些只编译，未在设备执行。
仓库没有单独配置 Kotlin formatter/typecheck 命令；使用编译、Android lint 和 `git diff --check` 验证。

服务端回归使用原有虚拟环境，未修改其业务代码：

```bash
services/backend/.venv/bin/pytest -q services/backend/tests
services/ai-core/.venv/bin/pytest -q services/ai-core/tests
```

AI Core：147 passed，2 个既有警告，4.63s。Backend：261 项全部通过，exit 0；进度全部为通过标记并到 100%，只有既有弃用警告（仓库 `-q` 叠加命令 `-q` 后不输出汇总行）。
完整输出在忽略目录 `build/memory-portrait-verification/`，不提交环境、生成文件或整份日志。

## 真实 API 循环

测试通过真实 Kotlin HTTP 适配器与 `LocalAgentEngine`，不经 Python Backend。
凭证从已有 `.env` 只传入进程环境，未写入代码、报告、命令参数或 APK。
存储为 JVM 测试实现，不能替代手机 SQLite/Keystore 验证；输入均为合成材料，未处理用户私有录音。
可选测试源码/Gradle init 在忽略目录 `build/local-smoke`，不进入常规测试或 APK。

```bash
./gradlew --no-daemon -I ../../build/local-smoke/live.init.gradle testDebugUnitTest --tests me.remember.app.data.local.LocalProviderSmokeTest
./gradlew --no-daemon -I ../../build/local-smoke/live.init.gradle testDebugUnitTest --tests me.remember.app.data.local.MemoryPortraitProviderSmokeTest
```

- 真实 ASR `qwen-audio-3.0-asr-flash` + LLM `deepseek-flash`：合成英文 AAC/M4A → 原文 → 观察/理解 → 队友问答 → 姓名校正 → 重载后问答，29s 通过。两名队友分别学习计算机科学、设计；Morgan 校正为 Jordan 后回答更新。
- 真实 LLM 中文语义循环：六段合成文本，使用替代 ASR 的测试实现；64s 通过。生成 30 条观察，四图均有依据；问答正确返回两位队友及专业，姓名林晨校正为林宸后保留学校与研究方向。
- 同一中文循环继续将比赛第二名校正为第三名，断言旧事件退出当前视图、原有有据日期保留；重载后结果保留，删除比赛来源后观察退出且依赖回答失效。
- 这不验证中文 ASR 识别率，不衡量人格拟真度，也未完成提案建议的 20 段/30 问人工评估集。

初次真实调用发现文字服务的默认思考预算导致输出截断/结构不完整；适配器现可选普通模式且拒绝截断结果。
已知 DeepSeek 地址默认 `reasoning_effort=none`，未知地址不自动附加该字段；依据见 [官方思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)。

## APK、兼容与安全

安装包：`build/releases/remember-me-1.5-local-debug.apk`，versionCode 6，10,394,121 字节。
SHA-256：`607801fc5d202e2567eecc8ed573b94c293e820b050cca85bd9490db4f533ab6`。
签名 SHA-256：`3a1a66daf4f19a9a86dc8d966694019297db72651d68956ee3bea9560478e92f`，与已交付 1.4 相同，可覆盖安装。
已扫描未推送历史、完整工作 diff/新增文件及 APK 全部条目，未发现已有两项供应商密钥或其他 Key 形状值；无已跟踪 `.env` 或 APK。凭证不进日志、备份、导出，测试报告只有合成内容。

覆盖安装保留原资料与配置，不卸载、不清除应用数据。旧资料默认直接读取；点“记忆 → 重新提取已有记忆”才把旧原文送给文字服务。
Debug 开启本地实验门；release 编译保持 `LOCAL_AGENT_ENABLED=false`，电脑模式入口保留。
旧代码不认识新增观察字段，不能通过卸载或清空数据回退；停止新任务后回滚源码重新构建较高 versionCode 的同签名包，仅使用旧能力。新观察及重提取队列应由新版本继续处理，避免旧代码重写 journal 后丢弃附加字段。

## 契约、设备未执行项与评审

`packages/contracts`、`integration-contract-v0.1*.json`、`agent-loop-v0.2-experimental` 和服务端业务代码未变；没有新增端点或跨模块 payload。
本地的 `local-memory-v1` 是内部观察分类，不冻结为两端契约。扩展电脑模式须另行 Issue/产品与 Integration 评审。
借鉴 Memex 的机制，自行实现，没有复制其 GPL 源码。

`adb devices -l` 没有设备。本轮未执行：手机覆盖安装/升级、真实麦克风、SQLite/Keystore、导航与图表点击、旋转/进程重启、断网继续、删除文件、通知权限/送达/省电策略。
手动验收：覆盖安装 → 检查旧原文/配置 → 重提取旧资料 → 四图逐项展开依据 → 录一段新经历 → 问队友/身份 → 校正姓名 → 检查画像与再次问答 → 断网恢复 → 删除来源核对失效。

状态、环境当前只接本人自述；声学情绪/环境音识别明确未检测。中文词项召回尚无语义向量能力，长相关集合仍可能超容量；完整时间有效区间、图关系推理和跨端数据导入均未实施。
用户授权实验并推送 feature 分支，不等于正式合并批准。合并前仍需刘修贤/康欣/张天霁及涉及 Backend 的 owner review，并追认既有 BYOK 边界。

## 原子提交

- `7b4d9dd`：观察提取，7 文件，251 行新增/16 行删除。
- `ba79182`：检索与增量理解，15 文件，299 行新增/38 行删除。
- `0db2c86`：四图投影与旧原文重提取，9 文件，206 行新增/18 行删除。
- `818135c`：四类画像界面，6 文件，291 行新增/46 行删除。
- `670d72f`：记忆筛选与固定导航，9 文件，129 行新增/21 行删除。
- 最终版本、实施范围和本验证记录在同一个交付提交；提交前审查完整暂存 diff 与实际文件数量。

每个提交一个可评审关注点，未做机械格式化或拆出无意义提交。只推送当前 feature 分支，不创建 PR 或合并。

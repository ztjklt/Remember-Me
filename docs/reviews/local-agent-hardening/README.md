# 本地 Agent 加固与交付记录

日期：2026-10-07。在用户已调通的 `feature/ai-agent-core` 上增量实施，批次起点 `1a33138`。
这是源码推送与 Debug APK 交付，未合并到 develop/main；六份 PR 正文草稿分别链接如下。

## 实施范围

| 关注点 | 提交 | 记录 |
| --- | --- | --- |
| 页面生命周期、草稿和处理结果 | `2aa50dc` | [PR 1](01-lifecycle.md) |
| 本地归档、问答历史、Demo 隔离 | `75fdf98` | [PR 2](02-archive.md) |
| 录音删除、级联失效、版本历史、清空 | `57abcf4` | [PR 3](03-lifecycle-data.md) |
| ASR 检查点、容量与版本恢复 | `b666413` | [PR 4](04-integrity.md) |
| 后端句级来源、失败隔离、锁定一致性 | `0b7301c` | [PR 5](05-backend.md) |
| 损坏 sidecar 的删除回归 | `9feb5d3` | [PR 3 补充](03-lifecycle-data.md) |
| 发布开关、中文文案与设计文档 | 本记录所属 `chore(android)` 提交 | [PR 6](06-governance.md) |

本轮按六个稳定关注点提交，另加一项复核发现的删除修复，共 7 次；不重排已有历史。
此前分支有 41 个尚未发布提交，首次推送会连同它们上传，共 48 个未发布提交。
字符串外置和 Mock/测试移动计入 Git 完整文件范围；不可用编辑器的文件数代替整个分支 diff。
Git 实际范围：本批次 46 个文件；整分支相对 develop 的共同基点 163 个文件，包含此前原型和 Agent 实现。

## 六项决策

1. 不新增远程历史端点：本地完整历史，远程已知会话历史和既有 GET by ID。
2. 本轮隐藏本地 trait 状态词表，不冒充已实现连续性或完整冲突检测。
3. 不做检索：超限明确提示，可删除旧录音并继续任务，不截断或压缩。
4. 虚构人物页面标记 Demo，移出真实流程，只从 Debug 菜单访问。
5. Debug 默认本地模式；release 关闭本地实验入口，保留电脑模式。
6. 本地主要操作中文；协议、模型名、调试标识保留原名。

## 执行命令与结果

Android（在 `apps/android`）：

```bash
export JAVA_HOME="$PWD/../../build/android-tools/java/usr/lib/jvm/java-17-openjdk-amd64"
export ANDROID_HOME="$PWD/../../build/android-tools/sdk"
export GRADLE_USER_HOME="$PWD/../../build/android-gradle"
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew --no-daemon test assembleDebug assembleDebugAndroidTest lintDebug assembleRelease
```

最终 BUILD SUCCESSFUL（1m44s）。Debug/Release 各 43 个 JVM 测试通过，零失败/跳过；设备测试仅构建，未运行。
`lintDebug`：0 errors、28 warnings，主要是依赖更新提示、既有图标/SDK/版本目录警告；未为消除提示升级无关依赖。
生成 BuildConfig 核对 Debug 本地开关 true、Release false。release 构建未签名，不作为本次手机安装包。

Backend（在 `services/backend`）：`.venv/bin/python -m pytest`，261 passed、4 warnings，1455.92s。
AI Core（在 `services/ai-core`）：`.venv/bin/python -m pytest`，147 passed、2 warnings，1.12s。
本轮未改 services/ai-core；后端最后一次全量包含混合转述的部分证据回归和内部迁移 0005。

电脑 HTTP 循环（临时数据库，不改现有会话）：

```bash
services/backend/.venv/bin/python scripts/run_agent_demo.py --mode fixture \
  --backend-port 18000 --ai-port 18100 --stt-port 18200
```

通过：上传/转写/Memory → revision 1 → ORIGINAL → LOCKED → 校准五维 → revision 2 → 再录音 → revision 3。
结果在忽略目录 `build/agent-demo/fixture/last-loop.json`。此项使用明确标注的固定转写，仅证明 HTTP/迁移/编排通路。

另用临时 JVM 测试源经 Android 实际 `HttpLocalModelClient`、`LocalAgentEngine`、`AgentRepository` 调用真实模型，
ASR `qwen-audio-3.0-asr-flash`、LLM `deepseek-flash`。凭证私下从未跟踪的 .env 注入，不写测试源或报告。
合成 M4A 原文是虚构 Morgan、研究生、两个队友（计算机科学/设计）。验证：

- 真转写 → revision 1；队友回答：“你有两名队友：一名学习计算机科学，另一名学习设计。”
- 本人校正为 Jordan → revision 2，保留原文与旧锁定回答；重建引擎后再次提问回答 Jordan。
- 临时 provider 测试成功（31s），报告 `build/local-smoke/report-hardening.json`，原文与凭证均未进入 Git。

临时测试通过 `-I ../../build/local-smoke/live.init.gradle testDebugUnitTest --tests me.remember.app.data.local.LocalProviderSmokeTest` 注入；
不是常规构建依赖，也未加入普通测试的网络门槛。随后普通 `testDebugUnitTest` 再次通过（18s），报告恢复 43 项。
合成音频和内存 journal 验证核心链路，不能替代 Android 麦克风、Keystore、SQLite 或 Activity 真机检查。

## APK 与安全核对

- 安装包：`build/releases/remember-me-1.3-local-debug.apk`，versionCode 4，10,241,293 bytes。
- SHA-256：`c4ec98e4abf17888379b0148848c22690cb0843ecff3add56fd2b64024bbe2b8`。
- 签名证书 SHA-256：`3a1a66daf4f19a9a86dc8d966694019297db72651d68956ee3bea9560478e92f`，与先前 1.2 APK 相同，可覆盖更新；不要卸载或清除应用数据。
- 待发布完整提交补丁、当前 diff、新文件和 APK 所有条目均扫描：未含已配置密钥，无意外 key 形值；.env/APK 未被 Git 跟踪。
- shared integration schema 未改；experimental 名称和版本不变，无新端点、供应商 SDK、子 Agent、检索或压缩。

## 未执行与合并前评审

`adb devices` 无设备，本轮未执行安装、旋转、Don't keep activities、dumpsys 密钥检查、播放、确认删除、断网和 SAF 导出。
SQLite 迁移/恢复及 Activity 重建 instrumentation 已编译，但设备行为需刘修贤真机验收。
真实模型输出仍可能变化；句级来源判定是中文启发式，未实现完整转述语义；校准并发分支未做压力测试。
远程完整历史列表、trait 连续性、检索、后台自动恢复、其他旧页面完整国际化不在本轮。

刘修贤审客户端/设备，康欣审 Person Model/Twin/Calibration 语义；张天霁审 UX、冻结边界与 BYOK 追认。
本地 BYOK 仅为用户授权实验，Product/Integration 尚未追认；须张天霁确认后才能合并。
推送功能分支不代表稳定主分支发布，也不代替这些 owner review。

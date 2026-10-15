# 本轮检查证据 · 2026-10-15 夜间

本轮是比赛前双端扫描与交接。没有改变业务运行代码、数据库迁移、线上配置、Android APK 或 iOS App；不能把本轮测试说成新真机验收。

## 固定输入与检查结果

| 检查 | 本次结果 | 实际覆盖 |
|---|---|---|
| GitHub 状态 | Android 基线 `e5c037c`，PR #94 OPEN，未合并；基线 6 项 CI 均成功，comments/reviews 均为空 | 本轮拉取时快照；交接新提交的 CI 需另看最新 SHA |
| 两端公网存活/就绪/版本 | 两端各 3 个请求均 HTTP 200 | [public-runtime.json](public-runtime.json)，TLS 正常验证；没有登录 iOS 或重新调用模型 |
| Android/ECS 后端重点回归 | **49 passed / 0 failed / 0 skipped**，37.229 秒 | 校对、语音会话、提交恢复、分享邀请、人物对话；隔离 SQLite + fixture |
| iOS 分支后端重点回归 | **41 passed / 0 failed / 0 skipped**，24.298 秒 | 声纹匹配、未知继续聊天、登记、多人归属、撤销、录音豆来源边界、托付；隔离目录，fixture 声纹/STT |
| Android JVM 重点回归 | **21 passed / 0 failed / 0 skipped** | Work3200Import 7、Work3200Session 9、ClientTranscript 5；不是硬件连接测试 |
| 静态扫描工具回归 | **4 passed** | 常量路径、动态路径保持未知、不执行目标源码、同路由不同字段、迁移 revision ID |
| 既有 schema Contract | **15 passed / 0 failed / 0 skipped** | `packages/contracts` 执行 `npm test`；旧 schema 自洽，不代表双端新功能等价 |
| 已装模拟器版本 | `0.12.1-internal` / `20261023` | ADB 包信息；只有 emulator-5554，无实体手机；reverse 列表为空 |
| GitHub Release | 非草稿 prerelease，7 个附件，APK 163,917,379 字节 | 本轮元数据核对；完整下载/哈希结果见同日交付记录 |
| 双端 Twin payload 交叉校验 | 双方真实模型均拒绝对方额外字段 | Pydantic `extra_forbidden`，不是网络或登录报错 |
| 整分支合并预演 | **19 个冲突文件** | [merge-preview.json](merge-preview.json)；只写 Git 临时对象，未合分支/索引/线上 |
| 最新 iOS 源码存在性 | 声纹分支 apps/ios 与 Android 基线树完全相同，5 个 Swift 文件，最后修改 10 月 7 日 | 最新文档所述 LiveKit/声纹/ActivityKit UI 源码未找到；另有 PR #90 的 10 月 10 日旧客户端增量 |

[focused-tests.json](focused-tests.json) 为 JUnit 汇总和交叉校验结果。既有同日完整 PostgreSQL 718 项、真实模型/Android 云端流程及媒体证据，见[云端交付记录](../../../agent-loop/CLOUD_SYNC_RESULTS_2026-10-15.md)。不把旧完整测试与本轮重点回归相加成新的全量测试。

## 如何重跑静态扫描

工具只从指定 commit 读取文件并解析 AST；不导入/执行被扫描分支、不读取 .env、不探测数据库、不输出配置值或密钥。

```bash
python tools/delivery/audit_platform_sync.py --android e5c037cd59dfe010637995c0627c82e1d7e89941 --ios-backend 7931dde6413466fb5d67021d342f2824cb0604e5 --output platform-scan-local.json
python -m unittest discover -s tools/delivery/tests -p test_platform_sync.py -v
```

[platform-scan.json](platform-scan.json) 固定了两个源 SHA、声明路由、Pydantic 类型字段、迁移与 iOS 文件列表。扫描覆盖 `services/backend/app/api/*.py` 与 migration 文件；只解析直接 `BaseModel` 字段和可静态求值的路由，**不是完整 OpenAPI、继承模型、依赖权限或注册状态验证**。同名地址仅作排查线索，不能视为协议等价。`main.py` 内定义的 service-info 不在该静态路由清单中，已有独立公网探测。

## 本次执行的测试命令

在 Android 后端 `services/backend`：

```bash
python -m pytest tests/test_transcript_correction.py tests/test_voice_sessions.py tests/test_voice_commit_recovery.py tests/test_sharing_invitations.py tests/test_persona_dialogue.py --junitxml=var/integration-audit-20261015/android-backend-tests.xml -q
```

将 iOS 分支固定 SHA 的 `services/backend`、`services/realtime`、`packages/contracts` 用 `git archive` 解到 ignored 的隔离目录，在该后端目录运行：

```bash
python -m pytest tests/test_voiceprint_person_model.py tests/test_speaker_identification.py tests/test_wearable_memory.py tests/test_entrustments.py --junitxml=ios-focused-tests.xml -q
```

本次使用既有 Python 3.13.5 测试环境，LiveKit API 1.2.1 / protocol 1.1.27 及依赖安装在独立 target 目录，仅对该测试进程提供 PYTHONPATH；没有改运行环境或下载/验证真人声纹模型。fixture 测试不需要 Sherpa 权重，不能写成模型真实识别验收。

Android 目录，JDK 17、SDK 与完整 Gradle 缓存配置后：

```powershell
./gradlew.bat --offline :app:testDebugUnitTest --tests me.remember.app.hardware.Work3200SessionTest --tests me.remember.app.hardware.Work3200ImportTest --tests me.remember.app.integration.ClientTranscriptTest
```

初次命令的通配符被展开为本地 log 文件名，第二次缺少 ANDROID_HOME；两次均未执行测试。改为精确类名并设置 SDK 路径后成功，未改产品代码绕过失败。测试只出现既有图标弃用/路径警告；Python 测试有 TestClient 弃用告警。

扫描工具另一次复查误在 `packages/contracts` 下使用仓库根的相对测试路径，未执行；回仓库根重跑 4 项通过。Contract 的 `npm test` 独立成功，不用后一个命令的退出码掩盖前一个路径错误。

公网探测第一次在发请求前因本机 SOCKS 依赖缺失退出；第二次用直连 HTTPS 和正常 TLS 校验完成。不是远端服务故障，未关闭 TLS 验证。

## 未验收

- 用户所述最新 iOS 声纹 bug、未描述的 Android bug，没有最短复现/日志，保持未定位。
- iOS 1.13.1 当前源码构建、真机声音、真实人物声纹准确性、录音豆实物、耳机和回声。
- 双数据库升级/合并、统一后端、跨端账号迁移、两条通话协议互换。
- 本次没有重录视频或改变延迟；发布页原速视频仍是既有同日样例，稳定两秒仍未实现。

后续补交/新结果请另加日期和 SHA，不覆盖这里的失败与范围说明。

本轮另做只读交接审查：对照固定源码、原始 XML 与新增文档/工具，未发现 Critical/Important 阻断。两处字段/视图名称 Minor 已修正。该审查不代表未知手机故障已解决，也不替代 iOS 新版构建和双数据库合并验收。

# 团队推送前验证清单 · 2026-10-10

## 版本与范围

- 基于 `6ca7244` 创建独立 `codex/team-handoff-20261010`，Android 增量提交 `a907a5b`；原 `codex/agent-integration` 工作区未被清理或覆盖。
- 干净候选目录中只加入已选择的 Android 文件、测试、交接说明、无密钥配置模板和 19 张截图；未复制正在开发的 AI/后端语义实验。
- 运行中的 ECS：`/opt/remember-me/releases/paired-c2e17fc`。本次只读检查 API、worker、profile、AI 四服务均 active；没有部署变更。

## 本次新执行的检查

| 检查 | 实际命令或方法 | 结果与边界 |
|---|---|---|
| 后端全量 | 在候选 `services/backend` 运行 Python `-m pytest tests -q` | **460 通过，6 跳过**，退出码 0；6 项为需显式 PostgreSQL 测试环境的探针，不能算通过 |
| AI Core 全量 | 在候选 `services/ai-core` 运行 Python `-m pytest tests -q` | **271 通过**；不包括未选入的语义实验，外部模型为确定性替身 |
| AI Core 独立安装包 | `uv build --wheel`，将 wheel 解压到仓库外临时目录，以 `python -I` 执行 `scripts/check_wheel.py` | **通过**；契约与共享原文件逐字节相同，schema 校验拒绝缺字段对象，服务启动及四组提取 HTTP 检查通过；`uv lock --check` 通过 |
| 共享契约 | `npm ci --ignore-scripts`、`npm test` | **15 通过**；不代替全部新增业务接口兼容测试，邀请/权限等由后端测试覆盖 |
| Android | `testDebugUnitTest assembleInternal assembleInternalAndroidTest -PrememberTestBuildType=internal --offline --console=plain --max-workers=2` | **52 单元测试通过**，无失败/错误/跳过；签名应用与 instrumentation APK 构建成功，使用已有 Gradle 缓存 |
| 新包 ECS 复验 | 安装本候选应用与测试包，运行 `MeetingDemoLiveTest` 的 resume 阶段 | **1 项通过，28.32 秒**。读取已处理故事/3 条记忆、播放 ECS 原音、重新实际请求问答、播放回答来源、人物入口。不是又录制一段新音频 |
| 业务连接 | `adb reverse --list`、实际服务地址 | 无转发规则；APP 直接请求 `https://39.108.183.47` |
| 截图完整性 | 对照源文件逐一复算 SHA-256 | 19 张顺序原图，26,341,999 字节；不附网站或密码文件 |
| 提交前检查 | `git diff --check`、已知密钥精确匹配及密钥/私钥模式扫描 | 选定文件及待同步历史未发现匹配；这不是专业渗透测试或无漏洞保证 |

Python 测试使用现有 Python 环境，在独立候选源码目录执行；不是重新安装全部依赖后的冷启动。框架的 Starlette/httpx/anyio 和 SQLite datetime 弃用警告保留，未将其隐藏或当成功能失败。PostgreSQL 专项验证此前在 ECS 隔离库执行，历史结果见 [部署恢复报告](PAIRED_DELIVERY_RECOVERY_2026-10-10.md)；本次没有重复对正式数据库跑测试。

## 推送后的安装包问题与修复

首次 PR 检查中，Backend、Android、Contract 通过；AI Core 的 Python 3.12/3.13 源码测试和 wheel 构建通过，但仓库外安装包启动失败。根因是 `app/narrative.py` 用仓库相对路径读取故事契约，而 wheel 未携带该文件。

修复将**同一份共享契约**随 wheel 打包，安装包优先读取内置资源；源码目录仍读取共享原文件。没有改契约内容、放宽证据校验或更换模型。独立 smoke 增加契约存在性、与原文件的字节一致性和无效对象拒绝检查，避免源码测试掩盖安装包资源缺失。

修复后本地重新执行 AI Core 全量：**271 通过，12.99 秒**（Python 3.13.5）；独立 wheel smoke 及锁文件检查通过。GitHub 的后续检查结果以 PR 当前提交为准，不能用首次失败提交的状态代替。

## APK 与真模型结果

本次重新构建：

- 文件：`apps/android/app/build/outputs/apk/internal/app-internal.apk`，构建输出不提交 Git。
- 大小：148,803,354 字节。
- SHA-256：`2d402713744f0df809d159765fb6411af6ce31ebe054a3e11a20338f590d5204`。
- 包名 `me.remember.app.internal`，版本 `0.7.0-internal`；同一内测签名，不是 debug 包。
- 新包复验使用既有 episode `ep_8a092f18940a4e01`，返回的来源版本标识为 `bailian/paraformer-v2`、`Deepseek-v4-flash`，保存 3 条记忆。
- 本次重新发起问答为 SIMULATION，引用仍来自较早同主题有效材料 `ep_07b58509766b4be7`。因此只证明“当前有权空间问答”，不能说只用刚录入材料回答。

19 张截图记录的是稍早当天的完整分阶段旅程，APK SHA-256 为 `3b09e67db50572933451ca7d0c7a7bedd21a526b8f7425ecdede9424cb35cec6`。重新构建产物与截图原包分别记录，不用一个哈希冒充所有版本。

## 不在本次通过结论内

- 没有重跑完整 60 问；54/60 是已冻结 v15 的历史开发集结果。
- 没有在本次新包复验重新跑 ASR、人物生成、邀请/补问、纠正、撤权、断网/重启全部阶段；当日截图及历史专项记录分别说明覆盖。
- 实体 Android 真人麦克风、iOS 编译/设备、任意网络、公众注册没有本次通过证据。
- 八维/四视图可以操作，不意味着材料丰富度、人物理解准确性和长期更新质量已合格。
- 本次没有向 ECS 发布尚未验收的语义实验，没有改供应商、放宽证据校验或移除权限保护。

原始测试日志、普通账号和调用结果留在原本的忽略目录；仓库交付结果摘要及带哈希的截图，不上传包含会话和凭据的原始运行目录。

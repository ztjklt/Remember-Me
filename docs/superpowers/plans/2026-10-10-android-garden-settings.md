# Android 花田与设置 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在现有 Android 双角色客户端中交付真实花田、花瓣阅读及日常设置，并允许至少 8 位密码。

**Architecture:** 原生 Compose 共用现有会话、播放器和服务端可见数据。纯展示映射负责按证据关联故事与记忆；外观偏好仅存本机。密码长度调整复用现有鉴权、哈希和管理员命令。

**Tech Stack:** Kotlin / Compose / SharedPreferences、Python / FastAPI / Pydantic / pytest。

**Spec:** `docs/mobile-ui/ANDROID_GARDEN_AND_SETTINGS_2026-10-10.md`，用户于 2026-10-10 确认继续，并追加简单 8 位密码要求。

## Global Constraints

- 仅在 Remember Me 交接工作区修改；不改饮食项目，不合并团队分支。
- 花瓣只映射当前有效、可见的真实 ID；旧网页 E01–E03 不进入正常模式。
- 不更换供应商，不放宽引文和故事授权，不把机器稿当核对稿。
- 密码下限从 10 调整为 8，上限仍为 128；不增加字符组成要求，不重置既有账号。
- 系统权限、云端同意与亲友授权分别显示；注册保持关闭。
- 新截图与旧 19 张分开；模拟器、真机及 iOS 分别报告。

## Review Focus

- 一段录音涉及不同故事：只按实际证据关联，不能把同音频全部记忆混入。
- 待核对、失效与撤权材料：不出现在成功花田或恢复后的详情。
- 主题切换与重启：外观保留，业务任务和核对文字不因换主题丢失。
- 退出或切换空间：关闭旧花瓣和播放，迟到结果不得恢复。
- 清缓存：仅清可下载来源音频，不删未上传原音或凭据。

## Task 1：8 位密码兼容

Files: `services/backend/app/api/accounts.py`、`app/account_admin.py`、`tests/test_accounts.py`、Android 登录页、`docs/architecture/account-password-policy-proposal.md`。

- [x] 添加注册／登录／管理员重置 8 位成功、7 位拒绝测试，并先观察失败。
- [x] 将 `Credentials.password` 的 `min_length` 改为 8；更新 Android 文案和登录按钮条件。
- [x] 运行 account 测试，确保旧密码、限速、退出和重置撤销会话仍成立。
- [x] 记录不需要数据库迁移；旧账号不自动改密码。

## Task 2：花田映射

Files: 新增 `integration/GardenProjection.kt` 和 `integration/GardenProjectionTest.kt`。

Interfaces: `projectGarden(stories: List<JSONObject>, narrative: JSONObject): List<GardenCluster>`；`GardenCluster` 携带真实 ID、标题、是否已组织、花瓣及来源录音 ID；`GardenPetal` 携带正文、来源类型与实际证据。

- [x] 先检验共用录音不同证据不会混入、待核对／失效排除、跨录音关联、ID 去重和来源移除。
- [x] 实现映射；记忆的全部当前有效证据须属于已确认故事，未归组录音保留独立入口。
- [x] 运行 `testDebugUnitTest --tests '*GardenProjectionTest'`。

## Task 3：花田与阅读

Files: 新增 `integration/MemoryGardenScreen.kt`；修改 `NativeWorkbenchScreen.kt`。

Interfaces: 花田消费 Task 2 结果，通过 `openSource(episodeId)` 进入现有原音／来源流程；筛选、选择及分页按 actor / subject 保存。

- [x] 原生花朵、五瓣分页、故事展开、证据阅读、列表与搜索接入档案“记忆”。
- [x] 实时资料变化后关闭不可见详情；返回恢复筛选与位置，换号清状态。
- [x] 已确认故事与未归组记录、空态、待处理分别显示，不编造标题或花瓣。
- [x] 编译并在模拟器点击花簇／花瓣／来源／返回，记录截图。

## Task 4：外观与设置

Files: 新增 `integration/AppearancePreferences.kt`、`integration/AppSettingsScreen.kt`；修改 `MainActivity.kt`、`NativeWorkbenchScreen.kt` 和 `NativeWorkbenchModel.kt`。

Interfaces: `AppearanceChoice(theme, scene, reduceMotion)` 是非敏感设备偏好；`MainActivity` 读取后传给主题和工作台；设置路由复用现有分享、请求、用词和审核组件。

- [x] 偏好解析先测未知值安全回退；实现系统／浅／深、场景和简化动态效果。
- [x] 拆出账号、外观、设备权限、分享、用词、待处理及帮助入口；只暴露真实能力。
- [x] 设备权限回到前台重读；提醒开关调用现有机制，系统设置不伪装应用已授予权限。
- [x] 缓存入口调用现有 `stopSource` 清下载源缓存，保留本机原音；测试其生命周期边界。
- [x] 模拟器验证主题重启、权限、换号和缓存清理。

## Task 5：构建、部署与交接

- [x] Android 单元测试及 APK 构建；后端 account 回归及完整后端检查。
- [x] 独立复核映射、状态恢复与隐私边界；修复后再检查。
- [x] 服务器仅更新已验证密码下限，保留旧发布目录、原音和数据库；不自动修改账号。
- [x] 新版 APK 单独构建、记录哈希与截图，更新安装说明和当前状态；未通过项明确列出。
- [x] 通过后同步既有 Draft PR，不合并；旧 APK 和 19 张截图保持可追溯。

## Execution ledger

- 2026-10-10：采用当前会话顺序执行；用户已确认规格和继续开发，本计划落实该指令，不重复询问是否继续。
- Ruling: 账号名继续允许 3–64 个字母、数字及 `_.-`，密码允许 8–128 字符 — 用户关注输入便利，不把账号名也强制为恰好 8 位。
- Ruling: 旧账号密码不自动重置 — 避免已发给队友的凭据失效；新建或明确重置时可使用 8 位。

- 实测范围以 docs/agent-loop/ANDROID_GARDEN_DELIVERY_2026-10-10.md 为准；未把412dp、完整权限矩阵、真机或iOS填成通过。
- 交付源码提交 `7b0d10f` 已推送到既有 Draft PR #89；`demo-android-0.8.0-20261010` 附件的 APK SHA-256 与本机最终实跑包一致。旧0.7.1未覆盖，原19图之外新增本版15图。

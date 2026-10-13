# Android 0.9.2 与 ECS 人物理解有效性修复

基线 `302ff4e90479318e11c345ee3e9a20e298b8cf6f`；继续 `codex/team-handoff-20261010` 和 Draft PR #89，不合并。安装与操作见 [0.9.2 使用说明](ANDROID_092_QUICK_START.md)。

## 两项问题与修正

**人物理解过度失效。** 旧实现把人物材料与授权记录混在同一个持久版本中，新建一次问答同意就会让已核对理解变成 stale。现在人物材料版本独立保存，在线读取仍检查权限；模型调用前后继续比较包含授权的完整版本。旧 hash 仍失效，不能自动恢复确认。兼容规则及真实样例复核见 [接口提案](../architecture/profile-material-version-proposal.md) 和 [后台修复记录](PROFILE_VALIDITY_FIX_2026-10-11.md)。

**Android 15 页面重建白边。** 故障时 Compose 根视图被系统默认 inset consumer 缩为 y=128、height=2209，窗口本身为 2400 高。修复仅在 API 35 补回布局标志，让背景覆盖系统栏；交互内容仍由 Compose 保留安全间距，没有隐藏状态栏或导航栏。该判断来自实测视图树及 [Android 15 PhoneWindow 源码](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-15.0.0_r1/core/java/com/android/internal/policy/PhoneWindow.java)，并遵循 [Android edge-to-edge 指南](https://developer.android.com/develop/ui/views/layout/edge-to-edge)。失败快照与尝试记录保留，没有对截图修图。

## 后台与模型实际结果

- SQLite 完整后端回归 474 passed、6 skipped；ECS 独立 PostgreSQL 库 99 passed。
- 独立审查后补齐的边界集在两种数据库各 13 passed，与上述测试有重叠，不相加。
- 三次新增问答同意后，2 项已确认理解仍有效。模型进行中新增／撤回授权、撤分享、改来源、删记忆、确认其他候选均不能发布旧结果。
- 真实 DeepSeek 生成 3 项候选，技术复核确认 2 项，拒绝 1 项过度归纳；保留 5 项历史 stale 与原拒绝记录。
- “喝茶口味”真实问答返回 ORIGINAL 并能定位原文。“留着旧杯子”的问题返回 UNKNOWN，登记为未解决的回答质量问题，不能写成全部问答正确。
- 记录者 10 段、亲友 8 段；亲友请求私密原音和所有者候选接口均返回 404，叙事来源也排除私密段落。

## Android 验证

使用 Android 15 模拟器，最终签名 internal APK，真实 ECS 数据。具体版本、哈希、单元测试、100%／200% 字号和重建检查结果见 [发布清单](PROFILE_ANDROID_RELEASE_2026-10-11.json)，界面见 [截图与日志](screenshots/profile-validity-20261011/README.md)。

| 检查 | 结果 |
|---|---|
| Android 单元测试 | 79 通过，无失败／跳过 |
| 记录者 100% 字号 | 77.921 秒，通过；10 段录音 |
| 亲友 100% 字号 | 47.661 秒，通过；8 段录音 |
| 记录者 200% 字号 | 62.046 秒，通过；10 段录音 |
| 100% 字号连续重建 3 次 | 14.811 秒，通过 |
| 200% 字号连续重建 3 次 | 14.771 秒，通过 |

APK 为 `0.9.2-internal`（20261016），163301982 字节，SHA-256 为 `ceb40714e156ce84ec207a0888ff5bec71e5386356f1edab177c0c3f583b7396`。签名证书 SHA-256 仍为 `9c99b41e65d934bd0dee3b111543266404b49fb7d799d43c23eb82f46d8e2f75`，已执行签名验证。

记录者和亲友的集成场景覆盖：进入各自可见花田、花瓣、实际原音播放、返回原位置、列表、查找、四视角、左右分页、八侧面和录音库。记录者还打开当前有效的“喝茶口味”理解与原文依据；亲友清除客户端模型再重建后仍恢复选定空间和 reader 身份。

记录者短录音检查只覆盖模拟器采集、暂停、继续、保存，没有上传这段短音频；不冒称新的真人转写验收。100% 与 200% 字号各连续重建 3 次，检查根视图背景仍覆盖完整窗口、空间和角色不变。

第一次亲友测试因权限定期刷新改变搜索按钮文字，自动测试定位失败。改用同时识别正常／忙碌状态的稳定选择器后再测；没有关掉权限同步，没有跳过搜索结果断言。失败日志仍保留。

## ECS 部署、兼容与回退

2026-10-11 12:48:42（北京时间）切换到 `/opt/remember-me/releases/paired-profile-material-20261011`。只替换 access、profiles、profile_relations 及两个 API 文件。API、AI、worker、profile 四项服务 active，数据库与原音存储就绪。

切换前备份数据库、32 个音频对象和配置；在独立数据库恢复并验证音频哈希、迁移版本。迁移仍为 `0016_share_invitations`，没有新增迁移，也没有修改模型、网络、注册、证书或同机其他服务。配置和备份仅存受限服务器目录，未进入仓库。

上一个应用目录 `/opt/remember-me/releases/garden-password8-c0e7a0f6` 保留。应用回退应先暂停新任务，原子恢复 current 链接，按部署说明重启四项服务并检查 ready；不要覆盖当前数据库或原音。旧代码不认识新材料 hash，会保守显示 stale，不能自动把候选标回有效。

旧 APK 也能受益于后台修复；系统栏修正需安装 0.9.2。源文件摘要见 release 附件，部署与源码一致性按五个文件的规范化换行 SHA-256 检查。

## 本轮未覆盖

完整 60 问、TTS／ASR 重跑、完整邀请和断网矩阵、新版实体手机、横屏／三键导航／多窗口、完整 TalkBack 与 iOS 未验收。现有中文语义归纳仍需核对；亲友可见材料的独立人物归纳、事件级独立支持判断、更多自然叙述式回答继续待做。

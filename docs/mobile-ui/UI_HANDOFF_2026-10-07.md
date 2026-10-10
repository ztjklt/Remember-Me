# UI 改进汇总与选取说明

> 2026-10-10 新增：[Android 0.8.0 原生花田、花瓣与设置](../agent-loop/ANDROID_GARDEN_DELIVERY_2026-10-10.md)，附新APK与15张实跑截图。下文仍描述10月7日；网页自由拖动与连续镜头未全部移植。

2026-10-07 · Remember Me / 勿忘我

这份交付用于集中查看并选取 Anker 工作区的 UI 改进。它是独立的设计候选分支，基于当天核对的 `origin/develop`（`4dc3d5a3f1d29ede9299259186b7b4aeb3421731`）。后端开发继续使用原来的分支与接口，本分支不会自动合并到 `develop` 或 `main`。

## 本次改进

| 方面 | 具体变化 | 可选范围与入口 |
| --- | --- | --- |
| 自然视觉 | 天空草地、湖畔、林间、海边夕照；低饱和雾蓝、苔绿、暖米色；页面留白与统一圆角 | Android / iOS 自然风格，网页 `nature/` |
| 品牌 | 参考真实勿忘我的五瓣、黄眼和曲线枝叶；浅色、深色、单色标记与字标 | `assets/brand/forget-me-not/v2/`；双端内置标记 |
| 导航与组件 | 常驻胶囊底栏、选中块滑动、按压反馈、页面渐变、字体/元信息/状态色分层 | 双端 UI 源码；网页组件页 `prototype.html#system` |
| 记忆花园 | 花丛 → 一组相关回忆 → 一个花瓣；拖动缩放、搜索、筛选、列表回退与分丛分页 | 网页 `memory-garden/`；尚未移植到原生端 |
| 花园动效 | 固定世界中的镜头聚焦；花朵与花瓣共用 620 ms 节奏；同源花瓣背景、反向返回、快速打断续接 | `camera.js`、`petal-motion.js`、`depth.js`；以实际文件为准 |
| 立体与环境 | 侧视花朵、写实枝叶、四种花园背景、夜景微光、首页缓慢云层 | 网页 2.5D 视觉，不是完整 3D 建模；可暂停并减少动态 |
| 透明材质 | 标签、底栏、首页卡片和详情页共用环境透色；录音播放器、提示框、编辑区、底部操作区补齐 | `nature/material-v22.css` + `nature/material-pages-v23.css`；文字保持清晰 |
| 意象体验 | 固定 3:2 的温暖回忆画风，来源查看、预览、采用/隐藏与图文音阅读 | 网页预生成示例；不代表已调用实时生图服务 |

## 三组提交如何选取

1. **Android UI**：`apps/android/app/src/` 下的设计系统、展示页面、导航和图像资源。录音/转写/整理 Repository、ViewModel、网络和 SDK 适配器不在这组变更中。
2. **iOS UI**：`Views.swift`、`BotanicalBrandGeometry.swift` 和 `Assets.xcassets`。API Client、Store、录音服务、配对配置与声音服务不变。
3. **网页设计包**：`docs/mobile-ui/` 和 `assets/brand/forget-me-not/`，包括自然背景、品牌、花园、材质、示意图、历史对照和对应验证资料。该组可独立用于设计评审。

三个提交分别只触及上述目录，可按客户端逐项采用。共享页面文件若在你的工作分支已有修改，应挑选所需样式或处理 cherry-pick 冲突，避免整份文件覆盖。图库、CSS、JS 是配套资源，单独复制 `prototype.html` 不够。

原生分组提交：Android `279a8f6`，iOS `82fa7e8`；网页分组为本分支的 `style(web): package memory garden and translucent UI for review` 提交。可以只取其中一组，无需合并整条分支。

**两端的完成程度不同：** 原生视觉主要是自然风格 v7–v9 与品牌 v2；网页是花园 v21、玻璃 v22.1 加全页面材质补齐。网页中的花园递进、同源花瓣镜头和微光并未据此自动进入 Android/iOS。

## 与后端的边界

- 本次没有 `services/`、`packages/contracts/`、`infra/`、数据库迁移、API 字段、模型配置或供应商密钥变更
- 不上传 Anker 本地工作台 `services/memory-workbench/`、SQLite、用户输入记录、缓存或处理结果
- 从交付副本移除了本地 `/workbench` 接线；保留其全页面材质改进，并独立保存为 `nature/material-pages-v23.css`
- 静态样板不采集麦克风、不请求模型、不连接后端，不能把它的模拟进度当作真实处理成功
- 花园内 15 个记忆点来自虚构示例稿，3 段 MP3 是已有合成演示音频；随包保留原稿和素材来源，不含用户的真实录音
- 保留录音与声音克隆分别授权、原话依据、失败提示等既有产品语义

## 预览和检查

从仓库根目录执行：

```powershell
python -m http.server 8773 --bind 127.0.0.1
```

打开 `http://127.0.0.1:8773/docs/mobile-ui/prototype.html?demo=1#archive`。不需要安装或启动后端。对照首页用 `#home`，组件页用 `#system`；去掉 `demo=1` 可以看到仅用于评审的尺寸/主题/大字/减少动态设置。

历史迭代文档保留了当时状态；本文件和本次 PR 是 2026-10-07 的同步范围说明。原始开发目录仍保留完整本地实验，提交副本只包含 UI。

## 本次验证

- 网页：`node --test docs/mobile-ui/memory-garden/*.test.cjs`，31/31 通过；包括镜头轨迹、连续交接、缩放、来源匹配与 302 条记忆的分页增长
- Android：使用本机缓存的 Gradle 8.9 执行 `test assembleDebug --offline --console=plain`，Debug / Release 各 18 项测试通过，APK 构建成功；构建使用仓库已有的 Sherpa AAR，未更换依赖或构建配置
- iOS：当前环境为 Windows，未运行 Xcode 构建或真机检查
- 浏览器：交付副本已验证花丛 → 花朵 → 花瓣阅读路径，资源正常加载、无 JS error / warning；播放器和阅读材质保持环境透色，并补正播放图标的前景对比。截图见 [交付预览](media/ui-handoff-20261007.png)
- 原生真机、真实模型和录音设备 SDK 的链路不属于本次 UI 提交验收

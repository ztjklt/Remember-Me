# 勿忘我 · 移动端 UI 实施包

本包已完成第二轮视觉调整：雾银底色、勿忘我蓝、声音刻线；包含可点击原型与 Android 实现。视觉参考和取舍见 [VISUAL_V2.md](VISUAL_V2.md)。iOS 对齐单独保存在 `codex/ios-ui-alignment` 分支，不能把两个平台分支整体互相合并。

## 打开与检查

- [交互原型](prototype.html)：纯 HTML，固定示例资料，不采集声音、不发送资料。可切换 Android / iOS、浅色 / 深色、200% 文字、减少动态，以及空 / 处理 / 失败状态。
- [设计规格](DESIGN.md)：导航、页面、组件、状态与后续功能边界。
- [验证记录](VALIDATION.md)：已跑检查、真实能力限制、设备验收步骤。
- [设计令牌](tokens.json)、[颜色检查结果](contrast-verification.json)、[原型检查结果](prototype-verification.json)。

可直接打开 HTML；也可以在仓库根目录运行 `python -m http.server 8768 --bind 127.0.0.1`，打开 `http://127.0.0.1:8768/docs/mobile-ui/prototype.html`。

## 实施基线

| 工作线 | 固定基线 | 本地目录 / 分支 |
|---|---|---|
| Android | PR #78，`f63f7efbe1f9b1cb438e80d230a29861c4b5c04c` | `D:/codex_work/remember-me-ui` / `codex/mobile-ui-core` |
| iOS | PR #77，`e146ac56f080299676fed40653394b97a37bd270` | `D:/codex_work/remember-me-ios-ui` / `codex/ios-ui-alignment` |

原仓库是 `ztjklt/Remember-Me`；#78 来自 fork 并不意味着原仓库迁移。两条 UI 工作线均没有合并上游 PR，也没有部署或发布。当前“饮食程序开发”目录未用于本次实现。

## Android 实现入口

`MainActivity → MobileViewModel → MobileApp`。

- `feature/MobileScreens.kt`：今天、档案、我的、独立录音、真实播放器、核对与来源详情。
- `feature/MobileViewModel.kt`：生命周期内可观察状态、按录音防重复操作、播放协调。
- `data/repository/RecordingWorkflow.kt`：本机转写 → 保存机器原文 → 保存核对版本 → 明确授权后调用注入的整理适配器。
- `data/repository/RecordingMetadata.kt`：旧 sidecar 兼容、独立核对字段、处理阶段、中断恢复。
- `AndroidAudioCaptureService.kt`：真实电平、计时、暂停、完成、播放、定位、原子写入、档案更新。
- `core/designsystem/Theme.kt`：统一语义色、系统字体、字号、圆角和深色模式。

旧演示页面和 mock repository 仍保留用于已有预览 / 回归测试；正常入口不引用它们。原有供应商适配器文件仍在，但正常入口不实例化；构建不再把客户端供应商密钥嵌入 BuildConfig。

## 当前可用性

Android 可录音、保存、回听、按标题 / 转写 / 记忆搜索、核对文字和展示已有记忆来源。构建得到的 APK **没有语音模型权重**，本机转写会清楚显示不可用；录音与播放不受影响。整理适配器默认未配置，所以不会出现假记忆，也不会在核对前上传文字。

`ReviewedMemoryProcessor` 是接入点。后续正式适配器应提供真实资料去向说明和 `organize(confirmedText)` 实现；本轮只用测试适配器验证成功、失败和重试。供应商 / 共享后端路线仍按原方案另案处理。

iOS 保留 #77 已有的配对 Mac、转写核对、记忆纠正、Twin、校准和独立声音授权能力；本次没有替换它的服务链路。详见 iOS 分支的 `apps/ios/UI_ALIGNMENT.md`。

## 后续使用

先在 Android 真机上完成 [验收清单](VALIDATION.md)，再决定接入正式整理服务与扩展后续功能。原型模拟状态、单元测试、语法检查不能替代真机视觉、麦克风、播放和读屏验证。

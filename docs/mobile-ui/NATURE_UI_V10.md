# v10 · 花瓣、材质与反馈

2026-10-02。本轮承接已认可的 v2 品牌，范围是**本地网页设计样板和技术参考**。没有新增原生客户端行为、修改业务 Contract、调用收费服务或发布。

## 可体验的结果

1. [花瓣与光](../../assets/brand/forget-me-not/procedural/preview.html)：可调弧度、细脉和光照的 2.5D 勿忘我；浅深色、柔和/细腻/平面光预设，附真实花形参考。公式、源码与复用边界见其 [README](../../assets/brand/forget-me-not/procedural/README.md)。
2. [手机组件样板](prototype.html#system)：植物实验入口、主动试听按钮、实色底栏偏好；底栏在此页也保持可用。
3. 原型各页：110 ms 按压反馈，160/240 ms 弹窗过渡，原有常驻底栏和分栏过渡保留；列表、正文、编辑器、播放器采用实色阅读底。
4. 底栏：高不透明度磨砂层、细边光和柔和阴影。只是 CSS 的材质近似，**不是 Apple 原生 Liquid Glass 的折射/融合实现**。
5. 声音：仅点“试听轻提示音”创建两枚短正弦音，不自动随导航、保存或录音播放；试听期间禁用按钮，录音开始或页面隐藏时停止。操作的含义仍由文字和视觉状态表达。

## 采用哪些现有组件

| 需求 | 已核对的原始来源 | 适合迁移的内容 | 对 Remember Me 的取舍 |
|---|---|---|---|
| Android 底栏与自定义品牌 | [Compose Samples / Jetsnack](https://github.com/android/compose-samples) | 自定义设计系统、布局、底栏动画；Apache-2.0 | 延续 Compose，复用组件结构和状态方式，不迁移成 React Native |
| Android 音频内容 | [Compose Samples / Jetcaster](https://github.com/android/compose-samples) | Podcast 播放内容布局、主题、WindowInsets | 参考播放器层级和媒体控制，业务仍接现有录音/播放状态 |
| Android 列表和响应式导航 | [Compose Samples / Reply](https://github.com/android/compose-samples) | Material 3、列表、不同屏幕导航 | 为后续大屏适配保留依据，不把邮件产品结构直接套入记忆产品 |
| Android 点击反馈 | [Compose interactions](https://developer.android.com/develop/ui/compose/touch-input/user-interactions/handling-interactions) | Button/Modifier.clickable、InteractionSource、按压/焦点/涟漪状态 | 原生端优先复用系统语义；按压和取消都要结束反馈 |
| iOS 自然内容与玻璃导航 | [Apple Landmarks](https://developer.apple.com/documentation/swiftui/landmarks-building-an-app-with-liquid-glass) | SwiftUI 官方完整示例 | 按系统版本使用原生组件和可用 API，旧系统保持标准 Material；本轮未移植新 API |
| 玻璃使用边界 | [Apple Materials](https://developer.apple.com/design/human-interface-guidelines/materials)、[Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/) | 控制/导航层与内容层区分，避免叠层玻璃，尊重辅助功能 | 导航有材质，正文有稳定底色；减少透明度/更高对比度自动实色 |
| 触觉 | [Apple Playing haptics](https://developer.apple.com/design/human-interface-guidelines/playing-haptics) | 与明确语义事件对应的触觉反馈 | 作为原生后续项；网页没有用 vibration 冒充 iOS 触觉，也未新增手机震动 |

以上为截至 2026-10-02 阅读官方文档/仓库得到的参考。没有安装这些示例工程，没有复制第三方代码。UI/UX skill 给出的通用棕色/紫色配色及外部字体建议不适用已确认品牌；保留苔绿、雾蓝、暖金和本机中西文字体，只采用其可读性、状态和动效检查建议。

## 本项目的具体规则

- 用一级标题、正文、日期/来源、状态标签四层层级；标题克制使用衬线，操作和长文保持系统字体。
- 状态同时提供文字和图标；灰色不承担“等待”“失败”“已完成”的全部差异。
- 移动点击区域至少 48 CSS px；按压不改变周围布局，动效不阻塞下一次操作。
- 玻璃只服务底部导航。列表、转写编辑、记忆原文、来源信息均用稳定阅读底。
- 保留 `prefers-reduced-motion`、原型减少动态开关、`prefers-reduced-transparency`、更高对比度与实色回退。
- 音效默认安静、按需试听；原生若接入则单独评估静音设置、触觉偏好和录音会话，不能把试听代码直接搬到录音链路。
- 小 logo 强调轮廓辨识；大插画才展示细脉。避免把复杂花瓣计算应用到每个列表图标。

## 验证记录

- Node 对 `flower.js`、`feedback-v10.js`、导航脚本和两页内联脚本语法检查通过。
- 完成后再次检查内联脚本及 `git diff --check`；通过。花瓣页与手机原型浏览器 warning/error 日志均为空，花瓣页图片均成功载入。截图：[花瓣样板](../../assets/brand/forget-me-not/procedural/preview-light.jpg)、[手机组件](media/nature-v10-components.jpg)。
- 浏览器实际运行 WebGL（`data-renderer=webgl`），预设切换及键盘调光已验证；不是只验证 HTML 返回 200。
- 花瓣页在实际 **1910 × 1075** 桌面视口和 **376 × 821** 手机视口均正常渲染、无横向溢出；手机切换为单列，浅深色与三种预设可用。WebGL 丢失/不可用回退已实现，但本轮未注入 GPU 故障来实测。
- 手机原型实际视口 **376 × 821 CSS px**：组件页普通模式、深色 + 200% 字号 + 减少动态组合；页面及内部阅读区无横向溢出。档案分栏切换正常，减少动态时无过渡克隆残留。
- 模拟“开始录音 → 授权弹窗 → 同意 → 完成保存”通过；弹窗可见、初始焦点正确，`sheet-enter` 样式生效。这是原型状态验证，不是真实录音/处理链路。
- 主动试听返回成功状态，按钮短暂禁用并恢复；未进行扬声器听感或手机音频会话验收。
- 当前浏览器媒体偏好 `prefers-reduced-transparency: reduce=true`，已实测自动实色回退；普通玻璃路径由 CSS 和保守对比计算检查，尚未在取消此系统偏好的设备上视觉验收。
- 底栏次要文字与最不利的纯黑/纯白背景合成计算：浅色 **5.61:1**，深色 **6.18:1**；这不是实机截图的逐像素检测。
- Android/iOS 本轮没有源码变化，因此没有重跑原生构建；真机材质、触觉、刷新率与新插画的原生迁移待后续验证。

代码：`nature/refinement-v10.css`、`nature/feedback-v10.js`、`nature/navigation-v9.js` 的组件页底栏开关、`prototype.html`；品牌实验在 `assets/brand/forget-me-not/procedural/`。v1/v2 原始品牌资产均保留。

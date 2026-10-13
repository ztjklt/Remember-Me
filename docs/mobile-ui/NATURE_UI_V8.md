# 每一页，都有风景 · 本地第八轮

2026-10-02。用户认可 v7 首页背景，并要求其他页面也有不同但统一风格的背景。本轮延续本地分支 `codex/nature-mobile-ui`，没有提交、推送或发布。

## 页面分配

| 页面语境 | 背景 | 接入范围 |
| --- | --- | --- |
| 今天 / 首页 | 原有天空草地 | 网页、Android、iOS |
| 档案、图谱与模型 | 新增湖畔 | 网页档案/组件页、Android 档案/图谱、iOS 档案/模型 |
| 录音、原音详情、核对与记忆详情 | 新增林间小径 | 网页、Android、iOS；Android 助手页也使用此场景 |
| 对话、我的与个人声音 | 新增海边夕照 | 网页、Android 对话/我的、iOS Twin/我的/声音设置 |

使用统一的自然摄影质感、柔和光线和奶白/苔绿界面。首页与录音的风景更清晰，阅读页面叠加较厚蒙层；列表、编辑框、授权提示保留实色或接近实色的表面。深色模式继续使用深绿蒙层。网页与 iOS 高对比度模式隐藏装饰背景；减少透明度保留风景并使用实色卡片。

Android/iOS 通过 `NatureScene` 显式指定每个页面的资源，避免散落图片路径。iOS 档案的列表与记忆子页共用父级背景，避免重复绘制。Android 普通文字跟随语义前景色，并让对话页复用已有底部导航，以保持背景上的可读性和系统栏避让。

没有修改录音、转写、数据保存、授权、搜索或模型服务逻辑；场景图片不是处理模式。浏览器仍使用固定示例，不代表真实录音或 AI 已接通。

## 查看

- [交互预览](http://127.0.0.1:8771/docs/mobile-ui/prototype.html?v=8)：切换档案、录音、核对、记忆、我的，iOS 模式下还可从底栏进入对话。
- [三场景对照](nature/gallery-v8.html)：实际网页截图，非原生截图。
- [素材与完整生成提示词](nature/GENERATION_V8.md)：内置 imagegen，三个原始 PNG 已复制进三端资源。

## 验证记录

- Android：`D:\viberoom\android-env\gradle-8.9\bin\gradle.bat -p apps\android test assembleDebug --offline --console=plain` 成功。Debug / Release 各 18 项现有单元测试，无失败。日志在 `output/playwright/android-build-v8.log`。
- 网页：原有录音确认、暂停/继续、保存、核对、整理确认、删除示例记忆和搜索流程通过；无页面脚本错误。
- 布局：360/412 Android、375/430 iOS，普通浅色与 200% 字号深色；七页共 56 组，未发现横向溢出或操作区超出视口。已加入对话页。结果在 `nature/browser-verification-v8.json`。
- 已实际打开并截图档案、录音、核对、记忆、对话、我的及深色“我的”；高对比度下背景隐藏已检查。截图在 `media/nature-v8-*.png`。
- 用户当前的内置浏览器已刷新，并打开湖畔背景的档案页进行目视核对。
- 三套新增资源逐文件核对，三端对应副本 SHA-256 一致；iOS Asset Catalog JSON 能解析且所引用文件存在。

原生视觉验收仍待设备完成。当前 Windows 环境未编译 iOS，也未运行 Android 模拟器；v7 记录的模拟器启动审批限制未再次尝试绕过。网页布局通过不能替代原生设备验收。

## 本地文件

Android 安装包：`apps/android/app/build/outputs/apk/debug/app-debug.apk`。新素材在 `docs/mobile-ui/nature/`、Android `drawable-nodpi/` 及 iOS `Assets.xcassets/`；不是只留在生成器目录。

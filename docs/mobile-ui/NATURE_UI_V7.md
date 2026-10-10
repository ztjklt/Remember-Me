# 自然风景 UI · 本地第七轮

> 本轮为历史记录；用户随后要求扩展其他页面背景，当前版本见 [v8](NATURE_UI_V8.md)。

2026-10-02。用户提供草地、天空、云朵与玻璃界面的截图，希望 Remember Me 更清新、放松，适合 Android / iOS。工作分支 `codex/nature-mobile-ui`，基线 `4dc3d5a`。本轮仅在本地修改，没有提交、推送或发布。

## 设计落地

- 首页是一扇可以停留的窗：原创草地天空、较大的留白、两行柔和标题「让此刻，慢慢留下来」。保留勿忘我花朵标识。
- 主操作使用苔绿色圆角按钮。独处、讨论、闲聊是录音场景的邀请文案，不代表新增了三套音频处理模式。
- 内容使用奶白色卡片；长文、核对文字和档案保持稳定的实色阅读区域。深色模式使用深林绿蒙版。
- Android 首页取消原来的分类矩阵、无操作的导出按钮、未实现的画像搜索和随机轮换话题，突出真实录音与档案入口；五个原有底部目的地继续保留，标签改成中文竖排图文，补齐系统栏避让。
- iOS 首页保留真实记录、草稿继续入口、问题回答和原有四栏导航，调整自然背景、标题、卡片和语义色。录音前/录音中显示风景，进入草稿和核对文字时回到稳定阅读底色。
- 风景为静态本地图片，没有循环装饰动画或网络图片请求。网页/iOS 的高对比度模式移除风景；减少透明度保留风景、采用实色卡片。Android 高对比度下的最终像素效果仍需设备检查。

## 使用与范围

在仓库根目录运行 `python -m http.server 8771 --bind 127.0.0.1`，打开 [交互预览](http://127.0.0.1:8771/docs/mobile-ui/prototype.html)。可以切换平台、深色、200% 文字和内容状态。

浏览器预览使用固定示例，录音、转写和整理都是状态演示，不调用麦克风或云端。它覆盖核心记录流程；Android 原生五栏导航与预览的精简导航仍有差异。浏览器截图不是原生手机截图。

原生录音、权限、保存、核对、整理授权与持久化逻辑未改动。Windows + Android 的真实模型接线和现场完整链路仍按工作区黑客松计划推进，不能用本轮视觉验证替代。

## 本次验证

| 检查 | 结果与边界 |
| --- | --- |
| Android `test assembleDebug` | 成功；Debug / Release 各 18 个现有单元测试，均无失败；生成 `apps/android/app/build/outputs/apk/debug/app-debug.apk` |
| 最终 Android 命令 | `D:\viberoom\android-env\gradle-8.9\bin\gradle.bat test assembleDebug --offline --console=plain`；日志 `output/playwright/android-build-v7.log` |
| 交互预览回归 | 录音确认 → 暂停/继续 → 保存 → 核对文字保存 → 授权整理 → 删除示例记忆 → 搜索；通过，无页面脚本错误 |
| 网页布局 | 360 / 412 Android、375 / 430 iOS，普通浅色和 200% 字号深色，首页/录音/档案/核对/记忆/我的，共 48 组；未发现横向溢出或操作区超出视口 |
| 语义色与 iOS 资源 | `python docs/mobile-ui/verify-design.py --ios-root .`；最低检查对比度 5.69:1；不代表风景背景每个像素的对比度或原生系统验收 |
| Android 模拟器 | 启动命令被自动审批策略阻止，工具未返回具体原因；未绕过，也未声称模拟器/真机验收 |
| iOS | 更新 SwiftUI 与 Asset Catalog；本机 Windows，未运行 Xcode 编译或 iPhone 验收 |

回归原脚本为 `verify-prototype.js`；本次拷贝到忽略目录 `output/playwright/verify-nature.js`，只把测试地址从 8768 改为 8771。完整结果在 `nature/browser-verification.json`；截图见 `media/nature-v7-home.png`、`media/nature-v7-record.png`、`media/nature-v7-dark.png`（均为网页）。

## 背景素材与生成记录

通过内置 `imagegen` 生成；没有使用付费 API CLI，也没有裁切用户截图。素材大小 1,950,359 bytes。三端使用同一份原图，均已复制到仓库，不依赖临时目录：

- 网页：`nature/meadow-v7.png`
- Android：`apps/android/app/src/main/res/drawable-nodpi/rm_meadow_v7.png`
- iOS：`apps/ios/RememberMe/Assets.xcassets/RmMeadow.imageset/meadow-v7.png`

最终生成提示词：

> Create an original mobile app background artwork for Remember Me, a personal audio memory journal. Use case: stylized-concept. Portrait composition 9:16, no UI and no text. A tranquil open countryside with gently rolling fresh green grass hills across the lower 40%, distant very small woodland at horizon, expansive soft clear blue morning sky in upper 60%, a few luminous creamy white cumulus clouds mainly near the outer edges. Warm soft early sunlight from upper left, fresh light green highlights, natural depth with airy atmospheric perspective. Dreamy but realistically rendered landscape, soft tactile grass, serene and inviting, understated cinematic quality, pastoral reverie, no oversaturated neon colors, no dark dramatic mood. The upper center should be softly blue and relatively uncluttered to support dark mobile UI text, the bottom foreground softly shaded green for pale panels. No people, buildings, roads, objects, logos, letters, borders, device mockups or watermarks. Background must fill the whole canvas.

## 接下来验收

优先在现场计划使用的 Android 手机上安装本地 APK，检查首屏留白、系统栏、深色模式、字体放大，以及录音暂停/保存和返回档案。iOS 在 Mac 上构建后检查同一组视觉状态。确认风格后，再用真实音频完善处理链路与演示素材。

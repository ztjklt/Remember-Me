# 勿忘我 · 留声品牌资产 v1

本资产包以用户选定的 C「留声」为基础：五瓣蓝花、轻微旋转的圆润花瓣、小金色花心。它是一个独立组件包，尚未替换 Android / iOS 的应用图标、已有首页或导航。

## 内容与来源

- `svg/mark-material.svg`：可编辑的立体渐变版，透明背景；建议显示尺寸 ≥64。
- `svg/mark-flat.svg` / `mark-flat-dark.svg`：浅色 / 深色背景上的双色简化版，适合 16–48。
- `svg/mark-mono.svg`：单色版；内联 SVG 的 `currentColor` 可随上下文变化，作为 `<img>` 时不继承外部颜色。Web 组件使用 CSS mask 处理颜色继承。
- `svg/app-icon-light.svg` / `app-icon-dark.svg`：全出血方形图标，背景不透明，没有烘焙圆角。系统负责裁切；花形缩至安全区域内。
- `svg/app-foreground.svg`：留有相同安全边距的透明前景，供 Android adaptive icon 接入。
- `exports/`：上述矢量资产由浏览器直接渲染出的 PNG，不是从概念图裁剪，也不含文字。1024 图标用于后续平台资源生成；不是已安装的应用图标。
- `remember-me-brand.js`：可直接使用的 Web Component，无外部依赖。
- `adapters/`：Compose / SwiftUI 接入文件；复制到对应客户端后再接入资源与原生构建。未自动加入原生工程。
- `preview.html`：浅深色、尺寸、版本、标题组合、首页顶栏和空状态的交互预览。
- `build_assets.py` / `tokens.json`：轮廓及色彩的统一来源，重生成 SVG 的命令为 `python build_assets.py`。
- `provenance.json`：概念图与生成工具的来源记录。

生成流程：最初 C 方案由内置 imagegen 创建；另生成了透明花形候选，但候选边缘与安全留白不够稳定，因此没有把它直接作为 UI 成品。当前交付为基于 C 方向、用共享轮廓和受控渐变重绘的矢量版本，**不是对概念图的逐像素复刻**。三种版本共享同一条花瓣路径及 5 个旋转角度；Android / SwiftUI 的简化路径与之对应。

## 用法

```html
<script type="module" src="./remember-me-brand.js"></script>
<!-- 默认无文字时是装饰；旁边已有“勿忘我”无需重复朗读 -->
<remember-me-brand size="28" variant="flat" wordmark></remember-me-brand>
<!-- 独立、有意义的品牌图像需要名称 -->
<remember-me-brand size="96" variant="auto" theme="dark" label="勿忘我"></remember-me-brand>
<!-- 使用当前文字颜色 -->
<remember-me-brand size="24" variant="mono" style="color:#325CCB" label="勿忘我"></remember-me-brand>
```

`size` 是总画布宽高，范围 16–512，实际花形有内置留白。`auto` 在 64 以下使用简化版，其余使用立体版。`theme="dark"` 使用适合深底的简化颜色，组件不会自己画背景。`wordmark` 使用可缩放系统文字，不包含字体文件；可用 `--rm-brand-wordmark-size` 和 `--rm-brand-ink` 调整字号、文字色。

Compose：复制 `adapters/RememberMeBrand.kt` 到设计系统目录，将 `exports/mark-material-1024.png` 命名为 `rm_brand_material.png` 放入 `res/drawable-nodpi/`：

```kotlin
RememberMeBrand(size = 96.dp, materialPainter = painterResource(R.drawable.rm_brand_material), label = "勿忘我")
RememberMeBrand(size = 24.dp, treatment = BrandTreatment.Monochrome)
```

SwiftUI：把 `adapters/RememberMeBrand.swift` 加入目标，把 PNG 放入 `RmBrandMaterial` Image Set（按原色渲染）：

```swift
RememberMeBrand(size: 96, materialAsset: "RmBrandMaterial", label: "勿忘我")
RememberMeBrand(size: 24, treatment: .monochrome)
```

两种原生接入文件在没有传入立体资源时回退为简化版，不发出网络请求。原生默认 `label=nil` 表示装饰；功能按钮必须由父控件提供自己的动作名称。品牌花形本身不承担点击操作。

## 使用规则

| 场景 | 版本 / 推荐范围 |
|---|---|
| App 图标 / 启动品牌展示 | 立体；图标使用专用全出血文件 |
| 首页短品牌介绍 | 立体 96–160；每屏最多一个主要花形 |
| 顶部标识 / 关于页面标题 | 简化 24–40＋可缩放文字 |
| 空状态 | 立体 64–96，配具体说明与实际按钮 |
| Android 通知 / 单色环境 | 单色；接入时按平台生成白色 alpha 资源 |
| 海报、介绍页、分享封面 | 优先 SVG；不从截图放大 |

外部留白至少约为画布边长的 1/8；保持等比缩放。不把花心改为红色录音灯，不把花瓣数量变为“完成度”，不把旋转花朵用作真实处理进度。录音、播放、成功状态继续使用功能图标和明确文字。

默认无常驻动画、无光斑粒子、无实时玻璃渲染。需要过渡时交由页面做短淡入；减少动态开启时立即呈现。不把三种版本当作三个不同 Logo。

## 预览与验证

在仓库根目录运行 `python -m http.server 8770 --bind 127.0.0.1`，打开 `/assets/brand/forget-me-not/v1/preview.html`。不需要安装 npm 包来使用组件。

浏览器验证包含浅深色、小尺寸、360 / 430 宽屏、200% 字体、导出 PNG 与无障碍名称；结果见 `verification.json`。原生接入文件的编译、应用图标系统遮罩、TalkBack / VoiceOver 实机检查须在正式接入时完成，不能由网页检查代替。

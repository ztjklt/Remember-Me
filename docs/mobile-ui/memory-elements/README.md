# 回忆图形组件 · Memory Leaves

本组件包包含六个原创图形：留声 voice、片段 archive、花笺 memory、原话 quote、核对 review、回望 recall。它们是应用内的辅助图形，不替换蓝花 Logo、启动图标或录音/删除等标准操作图标。

## 视觉规则

- 同一 96 单位网格，共用纸页形状、圆角、蓝灰色和小面积金色。
- 小尺寸去掉后层、阴影与渐变；大尺寸使用蒙版衰减后层、柔和投影、上方透光边缘。
- SVG 的蒙版和滤镜是可编辑真实结构；原生以同一轮廓实现分层和裁剪。Android 以少量偏移绘制近似柔影，SwiftUI 使用 Canvas shadow；三者不声称像素一致。
- 装饰不遮挡点击，不旋转、不呼吸、不充当电平或处理进度；默认对读屏隐藏。
- 图形需要承载独立含义时提供 label；按钮仍由父控件提供动作名称和足够触控面积。
- Web/iOS 减少透明度或增强对比度时退回简化轮廓；Android 不依赖透明玻璃或背景采样。

| 尺寸 | 默认表现 | 场景 |
|---|---|---|
| 16–32 | 单色轮廓 | 条目辅助标记；细节较多的花笺优先使用更大尺寸 |
| 33–63 | 双色 | 待处理入口、档案标题 |
| 64–192 | 蒙版/投影 | 空状态、小幅说明插图 |

`echo-pattern.svg` 为额外的静态回忆线纹：线条逐渐显现并消退，只以低透明度用于首页页眉背后。

## 使用

Web 无依赖，需通过 HTTP 访问 ES module：

```html
<script type="module" src="memory-elements/memory-glyph.js"></script>
<memory-glyph name="memory" size="88"></memory-glyph>
<memory-glyph name="quote" size="40" theme="dark" label="原话来源"></memory-glyph>
```

支持 name、size、theme(auto/light/dark)、treatment(auto/flat/duotone/material)、label。size 限制 16–192；未知 name 回退 voice。自动主题优先读取页面 data-theme，其次读取 .dark 或系统偏好。预览页可独立切换材质与尺寸。

Compose 使用 core/designsystem/MemoryGlyph.kt：

```kotlin
MemoryGlyph(MemoryGlyphKind.Memory, size = 88.dp)
```

SwiftUI 的可复制源文件为 MemoryGlyph.swift；当前应用的同一代码已生成到 Views.swift，避免漏加 Xcode target：

```swift
MemoryGlyph(kind: .memory, size: 88)
```

如复制为独立文件并跨文件引用，将 private 类型改为项目所需访问级别，并加入目标；不要同时保留两份同名声明。

## 生成与维护

原始轮廓在 build.py；36 个 SVG = 六款 × 浅深色 × 三种材质。catalog.json / catalog.js 与原生轮廓同源。

```powershell
python docs/mobile-ui/memory-elements/build.py
python docs/mobile-ui/memory-elements/build_native.py --ios-root D:/codex_work/remember-me-ios-ui
```

生成器仅使用 Python 标准库，无第三方代码依赖。修改轮廓后重新生成并检查两端，勿只修改某一导出。用户的 assets/brand/forget-me-not/v1 原始交付包保持不变。

## 搜索参考与取舍

以下是设计参考和机制资料，并未复制其中的路径、图片或品牌资产。本组由项目代码直接绘制，不是 AI 位图生成或来源图裁剪。

| 来源 | 采用的思路 / 边界 |
|---|---|
| [Phosphor core](https://github.com/phosphor-icons/core) 与 [duotone 示例](https://github.com/phosphor-icons/core/blob/main/assets/duotone/images-duotone.svg) | 主轮廓与次级面分层；小图仍需清楚 |
| [Iconoir](https://github.com/iconoir-icons/iconoir) | 系列图标的一致轮廓语言；不混用多套描边风格 |
| [Fluent System Icons](https://github.com/microsoft/fluentui-system-icons) | 组件库成套交付和平台适配组织 |
| [Fluent Emoji](https://github.com/microsoft/fluentui-emoji) | 比较不同图形表现形式；没有采用其角色或夸张立体表情 |
| [Material 早期图标设计说明](https://m1.material.io/style/icons.html) | 历史参考：纸面叠层、有限重叠、统一光源；不把 M1 作为当前平台硬性规范 |
| [Apple App icons](https://developer.apple.com/design/human-interface-guidelines/app-icons) | 系统启动图标与应用内插图的边界；本次不修改系统图标或重复烘焙其系统效果 |
| [MDN SVG mask](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/mask) | SVG 蒙版结构及遮罩机制 |

## 验证边界

Web 预览检查了六款图形、浅深色、24/48/96 尺寸、材质切换、尺寸切换、恢复默认、装饰语义和图片载入。Android 构建与测试、iOS 语法解析另见父目录 VALIDATION.md。未完成原生真机视觉验收，未测试所有辅助设置的系统级切换。

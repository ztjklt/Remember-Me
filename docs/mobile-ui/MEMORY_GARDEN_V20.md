# v20 · 薄暮里的记忆花园

2026-10-02。本轮把用户认可的层级与镜头节奏保留下来，改善花朵的视觉纵深，并提供三种静谧花园背景。

## 查看

- [三种光景并排比较](concepts/garden-light-v20/index.html)：池畔薄暮（默认）、暖色花径、林间微光，每张都可以进入完整交互原型
- [默认花园](prototype.html?demo=1&garden=pond#archive) → 雨夜，留着灯 → 借伞与回应，可查看侧视花形与花瓣展开
- [花丛截图](media/garden-clump-v20.png)、[单花截图](media/garden-flower-v20.png)、[阅读背景](media/garden-petal-v20.png)
- [本轮内置生图提示词与来源](nature/garden-v20/PROMPTS.md)

## 视觉与交互

生成了三张纵向花园背景、两种透明花朵视图。前后瓣缘、花萼、侧向花梗和微距明暗形成视觉上的立体感；使用图像分层与轻微远景视差，属于 2.5D 视觉方案，不是可以任意旋转的三维网格。两种花形交错使用，避免所有花正对观众。

枝干接在图片里的花萼或短花梗端点上，随花朵的角度、位置和缩放一起变化。叶脉增加暖色反光。图片中的五个花瓣区域继续对应既有分类；标签位置和镜头焦点使用同一套图像坐标，避免侧视花的点击位置与展开位置脱节。

花瓣展开继续使用同一图片，以该瓣为焦点靠近并渐变为阅读背景。进入、返回及中途折返仍共用 620 ms 的镜头曲线。转场快照冻结当时的云朵和微光位置，避免快照重新播放装饰动画。

花园背景与前景保持独立。边缘树木、低处花草、水面或小径提供环境；中央明暗较安静，文字区域有浅雾遮罩，标签、缩放工具和说明文字增加适量底色。背景选择位于「预览设置」，没有塞入正式 App 导航。对照页链接可指定 `garden=pond|path|woodland`；下拉选择会保存在本浏览器。

## 萤火虫层

九个远景微光点，约 0.8–1.55 CSS px，主要分散在草木边缘。每个点以独立的 17–34 秒轨迹小幅漂移，并在不同的 6.7–11.2 秒周期内短暂发光，有单闪与双闪，长时间保持暗淡。采用小范围暖黄光晕，不画星形、光线尾迹或规律光环。它们是环境装饰，不冒充新的记忆条目。

参考 [Xerces 的萤火虫介绍](https://xerces.org/endangered-species/fireflies/about) 与 [发光行为访谈](https://www.xerces.org/bug-banter/magic-of-fireflies-flashing-lights-glowing-worms-and-chemical-reactions) 中关于傍晚活动及不同发光方式的描述；本实现是视觉取舍，不模拟某个具体物种的闪光编码。

「暂停微光」可暂停位移与发光；减少动态时隐藏微光并关闭远景视差。后台及离开花园时暂停装饰动画。只动画 transform/opacity；鼠标视差按事件更新，触摸操作仍用于原有拖动与缩放。

## 验证

27/27 Node 检查通过：保留原有相机、手势、增长、原稿追溯及意象选择检查，新增透明素材、五瓣映射、侧视图焦点/标签一致性与旋转缩放后的花梗接点检查。

```sh
node --test docs/mobile-ui/memory-garden/botanical-v20.test.cjs docs/mobile-ui/memory-garden/petal-motion.test.cjs docs/mobile-ui/memory-garden/camera.test.cjs docs/mobile-ui/memory-garden/depth.test.cjs docs/mobile-ui/memory-garden/garden.test.cjs docs/mobile-ui/memory-garden/imagery.test.cjs
```

浏览器实测两种花形、下方花瓣、展开/收回、中途返回、三种背景切换、暂停/恢复微光。采样的花瓣动画均为 620 ms，源/目标图片相同，结束矩阵与实际目标的最大分量差小于 0.001；结束后临时转场层为 0。实际观察到不同微光的非同步透明度与位移变化。

358 × 843 CSS px 窄屏深色、200% 文字、减少动态下：document 358/358、内容区 343/343（clientWidth/scrollWidth），无横向溢出；微光隐藏，背景 transform 为 none。大屏内容区为 988/988。检查时测试页控制台无 error/warn。临时主题及视口检查已复原。

轨迹与布局证据：[garden-motion-v20-verification.json](media/garden-motion-v20-verification.json)。这些结果不代表 Android/iOS 真机帧率验收。

## 范围

仅更新本地网页、设计素材和交接文档，未提交、推送或部署；未改 Android/iOS、本轮未改共享 Contract。背景与花朵均为提前生成的装饰图片，分类仍为三组、15 个示例记忆。实时记忆生图、真实录音链路及 Windows + Android 实机体验仍需各自接入与验证。

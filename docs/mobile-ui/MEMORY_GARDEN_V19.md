# v19 · 走近一片真实的花瓣

2026-10-02。本轮按用户反馈修订本地网页：花瓣转场与花丛转场同速，使用生图素材改善符号化的瓣形。

## 可查看的结果

- [花园入口](prototype.html?demo=1#archive) → 厨房里的往事 → 妈妈的小本子
- [单花截图](media/garden-flower-v19.png)、[展开背景](media/garden-petal-v19.png)、[过渡中间帧](media/garden-petal-v19-mid.png)
- [原始透明花朵 PNG](../../assets/brand/forget-me-not/v19/forget-me-not-macro.png) 与 [最终提示词及来源](../../assets/brand/forget-me-not/v19/PROMPT.md)

## 实际变化

使用内置 image_gen 生成一张五瓣勿忘我微距风格图片，保留卷边、细脉、柔和阴影和不规则外缘。实际尺寸 1254 × 1254，RGBA，1,982,383 bytes；原样复制到项目，没有用 CLI，也没有调用项目的付费 API。品牌小图标保持 v2，新增图片用于记忆花园的大尺寸花朵。

花朵的五个可点击区域对应同一张图片，分类、15 条示例记忆和原稿出处不变。展开时镜头靠近选中花瓣所在的区域，完整照片参与缩放，避免裁出的扇形产生直边。阅读背景沿用这张照片，并通过局部径向透明渐变融入湖畔暖色背景。照片保持朝向和比例，底部花瓣不再额外旋转成竖直图形。

两个层级统一引用 camera.js 的 620 ms 时长及焦点/缩放曲线。旧版花瓣为 740 ms，且文字约在 281 ms 后才开始出现；新版文字随镜头立即渐显，约 397 ms 到达完整不透明度。保留可中断的矩阵衔接、快速返回和减少动态回退。图片在页面头部预加载，多个花朵复用同一资源。

## 本轮验证

执行：

```sh
node --test docs/mobile-ui/memory-garden/petal-motion.test.cjs docs/mobile-ui/memory-garden/camera.test.cjs docs/mobile-ui/memory-garden/depth.test.cjs docs/mobile-ui/memory-garden/garden.test.cjs docs/mobile-ui/memory-garden/imagery.test.cjs
```

24/24 通过；包括精确起终点、非退化矩阵、双向及时响应，以及花朵和花瓣相同的焦点/缩放节奏。

浏览器检查了上方和下方花瓣、进入/返回、中途返回、花丛到单花、宽屏背景、358 × 843 CSS px 窄屏的深色 200% 字号和减少动态回退。窄屏 document 为 358/358、内容区为 343/343（clientWidth/scrollWidth），无横向溢出。检查时控制台无 error/warn，结束后临时转场层为 0，花朵可见性已恢复。

[实际动效采样](media/garden-motion-v19-verification.json)：花丛相机终点时间为 620 ms，四次花瓣轨迹 duration 都为 620 ms，源/目标图片相同；完成时矩阵与实际目标的最大分量误差小于 0.001。采样用于验证时长、几何交接和清理，不能作为真机帧率或用户审美验收。

仅本地网页与设计资产变更，未提交、推送或部署。Android/iOS 原生 UI 和真人录音处理链路没有因此完成。该图片是预生成装饰素材，App 按真实记忆实时生图仍待后续接入。

# v21 · 走进整座花园

2026-10-02。本轮修改本地网页原型，承接用户对整体缩放、随机花园和写实枝叶的反馈。原生代码、共享 Contract、真实录音处理链路未在本轮修改。

## 体验变化

- 花朵、枝干、叶片、记忆标签和远背景一起平移缩放，标题与导航保持悬浮。原先内层画框的裁切和渐隐遮罩已去掉，只在手机内容画面边缘裁切。滚轮、拖动、双指算法、缩放按钮和键盘移动共用镜头状态。
- 花园提供池畔薄暮、暖色花径、林间微光、月下花园四种光景。默认重新进入花园时随机挑选，排除刚看过的那一处；花丛 → 花朵 → 花瓣保持同景。底部“换一处花园”随时轮换，预览设置或 `?garden=night` 等参数可以固定光景。
- 夜景保留中央蓝花的层次，把标题、标签和操作区调整为可读的暗色玻璃与浅色文字。九处微光分别漂移、明灭，可暂停；减少动态和后台状态会停止装饰动画。
- 以新生成的透明写实枝条替代平面线条，呈现圆柱茎的明暗、细绒毛、交替生长的叶片与细脉。用相似变换将茎顶接到既有花托位置、茎底伸入画外，保留叶片比例；部分枝条镜像，避免完全相同的姿态。

仍是预生成纹理与图层构成的 **2.5D 视觉**，没有引入可任意旋转的三维网格或实时光照。现有示例记忆数量和来源不变。

## 实现与维护

- `nature/garden-v21/scene-model.js`：四景清单、排除上次的随机规则、统一物理坐标投影、背景边缘约束。
- `nature/garden-v21/atmosphere.js`：持久背景层，解码完成后再交叉淡入；同层级浏览不重新抽景。前景/背景转场共用 91 个镜头采样与相同开始时间，继续使用 620 ms 节奏。
- `nature/garden-v21/garden.css`：整个手机内容区为可视窗口，内部舞台允许溢出；标题/控件独立叠层。采用 `overflow:clip` 避免浏览器因放大元素而偷偷滚动内容。背景留出 32 px 外延，并对平移范围做约束。
- `memory-garden/botanical-v21.js`：仅替换枝叶生成方法，保留 v20 花朵、花瓣和校准后的连接点。相似变换同时支持镜像，避免压扁叶片。
- `memory-garden/depth.js`：手势区域扩展到手机内容区，普通按钮和输入框仍正常操作；布局变化重新测量前景与背景的坐标关系。

素材为内置 imagegen 生成：夜景 1024 × 1536 PNG，枝条 1024 × 1536 RGBA。完整提示词、来源和编辑顺序在 [PROMPTS.md](nature/garden-v21/PROMPTS.md)，枝干锚点在 [素材说明](../../assets/brand/forget-me-not/v21/README.md)。本轮未对图片做代码重绘或像素后处理。

## 验证

31/31 Node 检查通过：既有数据/花瓣/镜头回归，加上场景覆盖、不连续重复、前后景投影一致、边缘覆盖、枝条两端接合与比例保持。

```powershell
node --test docs/mobile-ui/memory-garden/scene-v21.test.cjs docs/mobile-ui/memory-garden/botanical-v20.test.cjs docs/mobile-ui/memory-garden/petal-motion.test.cjs docs/mobile-ui/memory-garden/camera.test.cjs docs/mobile-ui/memory-garden/depth.test.cjs docs/mobile-ui/memory-garden/garden.test.cjs docs/mobile-ui/memory-garden/imagery.test.cjs
```

浏览器检查：

- 390 px 内容宽度、200% 镜头：前景与背景变换矩阵一致；标签随景缩放；标题保持原位；内容区无横向溢出、无意外滚动。
- 键盘平移后两层矩阵继续一致。搜索空结果能清除，列表回退能进入记忆。
- 夜景花瓣展开/返回与快速反向返回：仍为 620 ms，源与目标为同图；矩阵交接最大误差小于 0.001，没有残余覆盖层或隐藏花朵。
- 换景与重新进入能选到不同场景，花瓣内部保持同景。
- 实际 358 px 窄屏无横向溢出；深色 + 200% 文字回退列表，减少动态时萤光层隐藏。
- 页面控制台未发现警告或错误。

浏览器证据：[几何与状态记录](media/garden-motion-v21-verification.json)、[夜晚花园](media/garden-night-v21.png)、[单花](media/garden-flower-night-v21.png)、[大字号回退](media/garden-narrow-large-v21.png)。

尚未进行 Android / iOS 真机双指触控、GPU 帧率或内存验收；浏览器几何检查不能代替这些设备测试。图片是预生成本地资源，不表示 App 在线生图或 H05 真人音频闭环已经接通。

## 入口

- [手机原型](prototype.html?demo=1#archive)
- [四种光景对照](concepts/garden-light-v21/index.html)
- [固定夜景](prototype.html?demo=1&garden=night#archive)

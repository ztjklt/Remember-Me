# 花瓣与光 · 公式植物质感实验

2026-10-02。本轮在用户认可 v2 后，探索更细腻的花瓣、材质和光照；v2 仍是手机小尺寸标记。入口：[preview.html](preview.html)。在仓库 HTTP 服务上打开 `/assets/brand/forget-me-not/procedural/preview.html`。

## 实现

- 原创 `<botanical-flower>` Web Component：WebGL 高度场绘制五瓣花冠，SVG 贝塞尔曲线绘制枝叶和花苞。没有引入第三方运行库、模型、纹理或 CDN。
- 花瓣轮廓：将方位角折叠到五个扇区，`δ = atan2(sin(5(θ−π/2)), cos(5(θ−π/2)))/5`；射线与偏移圆相交，`R(δ) = d cosδ + sqrt(b²−d² sin²δ)`，其中 `d=.49, b=.405`。微小缺口和低频不对称项修饰轮廓。
- 高度：`q=r/R`，`z = cup*(.13q² + .12q⁸ − .12exp(−24r²)) + folds + asymmetry`。用中心差分求梯度，`N=normalize(−∂z/∂x,−∂z/∂y,1)`；漫反射和宽高光塑造起伏。
- 细脉：每个花瓣局部角度上的放射扇形条纹，辅以固定噪声；暖白喉环、金色花眼与深色中心按半径混合。参数控制弧度、纹理强度、光照方向。
- 这属于 **2.5D 艺术近似**，不是实拍复刻、精确植物学模型、物理透射渲染或完整三维网格。参数调整改变高度场的着色；不提供自由旋转视角。
- 仅在参数或尺寸变化时安排一次绘制，合并同帧更新，DPR 上限 2、画布宽度上限 960。没有空闲动画循环。移除组件时释放缓冲、程序和观察器。WebGL 不可用或上下文丢失时显示 v2 SVG，恢复后重建。

## 来源与复用边界

| 来源 | 实际启发 | 本轮用法 |
|---|---|---|
| [aherbez/glflower](https://github.com/aherbez/glflower) | 作者讲解从贝塞尔叶形到弯曲花瓣、法线和光照 | 技术路线参考；未复制代码。所查看仓库首页未标出许可证，不据此直接搬运 |
| [Vasileios-Bellos/BloomingRoseField](https://github.com/Vasileios-Bellos/BloomingRoseField) | 参数曲面控制玫瑰弯曲、开合；MATLAB 与 Web 版本 | MIT 项目，参考参数化思想；未引入玫瑰模型或代码，勿忘我采用独立五瓣形状 |
| [tantaneity/bouquet-gen](https://github.com/tantaneity/bouquet-gen) | C# 运行时生成花瓣、枝叶网格，种子可复现 | MIT 项目，记录为后续完整三维花束参考，未引入 Unity |
| [真实 Myosotis sylvatica 照片](https://commons.wikimedia.org/wiki/File:Vergissmeinnicht-JR-T20-4271-4398-2020-05-12.jpg) | 五瓣、浅喉环、金黄中心 | 沿用 v2 原图作等比参考，Johannes Robalotoff / CC BY-SA 4.0；未当作着色纹理 |

未确认这些项目就是用户记忆中的那个 GitHub 作者。本机已安装技能中未找到专门的“公式花瓣”技能；本轮沿用 UI/UX 技能的交互检查方法，程序绘制按用户明确提出的函数路线实现。

## 应用尺度

- 24–64 px 导航、头像、应用标题：继续使用 v2 简洁矢量图。
- 160–445 px 品牌页、欢迎页的候选插画：本轮植物质感实验。
- 真实客户端如采用该插画，优先评估导出静态资源，避免为日常小标记常驻 WebGL。尚未生成或接入 Android/iOS 新资源。
- 手机组件改进与验收记录见 [v10](../../../../docs/mobile-ui/NATURE_UI_V10.md)。

# 第二轮视觉打磨 · 2026-09-27

用户反馈第一轮界面过于通用，本轮重做构图与视觉辨识度。方向为雾银底色、勿忘我蓝、声音刻线；不改变录音、核对、来源与授权流程。

## 已实施

- 首页移除大块说明卡片。品牌、日期、短标题、刻线印记、独立录音入口和最近记录形成不同层级。
- 首页静态刻线是程序绘制的品牌装饰，隐藏于辅助技术，不对应任何录音样本，不持续运动，也不拦截点击。大字号时缩小装饰。
- 录音入口使用圆形麦克风与文字组合，整个区域可点。录音页用圆形细边与稳定表面衬托真实电平，暂停行为不变。
- Android 导航用圆角 Material 表面和原生 NavigationBar；iOS 保留原生 TabView。网页中的透明导航仅用于原型，不能当作原生 Liquid Glass 实测结果。
- 播放器保持真实播放状态与拖动，用独立表面区分控制。记忆正文不再作为一整块巨大标题，引文用蓝色文字与细分隔建立层次。
- Android / iOS 更新浅深色语义令牌。无外部字体包、3D 渲染依赖或第三方运行时代码。

## GitHub 参考与具体取舍

这些材料是设计参考，没有安装进全局 skills，也没有复制项目素材或组件源码。

| 参考 | 采用的原则 | 本项目取舍 |
|---|---|---|
| [Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | 确定明确视觉方向与一个记忆点，避免通用卡片模板 | 刻线品牌印记与录音入口；中文正文仍用系统字体 |
| [Impeccable](https://github.com/pbakaus/impeccable) | 审视层次、密度与模板化风格 | 删掉首页重复解释，区分列表、控制和长文 |
| [Taste redesign](https://github.com/Leonxlnx/taste-skill/blob/main/skills/redesign-skill/SKILL.md) | 在已有界面上重审构图和细节 | 保留业务流程，重做首页、录音、记忆详情 |
| [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 使用性和移动端检查清单 | 触控、字级、对比度与减少动态作为验收约束 |
| [React Bits](https://github.com/DavidHDev/react-bits) | 局部材质与视觉焦点 | 未引入 Three.js / React 组件；不把网页着色器当成双端现成方案 |
| [Android Liquid Glass](https://github.com/Kyant0/AndroidLiquidGlass) | 控制层与内容层的材质区别 | 本轮用原生 Material 表面，未添加玻璃库 |
| [DSWaveformImage](https://github.com/dmrschmidt/DSWaveformImage) | 用实际声音数据驱动波形 | 现有真实电平进入新构图；未给历史录音编造声纹 |

## 验证边界

原型固定样本与模拟播放始终有明确标记。原生源码与网页不是像素级同一实现，网页截图不能替代 Android / iOS 真机截图。Android 构建、原型交互与尺寸检查、语义颜色对比度可在本机验证；iOS 目前仅语法解析，设备操作、读屏、实际合成色与用户偏好仍需验证。

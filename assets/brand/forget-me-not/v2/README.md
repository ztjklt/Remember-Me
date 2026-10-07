# 一枝留念 · 勿忘我品牌 v2

2026-10-02，本地设计迭代。用户认为旧版浓蓝色花形突兀、缺少特色，要求先参考真实勿忘我，再做艺术化 logo。

## 从实物到标记

参考植物为 **Myosotis sylvatica**。RHS 记录其花朵小巧、五裂，蓝色花冠有白色或黄色中心。实物照片显示圆润的瓣缘、浅色喉环及小花心；旧版长水滴式花瓣改为较宽的圆润轮廓。

设计概念“一枝留念”保留五瓣花与暖金花心，加入一枚花苞、一片叶子和回环枝条。回环是品牌中的记忆意象，属于艺术表达。UI 色彩采用低饱和雾蓝和苔绿；“勿忘我”字标配衬线字体，英文名称作为较轻的次级文字。

- `botanical-art.png`：内置 imagegen 生成的植物手稿，1254 × 1254，原始透明 PNG 未改动。用于较大尺寸展示。
- `svg/mark-light.svg`、`mark-dark.svg`：为手机小尺寸重新绘制的简化矢量标记。移除手稿纹理，进一步降低蓝色饱和度。
- `svg/mark-mono.svg`：单色版，不依赖蓝色识别轮廓。
- `preview.html`：实物、手稿、UI 标记及 24 / 40 / 64 px 对照，支持浅深色。
- `GENERATION.md`：实际使用的完整提示词与生成方式。

手机页头采用 40 px 标记。24 px 可保留整体轮廓，花心细节较少；带字标的场合优先使用 40 px。标记保持静态，不表示正在录音或处理进度。

## 来源

1. [RHS — Myosotis sylvatica](https://www.rhs.org.uk/plants/41558/myosotis-sylvatica/details)：植物形态参考。
2. [Kew — Myosotis](https://powo.science.kew.org/taxon/urn%3Alsid%3Aipni.org%3Anames%3A30010296-2/general-information)：五裂花冠与花序资料。
3. [Johannes Robalotoff — Myosotis sylvatica photograph](https://commons.wikimedia.org/wiki/File:Vergissmeinnicht-JR-T20-4271-4398-2020-05-12.jpg)，2020-05-12 摄，来源 Wikimedia Commons，许可 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。本地 `reference/myosotis-sylvatica.jpg` 为原文件副本，未修改；摄影者没有为本项目背书。它用于植物形态参考与对照页展示，未加入客户端资源。

## 源码接入

运行 `python assets/brand/forget-me-not/v2/build_assets.py` 会由同一套路径生成 SVG、网页副本、Android VectorDrawable 和 iOS `BotanicalBrandGeometry.swift`。路径记录在 `geometry.json`，浅深色颜色随同各图层定义。

Android / iOS 的 `RememberMeBrand` 保留原有参数和无障碍语义，默认标记改用 v2；首页标题锁定组合一起调整。网页通过 `docs/mobile-ui/brand/v2/brand.css` 使用对应资源。历史 v1 原文件保留，启动图标和旧材质导出本轮未替换。

## 本次验证

- Android `assembleDebug --offline --console=plain` 成功；日志 `output/playwright/android-build-brand-v2.log`。此次为资源和展示调整，没有重新运行业务单元测试。
- 三种 SVG、三种 VectorDrawable XML 可解析；网页副本与源 SVG 一致。生成 PNG 角落 alpha 为 0，确有透明背景。
- 浏览器实际检查首页、浅深色标记及 200% 字号；实际 CSS 视口 358 × 798 下无横向溢出。品牌对照页图片全部加载，无脚本 warning / error。
- iOS 的新 Swift 文件由现有 `project.yml` 的 RememberMe 源目录包含；当前 Windows 未编译 iOS。双端标记的原生设备视觉检查仍待完成。
- [品牌截图](brand-signature.jpg)、[对照页截图](brand-board.jpg)、[首页截图](../../../../docs/mobile-ui/media/brand-v2-home.jpg) 均为网页截图。

本轮没有修改录音、数据、授权、后端或模型行为，也没有提交、推送或发布。

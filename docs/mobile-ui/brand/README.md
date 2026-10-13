# 品牌资源来源

2026-10-02：当前网页及双端默认品牌组件使用 [v2 / 一枝留念](../../../assets/brand/forget-me-not/v2/README.md)。以真实勿忘我照片为参考，经内置 imagegen 生成植物手稿，再将小尺寸标记重绘为低饱和雾蓝 / 苔绿矢量；资源在 `v2/`，此前的以下 v1 文件保留为历史。

本目录的三张 SVG 原样复制自用户在侧边设计流程交付的 `assets/brand/forget-me-not/v1/svg/`，概念为 C / 留声，五瓣蓝花与金色花心。

`mark-flat.svg` 用于小尺寸浅色界面；`mark-flat-dark.svg` 用于深色界面；`mark-material.svg` 用于空状态等较大尺寸。所有图形保留原样，不作为录音指示或进度动画。

Android 和 iOS 各自复制必要的原始导出与适配代码。Android 单色启动图标由同包 `mark-mono.svg` 的路径转换为 VectorDrawable，并加入启动图标安全边距。

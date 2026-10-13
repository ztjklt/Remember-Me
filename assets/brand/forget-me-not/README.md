# 勿忘我品牌源包交接

**当前本地版本：[v2 / 一枝留念](v2/README.md)**（2026-10-02）。真实花形参考、艺术手稿、共享矢量几何与双端接入见该目录；[可交互对照稿](v2/preview.html)。新增 [公式植物质感实验](procedural/README.md) / [交互预览](procedural/preview.html)，用于较大品牌展示；小尺寸客户端标记仍为 v2。以下是 v1 的历史交接。

2026-09-27：将侧边设计流程交付的 C / 留声品牌源包 `v1/` 纳入 UI 工作分支，供后续维护。包含概念参考、生成记录、共享轮廓脚本、SVG/PNG、Web 组件、Compose/SwiftUI 适配器及文件哈希清单；v1 内文件原样保留。

v1 README 和 verification.json 中“尚未接入原生应用”描述的是最初独立品牌包阶段。当前第六版 UI 已将必要资产接入 Web、Android 以及独立 iOS UI 分支；Android 构建通过，iOS 仅语法检查，设备上的启动图标、材质与读屏仍待验证。实际运行代码见各客户端，不直接用模板适配器覆盖已有实现。

- [源包说明](v1/README.md)、[预览](v1/preview.html)、[来源](v1/provenance.json)、[文件清单](v1/manifest.json)。
- Web 运行副本：`docs/mobile-ui/brand/`。
- Android：`core/designsystem/RememberMeBrand.kt`、`res/drawable-nodpi/`、启动图标资源。
- iOS 分支：Views.swift 中品牌组件与 Assets.xcassets 中对应资产。

完整交接见 [HANDOFF.md](../../../docs/mobile-ui/HANDOFF.md)。外层 `remember-me-brand-v1.zip` 是 v1 目录的重复便携包，仅保留本地；仓库内的展开源文件是交付内容。

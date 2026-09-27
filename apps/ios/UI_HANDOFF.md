# iOS 移动 UI 交接 · 2026-09-27

第六版 UI 对齐代码位于 `codex/ios-ui-alignment`，固定基于 #77 的 `e146ac56f080299676fed40653394b97a37bd270`，Draft PR 比较目标为 `feature/ios-calibration`。交接时 #77 仍为 OPEN / Draft，head 未变化；本次没有合并或发布。

交接 PR：**[iOS #80](https://github.com/ztjklt/Remember-Me/pull/80)**；对应 **[Android / 设计资产 #79](https://github.com/ztjklt/Remember-Me/pull/79)**。远端状态见 Checks，自动运行的 Android CI 不能视作 iOS 编译验证。

## 交付和入口

- [逐项改动与各轮检查](UI_ALIGNMENT.md)：导航、录音、播放、核对草稿、来源、浅深色、品牌、渐变和回忆图形。
- [双端详细交接](https://github.com/ztjklt/Remember-Me/blob/codex/mobile-ui-core/docs/mobile-ui/HANDOFF.md)：当前设计、品牌来源、组件生成、Android 差异和待办。
- [图形源包](https://github.com/ztjklt/Remember-Me/tree/codex/mobile-ui-core/docs/mobile-ui/memory-elements)、[品牌源包](https://github.com/ztjklt/Remember-Me/tree/codex/mobile-ui-core/assets/brand/forget-me-not)：都在 Android/设计工作分支，iOS 只携带实际所需代码和资源。
- [服务与设备接入](README.md)：沿用 #77 的配对 Mac 服务；转写不发生在 iPhone 本机。

原生实现集中在 `RememberMe/Views.swift`、`AppModel.swift`、`RememberMeApp.swift`、`Assets.xcassets`。Views.swift 内已有品牌和 `BEGIN/END GENERATED MEMORY GLYPHS` 生成区；不要再次加入同名独立组件文件。字体跟随 Dynamic Type，系统导航使用原生材质，不声明已验证 Liquid Glass。

## 获取与复核

```sh
git clone --branch codex/ios-ui-alignment https://github.com/ztjklt/Remember-Me.git remember-me-ios-ui
cd remember-me-ios-ui/apps/ios
xcodebuild -project RememberMe.xcodeproj -scheme RememberMe \
  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

项目使用 Swift 6，部署目标 iOS 17.0。上述 Xcode 命令尚未在本次 Windows 环境执行。四个 Swift 文件已进行 tree-sitter 语法解析、七组 Any/Dark 颜色与共享 tokens 比对；这不等价于 SwiftUI 类型检查和构建通过。Android 构建结果与 HTML 截图也不能证明 iOS 可运行。

需要修改图形时，将两条分支分别检出到相邻目录；在 Android/设计目录运行：

```sh
python docs/mobile-ui/memory-elements/build.py
python docs/mobile-ui/memory-elements/build_native.py --ios-root ../remember-me-ios-ui
python docs/mobile-ui/verify-design.py --ios-root ../remember-me-ios-ui
```

分别检查和提交两边变化。Web 滤镜、Compose 近似投影与 SwiftUI Canvas 阴影不是像素一致实现，原生设备观感仍需调整。

## 接手执行单

- [ ] Mac/Xcode 编译，修复真实类型或资源错误后再声明构建通过。
- [ ] 375/430 pt、普通/大字、浅深色、减少动态/透明度、增强对比度与 VoiceOver；检查原生图形阴影和 AppIcon。
- [ ] 录音开始/暂停/继续/关闭/后台保存、拒绝及恢复权限、回听/暂停/定位、异步下载切换与录音互斥。
- [ ] 配对 Mac 转写、核对草稿刷新保留、明确同意整理、删除和纠正失败可恢复；回归证据、Twin、校准和独立声音授权。

当前仍为原有单个待处理录音机制，未实现多个离线草稿队列或新同步引擎。已配对服务不可用时，不把远端流程成功显示为本地已完成。

## 共享影响与回退

相对固定 #77 基线，本 UI 分支没有修改 `Network.swift`、共享 Contract、Backend、AI Core、Voice 服务或供应商 SDK。新增本机核对草稿按 Episode 保存，原服务授权和独立声音授权保留。没有把新功能范围扩大到原有能力以外。

本次分支尚未集成，主线未被修改。试装回退前保留录音与待处理草稿；不要通过卸载、清数据或强制重置解决版本问题。旧版对新增本机草稿的无损降级尚未验证。

Android 分支基于另一条 #78 开发线，且 #78 后来新增了画像导航；**不要把 Android 分支整体合并到本分支以获取设计文件**。若要移植，应在明确集成基线后按 UI 差异审阅并验证。本页提供接手材料，不自动指派人员，也不代替合并或发布决定。

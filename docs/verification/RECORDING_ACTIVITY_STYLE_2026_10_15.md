# 录音实时活动视觉对齐，2026-10-15

用户要求实时活动、灵动岛贴近 App 风格。本次仅修改 iOS 视觉及版本，不改变录音、设备认证、上传、声纹匹配或后端接口。

直接复用 `RMDesignTokens.swift` 与 `ForgetMeNotFlower.swift`，由 XcodeGen 共享给扩展；不复制另一套品牌色或花朵。`Shared/RecordingActivityPresentation.swift` 提供锁屏与灵动岛共用组件。采用 App 的纸色／深色背景、蓝色、五瓣勿忘我、系统字体与圆角计时；灵动岛保留系统黑底，返回入口为浅蓝胶囊。

录制、暂停、状态待确认分开显示；紧凑与最小形态以花朵和暂停／问号标记识别状态。仅显示实际来源、状态与计时，不添加模拟音量动画。紧凑布局限制字号上限并对长计时缩放；辅助功能大字号预览仍能读到状态。App 内样式画廊仅 DEBUG 启用，并标明“无录音”，Release 不含该入口。

实际验证：

- `build/activity-style-release-final.log`：1.13.1 / 2026101507，含主 App、实时活动扩展与官方 SDK 的签名 Release 构建通过。
- `build/activity-style-signature.log`：`codesign --verify --deep --strict` 成功。
- `build/activity-style-ui.xcresult`：共享界面样式、真实 ActivityKit 创建／结束共 2 项通过；修正紧凑字体限制后再次运行样式检查。
- `build/activity-style-dark-ui.xcresult`：显式浅色／深色、辅助功能 XXXL 样式检查通过；实际查看最终浅色与深色截图，包含锁屏录制／暂停、展开／紧凑／最小及状态过期。
- 最终截图在 `build/activity-style-final-images/`；这是同一组 SwiftUI 组件的 App 内布局预览，不冒称真机系统锁屏截图。
- `build/activity-style-install.log` 与设备安装清单确认「黑幕」已安装 1.13.1 / 2026101507，覆盖安装，未卸载原 App。新安装后的自动启动被锁屏拒绝；此前 1.13.0 已实际启动并核对存活进程。未擅自录制真实环境声音验证视觉。

实际系统锁屏／灵动岛效果和长时间佩戴验证可在用户主动开始录音后继续检查。

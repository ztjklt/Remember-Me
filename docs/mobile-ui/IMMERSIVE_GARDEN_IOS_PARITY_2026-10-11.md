# iOS 对应设计与接口（尚未编译验收）

Android 0.9.0 为本轮可运行端，iOS 本轮交付以下页面映射，不声称 SwiftUI 已经完成这些移植。

| Android 本轮行为 | SwiftUI 对应 | 复用资源/接口 |
|---|---|---|
| 今天：讲一段、继续整理、我的录音 | 同语义首页，sheet/fullScreenCover 进入录音；底部固定控制 | Episode；录音与云端确认分别触发 |
| 花田：沿地面错落的故事花 | ScrollView + ZStack，保存稳定故事 ID 顺序、scroll position；用原 photo assets | `workbench/subjects/{id}/stories` + `/narrative` |
| 花瓣聚焦与内容阅读 | 同花形局部高亮；可打断约620ms过渡；Reduce Motion 直接切换 | `docs/mobile-ui/native-garden/asset-manifest.json`，三种花形 |
| 人物两个分段与四视角 | Picker：了解这个人/记忆侧面；四视角首屏2×2，内容预览优先 | 同一 narrative records、source_valid、understandings |
| 八维四字标签 | 人生经历、人物关系、身份角色、偏好习惯、在意选择、感受状态、愿望牵挂、原话寄语 | 只改显示名，不改共享枚举 |
| 查找 | 本地精确内容 + `/api/v1/subjects/{id}/memory-search` 相关检索；问一问另触发 | 禁止把搜索请求当成生成问答 |
| 原音与书面来源 | AVPlayer 播完整授权原音；书面补充不展示虚假音频定位 | `/stories/{episode}/audio`，依当前身份鉴权 |
| 字体放大 | Dynamic Type 下花瓣改顺序阅读，固定导航与录音控件 | 不缩小系统字体，不固定卡片文本高度 |

默认沿用当前服务端 Paraformer 转写与核对路线；不能重新接回早期本地 Whisper 自动整理。私密、撤权、失效来源同时约束标题、原话、人物内容和播放器。人物空间名中统一保留“虚构人物”，避免在每条内容里重复测试说明。

Mac 编译、375/430pt、VoiceOver、真实麦克风及后台保存：待单独执行。不要将 Android 截图或网页预览当作 iOS 实跑图。

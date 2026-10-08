# iOS Android 原型复刻记录

2026 年 10 月 8 日。分支 feature/ios-android-parity，从 develop 的 4dc3d5a 建立。用户明确要求先复刻队友 Android 原型，再在 iOS 上补完 AI Agent Core；本批交付先完成界面和已有能力的接合。

## 对应关系

复刻来源为 Android PR #81 的 aef0b9b，经 #83 接合后的 MainScreens.kt。采用既有蓝灰色设计令牌和 iOS 原生导航，不包含 Draft #85 的自然风格/记忆花园改版。

| Android 原型 | iOS 实现与动作 |
| --- | --- |
| Portrait | 五入口导航、搜索/导出栏、品牌栏、八类记忆网格、录音与实际采集问题 |
| Graphs | 四类画像入口、同源关系图设计示意、真实七领域结论与可展开证据 |
| Memories | 当前记忆看板、档案入口、核对/纠正、单条删除与录音新增 |
| Agents | Memory keeper、Portrait reader、Twin guide 状态，真实最近处理记录，问答与校准入口 |
| Me | 本地录音/转写使用说明、当日服务端录音与记忆数量、系统权限、独立声音授权与服务连接 |

八类卡片是展示入口，服务端仍采用原有七领域 Person Model。声音状态、环境分析与情绪趋势明确显示待接入；不会由文字模型编造结果。关系图 PNG 直接复用队友资产，并在图前明确标注设计示意。记忆列表不把排序位置当版本号；完整历史比较尚未由现有 API 提供。

iOS 原有 AppModel、Backend Contract、证据问答、五维校准、个人声音授权和录音/核对流程保留。新入口允许先浏览和保存一段本地录音，服务连接通过独立页面完成；上传/转写仍要求配对服务，客户端不持有供应商密钥。现有单个待处理录音机制没有变成离线多任务队列。

重新连接前阻止跨服务移动未完成录音；切换服务、证书指纹或 Subject/Actor 后清理原来的可见资料与授权缓存。原有另一个 iOS 工作目录中的签名配置和用户数据未修改。

## 本地验证

Xcode 27.0，iPhone 17 Pro Max 模拟器，iOS 26.5。模拟器构建命令：

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath build/ios-parity CODE_SIGNING_ALLOWED=NO build
```

结果 BUILD SUCCEEDED。初次构建发现跨文件 ConnectionNotice 访问级别不正确，修复后通过。AppIntents 元数据提取提示没有该框架依赖，不影响构建。

新增原生 UI 检查覆盖：五入口、画像分类搜索与空态、录音页面打开、记忆分段、Agents 至原有 Twin、我的页面和配对页。测试打开录音页但不模拟真人麦克风录音；没有注入虚构个人画像或调用付费供应商。

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,id=D2FE37B7-EC92-4C64-A7E0-CEC9F332E987' \
  -derivedDataPath build/ios-parity \
  -resultBundlePath build/ios-parity-final-tests.xcresult \
  CODE_SIGNING_ALLOWED=NO test
```

最终结果 TEST SUCCEEDED：2 项 UI 测试通过，0 失败，执行约 36.5 秒。测试结果包和原生截图留在忽略的 build 目录。真机麦克风、配对后的实际上传、模型输出质量和个人声音不由本批 UI 检查证明。

人工查看模拟器原生截图：浅色 Portrait 首页布局正常；深色模式与 accessibility-medium 字号下，分类标题可以换行，首屏未观察到文字重叠或导航遮挡。该观察只覆盖首页，不等同于完整无障碍检查。检查后将模拟器恢复为浅色和 large 字号。最后调整当日统计的文字为“已上传录音”，并把服务地址与证书指纹纳入连接缓存隔离；随后再次构建最终源码。

## 下一批 AI Agent Core

沿用当前 iOS v0.2–v0.4 Contract 与服务端模型，先在实际手机上验证录音核对、画像证据、锁定回答、本人回答、五维比较、模型更新与再次提问。再依据结果补齐画像连续性、当前结论/反例展示、校准失败恢复、采集问题生命周期和语义评测。

feature/ai-agent-core 的实验增量需要逐项比较后迁入，避免整体覆盖当前 iOS 服务端和迁移链。新契约、八类记忆语义扩展、长期检索、硬件、Legacy 和新增声音能力各自需要有界方案，未作为本批交付完成。

## 共享影响

本批未修改 packages/contracts、services、infra 或数据库。没有改变录音/Cloud Twin/Voice 各自授权语义，没有嵌入 provider secret，也没有发布安装包或更改 main/develop。变更仅涉及 iOS UI、连接状态保护、图资产、UI 检查和说明。

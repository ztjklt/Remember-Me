# Android → iOS 差异补齐与本地验证

- 日期：2026-10-10
- 工程：`apps/ios/RememberMe.xcodeproj`；Scheme：`RememberMe`
- 分支：`feature/ios-android-parity-sync`，基于 `origin/develop` 的 `4dc3d5a`。
- 复用已有 `e3186a7` 的五入口 UI 移植；未引入该历史分支后续的 AI Core、Backend 或跨模块合同变更。

## 差异与本次结果

对照当前 Android 导航、MainScreens、MobileViewModel、RecordingWorkflow 和 AndroidAudioCaptureService，以及 develop 上原有 iOS 实现：

| Android 已有而原 iOS 缺少或不完整的部分 | iOS 本次结果 |
| --- | --- |
| Portrait / Graphs / Memories / Agents / Me 五入口 | 五个入口均可导航，保留 iOS 原有模型、Twin、校准与声音授权入口 |
| 八类画像卡片与分类查找 | 卡片映射真实七领域画像与情绪记忆；搜索和分享使用真实服务数据 |
| 关系图展示与 Memories 控制板 | 移植布局；静态关系图明确标注示意，未宣称已有真实知识图谱 |
| Agents 状态页、Me 今日数据 | 接入现有 iOS 真实处理状态；本机录音与服务端 Episode 分开计数 |
| 未连接服务时浏览和录音 | 不强制先配对；录音仍需用户确认及系统麦克风权限 |
| 多段录音长期留在手机、逐段回放 | 本机录音目录，回放、暂停、拖动进度；准备新录音保留上一段原音 |
| 可选本机中文 ASR | 增加 Apple Speech 适配器，仅设备支持离线识别时可用；失败保留原音 |
| 机器原始转写、编辑草稿、确认版分开保存 | 三种文本分别持久化；本机确认不会自动提交给 AI |
| 从已保存录音继续核对和整理 | 每段保留自身 Episode ID，重试沿用原有上传幂等流程；接入既有 Mac 转写、核对、Memory 和模型更新 |

Android 的部分设置、图谱和 Agents 入口仍是原型或待接入状态；本次没有把这些按钮包装成已完成能力。iOS 已有的证据问答、五维校准、独立个人声音授权继续使用原实现。没有新增一个与服务端竞争的本机 AI 核。

## 数据与失败处理

- 原音不因上传、处理完成、ASR 失败或准备新录音而删除。一段录音对应一份原子写入的元数据文件。
- 保留录音 ID、问题 ID、校准 ID、录音同意时间、Episode ID 和机器原始转写；本机文字改动另存。
- 导入原来的单段 `pending-recording`；容器路径改变时按现有原音文件名恢复引用，不重建身份或来源。
- 录音信息损坏或原音丢失时保留其余可读数据并显示错误。元数据目录排除系统备份，文件使用 iOS 完整保护。
- 已绑定录音只对相同 Subject、Actor、服务地址和证书指纹可见。处理中的录音不可切换；异步返回结果在写入前再次验证所属录音与空间。
- 未上传录音换服务时仍要求同一 Subject 和 Actor。上传采用用户主动操作，没有增加自动后台上传。
- 配对、处理状态和转写状态读取采用 15 秒超时，失败可重试；音频上传及较长 AI/声音请求保留原来的超时预算。
- 未修改 Contracts、Backend、AI Core、Voice 或数据库迁移；无跨模块合同影响，无 provider 密钥进入手机。

本机识别先检查 `supportsOnDeviceRecognition`，获准后设置 `requiresOnDeviceRecognition = true`，不会退回网络识别。能力依据：[Apple 设备能力说明](https://developer.apple.com/documentation/speech/sfspeechrecognizer/supportsondevicerecognition)、[Apple 本机识别请求说明](https://developer.apple.com/documentation/speech/sfspeechrecognitionrequest/requiresondevicerecognition)。具体 iPhone 的中文模型可用性和识别效果仍须真机检查。

## 本地验证

环境：Xcode 27.0；iPhone 17 Pro Max 模拟器，iOS 26.5。

```bash
cd apps/ios
xcodegen generate
```

在仓库根目录构建和测试：

```bash
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,id=D2FE37B7-EC92-4C64-A7E0-CEC9F332E987' \
  -derivedDataPath build/ios-android-parity-sync \
  -resultBundlePath build/ios-android-parity-sync-release-tests.xcresult \
  -parallel-testing-enabled NO CODE_SIGNING_ALLOWED=NO \
  COMPILER_INDEX_STORE_ENABLE=NO test

xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'generic/platform=iOS' \
  -derivedDataPath build/ios-android-parity-sync \
  CODE_SIGNING_ALLOWED=NO COMPILER_INDEX_STORE_ENABLE=NO build
```

- 模拟器构建通过；14 项测试全部通过，0 失败、0 跳过：11 项本机录音单元测试、3 项导航 UI 测试。
- 单元测试覆盖多录音保存与恢复、机器/编辑/确认文本分离、坏元数据、丢失原音、容器迁移、旧草稿导入、Subject/Actor/服务隔离、活动录音切换、处理状态锁及 ASR 不可用/空文本重试。
- UI 测试覆盖五入口、分类搜索、录音入口、未配对本机档案入口、原有 Twin、服务连接页。测试使用独立临时目录与 UserDefaults，不读取或更改使用者的真实录音与配对。
- 最新构建安装到模拟器后，检查 Portrait 实际截图：五个底部入口、搜索、录音按钮及画像卡片正常显示，无截断或重叠。
- iPhone 设备目标无签名构建通过；本次没有签名安装到真机，没有声称完成真实中文 ASR 或真实 Backend/AI/Voice 回路测试。
- 首次构建遇到磁盘空间不足，仅清理旧工作树内可重新生成的编译缓存后继续；保留源码、原音、数据库、构建产品和测试结果。

## 给本机测试者的步骤

1. 打开上述当前项目，选择 `RememberMe` Scheme 和你的 iPhone，Run。已有安装直接覆盖即可；不要先卸载以免删除本机数据。
2. 未连接服务也可先浏览五页。Portrait 点击录音，确认本次录音，允许麦克风，录一段中文，暂停/继续后保存。
3. 点击“保留这段，再录一段”，保存第二段。进入 Memories → 记忆档案 → 录音，两段都应存在；逐段回放和拖动进度。退出并重启 App 后再检查。
4. 在本机录音详情点击“在 iPhone 上转成文字”。允许语音识别；设备不支持时应明确提示并保留原音。识别成功后修改文字、保存核对版，展开机器原文确认原文没有被覆盖。
5. 选择“继续转写与整理”，按 `apps/ios/README.md` 连接 Mac 服务并上传。在服务核对页确认本机编辑草稿被带入，核对后显式提交；等 Memory 和画像更新。断网重试应继续同一段，不串到另一段录音。
6. 检查真实画像分类、证据、Agents 中原有 Twin/校准，以及 Me 中独立声音授权。静态关系图只检查展示和说明，不当作真实数据输出。

本机转写和本机核对是保存步骤；生成 Memory、更新模型、Twin 和个人声音仍依赖既有配对服务及各自授权。

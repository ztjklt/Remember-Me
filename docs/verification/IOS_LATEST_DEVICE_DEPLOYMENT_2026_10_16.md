# 最新修改真机部署 — 2026-10-16

本人在当前会话直接要求「把最新修改都部署到手机」。目标为 iPhone 15 Pro Max「黑幕」，沿用 `me.remember.personal.ios` 覆盖更新，不卸载或重置数据。

## 安装包

- 新版本 **1.16.1 / 2026101611**，主 App 与 RecordingActivity 扩展版本一致。
- 包含录音页并排设备入口、白色大背景及黑色设备无独立小框、主用户文字／语音问答归档与左滑删除、游客不留存对话，以及最新托付／游客锁定和密语保护修复。
- 使用 `project.hardware.yml`，保留录音豆 SDK、火山 RTC、LiveKit 与后台模式。框架清单包含 `module_spplinkKit.framework`、`VolcEngineRTC.framework`、`RTCFFmpeg.framework`、`RealXBase.framework`、`LiveKitWebRTC.framework`、`RustLiveKitUniFFI.framework`。
- 最终源码冻结在 ignored `build/device-latest-20261016-2026101611/source/ios`。125 个输入在构建及签名前摘要一致，也与当前工作区最新输入集合一致。并行出现的游客／托付修复已重新冻结、重新构建；较早候选包移入 superseded 目录，没有安装。
- Release 构建成功。主 App／扩展的版本、bundle ID、签名及目标设备授权核对通过，描述文件在有效期内。归档前及解包后均执行 `codesign --verify --deep --strict`；Release 不含 DEBUG 离线测试入口。

签名包：`build/releases/RememberMe-1.16.1-2026101611.app.zip`，同名 manifest 保存可执行文件、归档和输入清单的 SHA256。安装使用该归档的解包副本。

## 检查

- 最新 `GuestAccessTests` **26 passed**，覆盖锁定期间阻断轮询、播放、录音、发送，以及旧密语和语音范围检查。生产源码在测试前后摘要一致。结果 `/tmp/remember-latest-guest-unit-20261016.xcresult`。
- 定向界面检查 **4 passed**：托付浅／深色输入界面、录音页设备入口、两项游客只读与密码返回限制。截图目视检查通过。结果 `/tmp/remember-latest-focused-ui-20261016.xcresult`。
- 最终服务快照的游客托付专项 **56 passed**；此前冻结快照的游客／归档／迁移专项 **121 passed**。AI Core **296 passed**，Contract **60 passed**。Backend 全量 **913 passed、6 skipped** 发生在最后的游客加固前，不能作为最新快照的全量结果；最后补强后的 **126 项**定向结果另见[追加修复验证](GUEST_ENTRUSTMENT_FIX_2026_10_16.md)。
- 原有录音归档及设备界面检查见[功能验证](IOS_RECORDING_DEVICES_AND_HISTORY_2026_10_16.md)。线上核验与手机版本读回见下节。

## 部署状态

已完成覆盖安装，设备应用列表独立读回确认 **1.16.1 / 2026101611**，安装前为 1.16.0 / 2026101610。`devicectl` 确认普通启动成功，未传入测试参数。安装前后 **7 个原音文件**的相对路径与完整 metadata 一致，没有卸载或重置，也没有读取音频内容。安装摘要在 `build/device-latest-20261016-2026101611/installation-proof.json`；原始设备回执保存在 ignored `build/private/device-latest-*-2026101611.json`。

配套服务 **CloudBase054 / `ios-latest-f54e295dc7d4`** 已获得100%流量，控制面与公网 `service-info` 版本一致；公网 `/ready` 返回 ready，数据库及对象存储均正常。数据库已迁移到 `0031_guest_secret_index`，迁移前后既有 episode、memory、subject、answer 总数一致。保留原运行镜像、现有供应商与39项配置，并加入仅服务端使用的独立暗号检测密钥。

公网隔离功能核验通过：

- 主用户文字与语音关联记录列表返回200；删除指定轮次后原文已清除。
- 游客连续两轮仍有上下文，`TwinAnswer` 零落库。
- 新建私密托付、自然句内完整暗号解锁及回包脱敏通过；撤销后不再能读私密来源。
- 本人密码复验的错误／正确路径分别返回401／200；未登录访问新增归档及游客管理路由均返回401。
- 未使用本人账号或调用真实供应商；合成账号、空间和计划已清理，残留计数为0。

053的零流量实例已退役，旧镜像及私密回滚配置保留。服务端安全证据在 ignored `build/latest-phone-backend-20261016-v4/{deployment,manifest,migration-proof,route-proof,public-probe,verification,final-proof}.json`，完整过程见[后端发布记录](IOS_BACKEND_054_DEPLOYMENT_2026_10_16.md)；手机构建、签名及安装证据在 `build/device-latest-20261016-2026101611/`。

真实安克设备绑定、录音取回、耳机切换、本人通话及长时间锁屏体验仍需实际使用，不能由构建、安装和模拟器结果推断。

# 通话状态修复真机安装 — 2026-10-16

本人要求先将本轮客户端修复安装到手机。本轮已覆盖安装到 iPhone 15 Pro Max「黑幕」，沿用 `me.remember.personal.ios`，版本 **1.16.2 / 2026101612**；安装前为1.16.1 / 2026101611。没有卸载、重置容器或部署后端。

## 修复与验证

包含[通话中断排查](IOS_VOICE_OUTAGE_DIAGNOSIS_2026_10_16.md)中的取消请求误报、通话期间刷新竞态、旧回包隔离及挂断原因保留。保留同工作区已完成的音色刷新单飞、连接恢复／撤权清理及请求超时调整；本轮按冻结源码补验，没有把这些新增变更全部归入此前67项结果。

硬件项目 `project.hardware.yml` 的126个输入冻结在 ignored `build/device-voice-fix-20261016-2026101612/source/ios`。使用现有SDK及固定LiveKit依赖；生成项目前后与构建后冻结摘要一致。签名前与当前工作区比对，只有后续并行编辑的 `RememberMeUITests/AndroidParityUITests.swift` 不同，未纳入本次冻结包；运行代码一致。

冻结源码的定向模拟器检查 **155 passed / 0 failed**：ECSConnection57、GuestAccess26、TwinVoiceCall25、VoicePreparation17、VoiceReview5、VolcengineVoice25。Release构建成功；App／RecordingActivity扩展版本一致，签名、描述文件有效期及目标设备授权核对通过。6个既有嵌入框架齐全，Release不含DEBUG离线测试入口。归档与解包后的安装副本均通过 `codesign --verify --deep --strict`。

## 安装与原录音

使用签名归档的解包副本安装。`devicectl`安装回执成功，随后设备应用列表独立读回 **1.16.2 / 2026101612**。

安装前后的9个原音路径、大小、修改时间、所有权及权限一致；没有读取音频内容。其中1个文件新增了系统数据保护扩展属性 `com.apple.dataprotection.policy.exception-applied-by`，其余扩展属性相同。因此不声称完整metadata逐字段完全一致；初次严格比较失败的回执与后续逐字段核对均保留。

普通启动被系统以 `Locked` 拒绝：手机锁屏，未能自动解锁。安装已经成功；解锁后手动打开即可。未执行真人通话，不能据此声称生产数据库持锁问题或持续通话质量已修复。

## 本机证据

- 签名归档及清单：`build/releases/RememberMe-1.16.2-2026101612.app.zip`、同名 `.manifest.json`。
- 冻结源码、Release日志、155项测试结果及安装摘要：`build/device-voice-fix-20261016-2026101612/`。
- 设备安装／版本／启动回执与原音metadata核对：ignored `build/private/voice-outage-20261016/install-*-1612.*`；私密回执没有加入源码或签名包。

# 录音豆设备联调版

入口：登录本人空间 → 我的 → 连接录音豆。设备录音开始和结束使用实体按键。本次先实现录完再导入；没有远程开始录音、实时对话或 Wi-Fi 下载。

首次连接：允许附近设备权限（旧 Android 为位置权限），打开蓝牙，点准备连接。SDK 鉴权成功后扫描，选择自己的录音豆。首次使用点绑定，把录音豆放进充电盒，闪灯时按盒上按钮。只有收到设备确认才显示绑定成功。

连接后核对真实电量、固件、存储信息；点击读取录音列表，选约 30 秒的录音下载。请保持页面在前台；切后台、离开页面或换账号会关闭连接，已保存文件保留。

“手机已保存”表示 SDK 完成文件回调后，App 检查了本机文件、路径和 SHA-256。传输进度或设备状态码不会单独触发这一状态。可以导出原始 `.raw` 文件和不含授权令牌的连接记录；文件保存依赖实际设备回调，模拟器没有伪造已下载录音。

试听按厂商文档的 160 字节/20 ms 裸 Opus 帧解码为 16-bit PCM WAV。会拒绝不同分包、非法帧时长和不一致的解码时长；失败时保留原件并提示导出。手机已有文件再次读取时校验哈希，当前账号与人物范围外的录音不显示。本页不自动上传、不删除设备录音。

## 构建与配置

需要 JDK 17、Android SDK 35、Gradle 8.9。Kotlin 2.2.21、coroutines 1.11.0、OkHttp 5.2.1、Ktor 2.3.13 与厂商新版 SDK 对齐；额外包含 Ktor logging 和 SpongyCastle，避免仅编译通过但初始化缺类。

将交接包中经校验的 Android AAR-layout ZIP 复制为本地 `.aar`，保持内容不变。库留在仓库之外。构建：

```powershell
gradle :app:testDebugUnitTest :app:assembleDebug '-PrememberSoundcoreSdk=D:/private/soundcore-1.3.02.aar' '-PrememberRequireHardwareSdk=true'
```

正式内测包使用 `tools/delivery/build_signed_internal.py --signing-dir <私有签名目录> --soundcore-sdk <AAR> --gradle <Gradle启动器> --output <新目录>`。它要求 Android 源码已经提交，验证原签名和非 debug 包；不会生成新签名。

服务端配置：`REMEMBER_WORK3200_APP_ID`、`REMEMBER_WORK3200_APP_KEY`、`REMEMBER_WORK3200_ENVIRONMENT=DEVELOPMENT`。本批比赛凭据已实际验证仅测试环境可用，正式环境返回 app_id 不存在。鉴权协议见 [跨模块说明](../../../docs/architecture/work3200-device-contract-proposal.md)。

接口暂不可用时，手机导出本机授权申请。开发电脑在 backend 虚拟环境运行：

```powershell
python tools/work3200_provision.py --business <私有业务配置.json> --request <手机导出的申请.json> --output <新的短期授权.json>
```

把生成文件私下传给同一手机，在 App 中导入。授权文件含短期令牌，应私下传递；不含业务 app_key。文件过期时需重新生成，未过期的授权缓存在 Android Keystore 加密存储中。

## 验证范围

本轮本机验证：Android 单元测试、厂商 SDK 在 Android 15 模拟器内在线鉴权、440 Hz 合成固定帧 Opus 解码、虚构账号登录和设备页面导航。合成输入位于 androidTest/assets，不打入用户 APK。

实物待验：vivo 手机权限和发现、充电盒绑定、真实电量/固件/列表、约 30 秒录音下载及清楚试听、断开重连、重复下载。实际文件的编码、双声道意义和音质不能由模拟器结果代替。后续上传到转写和记忆流程单独接入并验收。

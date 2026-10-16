# Soundcore Android 1.3.02 能力台账

范围：用户提供的 Android AAR 与配套 ToB 文档，适配勿忘我 Android；不是官方 soundcore App 全部云端功能，也不是 iOS 1.3.01 验收。来源是本机私有交接包，不复制凭据或 AAR 到仓库。

下表“接入”表示适配层存在真实 SDK 调用和对应产品入口。实体录音豆尚未接到本开发环境，所有蓝牙、Wi-Fi、日志、升级实物结果均待验收。静态签名/回调覆盖不能替代实物验证。

| SDK 方法 | App 入口及处理 |
|---|---|
| getVersion / getProductCode | 设备维护显示当前 SDK 与型号 |
| initSDK / registerBusinessCallback | 服务端短期授权、真实 SDK 鉴权、作用域事件监听 |
| startScan / stopScan | 首页准备连接、扫描/停止、拒绝权限与超时提示 |
| connect / disconnect / close | 身份作用域会话，前台服务，切页保持；退出/换人物关闭 |
| getDeviceInfo | 电量、固件、存储、录音快照；维护查看序列号、Wi-Fi/充电盒版本 |
| isDataTransferring | 维护前检查传输占用，拒绝与下载/录音争抢 |
| syncTime | 每次连接自动同步，维护可重试；UInt 的 JVM 名称按 AAR 绑定 |
| bindingDevice(true/false) | 首次绑定实体确认；解除绑定需用户确认 |
| pauseRecord / resumeRecord | 首页暂停/恢复已开始的录音；不冒充从空闲开始录音 |
| acquireRealtimeAudioData | 实体开始回调后申请，读取片段计数与标记；结束后完整文件校验 |
| getAllAudioRecordFiles | 读取完整分页列表，结束后按准确 fileId 自动同步 |
| startSyncAudioFile | 蓝牙下载，15 秒阈值由 SDK 切换 SPP；同一保存、解码、试听入口 |
| startSyncAudioFileByWIFI / closeWIFITransport | 单文件 Wi-Fi 下载、权限、状态、取消、错误与关闭；不以热点连通冒称文件完成 |
| deleteFiles | 单个设备录音确认删除，刷新列表；保留本机副本 |
| setFindMyEnable | 维护中的开关及结果；SDK 不提供本 App 的位置地图 |
| resetDevice | 明确确认后重置，展示结果并等待重新连接 |
| requestDeviceLogList | 查询日志及采集状态 |
| setDeviceLogEnableCollection | 开/关采集，文档参数 level=0/module=111；该模块参数仍属厂商约定 |
| setDeviceLogTransfer | 单日志下载/停止、真实进度，私有会话目录保存和手动导出 |
| deleteDeviceLogFile | 选中日志并确认删除，成功后刷新 |
| startCombinedOta | 导入官方材料并校验型号/版本/hash，用户确认后执行，SDK 电量/录音/占用检查与进度/结果反馈；工具包未含固件，未刷机 |

`getArrayList` 字节码仅创建空 ArrayList，不是设备能力；构造器和 Kotlin synthetic accessors 也不构成业务功能。不会为凑覆盖数调用它们。

## 38 个业务回调

- 连接状态之外的全部业务回调均在 `Soundcore1302Bridge` 覆盖：录音状态/时长/实时片段，离线列表及错误，传输状态/进度/补包/拒绝/解码文件/两种重点回调，设备信息及错误、电池/充电变化，绑定/解绑发送与实体确认/错误，同步时间/Find My/重置/删除结果，Wi-Fi 启动等待/发现/连接状态/错误/关闭/实时切换，SPP 通道，设备日志采集/列表/传输/删除/分片进度，以及 OTA 错误。
- `onRealtimeTransferSwitch` 的第三参数是 **fileId**，不是模式编号。它表示 Wi-Fi 传输切换到实时录音。
- `onAudioRecordStatusChanged` 的 duration 只有 STOP 有效，fileId 只有 RECORDING 有效。停止/暂停缺 ID 时仅关联当前活动录音。
- `onTransferFileStatusChanged` 的 markTimeStampList 和 `onDecodeFileMarkers` 是毫秒时间点；`onReceiveAudioFragment.isMark` 只做实时提示，不把 sequence 猜成毫秒。
- OTA 主回调包含阶段、百分比、错误、完成；其他可选硬件/TWS 扩展回调不作为 D3200 升级成功条件。

## SDK 没有提供的产品功能

- 无公开的空闲远程开始/结束录音组合；请使用录音豆自锁实体按键。暂停/恢复不能替代开始/结束。
- 无公开的写入设备重点 API；手机“标记重点”保存在 App，与设备双击重点区分来源。
- 不提供转写、字幕、AI 整理或 AI 权重。重点 AI 优先整理由本项目实现。当前实时片段接收不等于实时字幕。
- 无本 SDK 的 Twin 回答扬声器播放接口；声音播放仍在手机/耳机。

## 官方固件资料包格式

本 App 用 ZIP 包裹官方提供的原始 bin 和核对资料。ZIP 顶层 `manifest.json`：

```json
{"product":"D3200","sdk":"1.3.02","bt":{"version":"03.30","file":"official-bt.bin","sha256":"官方文件的64位SHA256"}}
```

可加 `wifi`，结构同 `bt`，至少一个固件。不从文件名猜版本；内部单 bin 最大 8 MiB，ZIP 最大 20 MiB。hash 只证明文件与清单一致，不证明发行者身份，必须由官方渠道取得并核实。现有工具包没有固件，不制作测试 bin 供刷写。

## 本轮重点整理规则

读取 `metadata.hardware.markers` → 保留 ASR 句子毫秒时间轴 → 取标记前10秒/后5秒内完整句子 → 与本人核对文字唯一匹配 → AI 输入重点优先级2/普通1 → 输出证据验证 → 有重点证据的记忆优先显示。优先级不是置信度或模型参数。无时间轴、改写、重复无法对应时明确不加权。详见 `docs/architecture/work3200-sdk-complete-20261016.md`。

## 验证入口

`tools/delivery/audit_soundcore_api.py --jar <私有 classes.jar> --output <本地报告.json>` 检查 public 方法和回调是否有适配，报告注明静态边界。APK 编译、模拟器状态/权限/存储与云端链路的具体结果另写交付记录，不在此预先宣称通过。

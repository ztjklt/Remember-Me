# 录音权限与本地存储

本文说明 Android Capture 阶段的麦克风权限、录音文件和本地播放行为。录音文件属于敏感的原始个人数据；当前实现只在设备本地保存，不会自动上传。

## 麦克风权限

- 应用在用户进入 Capture 并主动开始录音时才请求 `android.permission.RECORD_AUDIO`，不会在启动或浏览其他页面时提前弹窗。
- 请求前在界面说明用途：录制用户主动说出的内容，音频保存在此应用的私有存储中。
- 用户拒绝后不启动录音。Capture 显示拒绝状态和重试入口；如果系统不再显示权限弹窗，界面提示用户前往系统设置允许麦克风权限。
- 录音启动、暂停、继续、保存或播放失败时显示可见错误，不将失败当作成功状态。
- `RECORD_AUDIO` 是危险权限，必须在运行时获得授权。卸载应用会撤销该授权。

## 文件与元数据

录音由 Android `MediaRecorder` 从设备麦克风采集，编码为 AAC，封装在 MPEG-4 音频容器中。当前配置为 44.1 kHz、单声道，MIME 类型为 `audio/mp4`，文件扩展名为 `.m4a`。

音频和对应 JSON 元数据保存在应用内部目录：

```text
<filesDir>/recordings/<随机 ID>.m4a
<filesDir>/recordings/<随机 ID>.json
```

`filesDir` 由 Android 按应用隔离，其他普通应用不能直接读取；此路径不需要存储空间运行时权限，也不会出现在公共媒体库。JSON sidecar 记录音频绝对路径、实际录制时长（毫秒）、MIME 类型、文件字节数、采样率、声道数和 `created_at`（RFC 3339 时间戳）。文件大小在录制结束后从最终文件读取。

应用通过 sidecar 查找最近一次完整且仍存在的录音。Capture 可以显示元数据、调用本地播放器重新播放文件；播放不会向后端或其他应用发送音频。

## 生命周期与备份

- 应用内部文件会随应用卸载而删除。清除应用数据也会删除录音和 sidecar。
- 重新安装、清除数据或恢复到另一台设备后，不保证录音仍可用；本地 Capture 目前没有云端副本或导出流程。
- Manifest 当前启用 Android Auto Backup。系统备份是否包含这些文件取决于设备和系统备份设置；不要把设备备份视为音频的可靠副本。后续若调整备份规则，应将 `files/recordings` 作为敏感录音单独评估。
- 当前不提供单条录音删除、加密密钥管理或云同步。上传与 Episode 处理属于后续 Golden Path 集成，不属于本地录音实现。

## 验证

```bash
cd apps/android
./gradlew testDebugUnitTest assembleDebug
./gradlew connectedDebugAndroidTest
```

仪器测试使用 fake `AudioCaptureService` 验证 Capture 状态和界面交互，不会写入真实录音。真机麦克风、暂停/继续和音频解码仍需在 Android 设备上手动验收。

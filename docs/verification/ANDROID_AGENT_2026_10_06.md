# Android Agent 页面更新 — 2026-10-06

在 `feature/ai-agent-core` 普通分支继续更新现有安卓原型，按用户要求复用网页版流程。
Backend、AI Core、Memory 提取、数据库和共享契约未修改，无新增运行依赖。

## 行为

- 录音页可直接连接已有资料；上传完成进入理解页时显示本次录音原文。
- 主页面显示原文、当前理解、问题与回答、本人校正及更新结果，技术字段和依据折叠。
- 提问仅调用一次 `/calibrations`，显示并校正同一份保存的回答。变更问题或 revision
  后不能提交旧回答的校正；请求使用锁定时的 revision，由 Backend 最终检查 CAS。
- 保存校正后保留原回答和本人文字，再读取理解和材料；读取失败保留已保存状态，
  可以刷新重试。再次提问清除上一轮校正。撤除材料时先清除缓存，后续读取失败也不显示旧材料。
- Actor/Subject 切换和同意失效继续清空会话；供应商密钥不进入 App。Backend token 仅在内存。
- APK 为 debug `1.1-agent` / versionCode 2，最低 Android 8（API 26），目标 API 35。

## 验证

在 `apps/android` 运行：

```bash
./gradlew --no-daemon test assembleDebug assembleDebugAndroidTest lintDebug
```

本机使用 `/tmp/remember-android-tools` 下的 JDK 17、SDK 35，通过 `JAVA_HOME`、`ANDROID_HOME`
配置；`GRADLE_USER_HOME` 指向忽略的 `build/android-gradle`。工具和 APK 未提交。

- Debug、Release 各 31 个单元测试通过；包含真实 HTTP adapter 消费 Backend fixture、
  一次锁定、校正保留、版本/问题限制、刷新失败、撤除后读取失败及会话隔离。
- App 与 instrumentation APK 构建通过；Lint 0 error、28 warning，涉及既有依赖版本、
  缺少图标和构建配置提示。未配置独立 format/typecheck；Kotlin 编译与 staged whitespace 检查通过。
- APK 签名校验通过，确认包名 `me.remember.app`、versionCode 2、versionName `1.1-agent`。

新增 Compose 页面测试已编译，未执行：本机 API 35 软件模拟器启动未完成，用户选择先交付
APK；测试模拟器已停止。本轮未连接真机，没有重新验证手机现场录音或真实 ASR/LLM。
单元测试的固定材料不作为语音或 LLM 质量验收；服务端问答实现保持此前已验证的版本。

## 安装与连接

交付安装包位于 `build/releases/remember-me-1.1-agent-debug.apk`，原始构建产物位于
`apps/android/app/build/outputs/apk/debug/app-debug.apk`。
SHA-256：`704923cf8561c5e9f633aa62fa0c131b8c44330871bb6ced912020fa35de6b7c`。
同签名安装可执行
`adb install -r <APK>`。手机仍需访问运行中的 Backend；当前 demo 监听电脑回环地址，
通过已连接的 adb 执行 `adb reverse tcp:8000 tcp:8000`，App 地址填 `http://127.0.0.1:8000`。
Android 11 及以上可使用 [官方无线配对调试](https://developer.android.com/studio/run/device#connect-to-your-device-using-wi-fi)，
无需 USB；模拟器填 `http://10.0.2.2:8000`。使用已有演示会话的 Actor Token、Subject ID 和
RECORDING Consent ID，明确同意 Cloud Twin。未建立自动更新渠道或发布到商店。

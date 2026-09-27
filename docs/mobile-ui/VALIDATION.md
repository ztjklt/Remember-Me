# 验证记录与设备验收

日期：2026-09-27。当前为本地实现验证，未合并、推送、发布或启动远端 CI。

## 本轮已执行

| 检查 | 结果 | 证明范围 |
|---|---|---|
| Android `testDebugUnitTest` | 18 项通过，0 失败 | 包含 9 项新流程 / 来源 / 兼容测试，9 项原有回归 |
| Android `assembleDebug` | 成功生成 APK | Kotlin、资源、依赖和打包成功；不证明实际录音成功 |
| Android `assembleDebugAndroidTest` | 成功生成测试 APK | 录音控件 / 响应式档案测试可编译；尚未连接设备执行 |
| Android `lintDebug` | 0 error，25 warning | 主要为继承的依赖版本提示及旧 SDK 分支；未为本 UI 改造升级工具链依赖 |
| 原型交互流程 | 通过 | 模拟录音、暂停、继续、保存、转写、编辑、仅保存、明确同意整理、删除、搜索 |
| 原型布局矩阵 | 48 组合通过 | 360 / 412 / 375 / 430 CSS px × 普通 / 200% 深色减少动态 × 6 页面；无横向溢出、底部操作在视口内 |
| 原型场景 | 空、处理中、失败检查完成 | 固定示例状态，不代表后端或麦克风能力 |
| 指定文字颜色对比 | 22 组合通过，最低 4.83:1 | 指定实色文字 / 背景组合；不涵盖所有系统控件合成色 |
| iOS Swift 语法解析 | 4 文件未报告语法错误 | tree-sitter-swift；不证明 SwiftUI 类型检查 / 构建成功 |
| iOS 颜色资源 | 7 组浅深色数值核对通过 | 与设计令牌一致 |
| `git diff --check` | 通过 | 未发现 diff 空白错误 |

## 新增单元测试覆盖

1. 转写与核对不会调用整理适配器；机器原文与核对文字分开保留。
2. 未核对或未明确同意时，整理调用被阻止。
3. 整理失败保留原音与两份文字；重试后只有一套当前记忆；成功重复调用不再发出请求。
4. 缺少本机 ASR 或整理适配器时，原音及已有文字保留。
5. 不在确认文字中的非空证据引文会被拒绝。
6. 修改核对版本后旧结果转为历史，不把旧证据伪装成当前结果。
7. 协程取消保留可重试的中断状态并继续抛出取消。
8. 旧元数据不虚构确认；新元数据往返保留来源；处理中状态可恢复为中断。
9. 订阅的档案发出删除后的新结果，同时保留来源录音和转写。

## 可复现命令

Android 需要 JDK 17、Android SDK 35 和项目 Gradle wrapper：

```powershell
cd apps/android
.\gradlew.bat testDebugUnitTest assembleDebug assembleDebugAndroidTest lintDebug --console=plain
```

原型启动本地 HTTP 服务后：

```powershell
npx --yes --package @playwright/cli playwright-cli -s=remember-ui open http://127.0.0.1:8768/docs/mobile-ui/prototype.html --headed
npx --yes --package @playwright/cli playwright-cli -s=remember-ui run-code --filename docs/mobile-ui/verify-prototype.js
python docs/mobile-ui/verify-design.py --ios-root D:/codex_work/remember-me-ios-ui
```

本地输出：`output/android-validation.txt`、`output/playwright/`；这些临时输出已忽略。可跟踪的结果摘要为 `prototype-verification.json` 和 `contrast-verification.json`。原型图片只表示设计原型，不是原生 App 截图。

APK：`apps/android/app/build/outputs/apk/debug/app-debug.apk`。测试 APK：`apps/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`。

## 真实能力限制

- 当前 APK 未附带被 Git 忽略的 `paraformer/model.int8.onnx`。尝试转写会显示“本机转写暂不可用”；不回退云端。要验证真实转写，需要单独提供许可合适且与现有 sherpa 配置匹配的模型。
- 正常 Android 入口未配置 `ReviewedMemoryProcessor`；整理成功 / 失败 / 幂等性使用测试适配器验证。真实远端整理尚未接通，不能把原型中的成功记忆当作已接通证据。
- `adb devices` 当前没有设备。麦克风、电平、播放器时间、拖动、Android 权限交互、文件写入失败恢复尚未通过设备实测。
- iOS 当前只进行了源码与语法检查；Xcode、模拟器、iPhone、配对 Mac 服务联调均待完成。
- 没有安排或冒充 5 位目标用户参与测试。

## Android 真机执行单

每项记录设备型号、系统版本、APK 构建、网络条件、观察与证据；失败不勾选。

- [ ] 首装默认今天页，无演示人物、假记忆或可点击假对话。
- [ ] 同意前不启动麦克风；拒绝后保留清晰重试 / 设置入口；重新授权后可录。
- [ ] 开始、暂停、继续、保存计时与状态同步；实际发声时电平变化，暂停时停止。
- [ ] 系统返回 / 关闭询问保存或继续；进入后台结束保存；旋转不丢失 ViewModel 内容。
- [ ] 飞行模式能录音、保存与播放；缺失 ASR 权重不影响原音。
- [ ] 播放结束、暂停、继续、拖动、切换录音均显示实际状态；录音开始前停止播放。
- [ ] 录音成功立即确认保存；强制结束处理中进程后不自动重新上传，显示中断。
- [ ] 原始机器转写与修改后文字分别保留；抓取适配器测试日志确认核对前无整理 / 命名调用。
- [ ] 整理失败可重试；原音、转写不丢；成功重试不重复当前记忆。
- [ ] 删除记忆后详情与列表一致，来源录音仍可播；旧文件可读。
- [ ] 记录信息损坏时有效原音可恢复；不能解码的文件不伪装成成功录音。
- [ ] 360 / 412 dp，普通 / 200% 字号，深色、减少动态、TalkBack；键盘不遮挡确认操作。
- [ ] 中端 Android 真实录音、连续滚动和切页不卡住主要操作；记录设备与观察，不虚构 FPS。

## iOS 与用户验证

iOS 按 `apps/ios/UI_ALIGNMENT.md` 构建，然后覆盖 375 / 430 pt、大字、深色、减少透明度 / 动态和 VoiceOver；回归既有证据、纠正、Twin、校准、声音授权。原有单待处理录音与配对服务依赖应在验收时明确。

5 位接近目标用户分别执行“录一段话 / 找回原音 / 确认转写”，记录独立完成情况、耗时、犹豫位置和误解；目标至少 4 人无需指导完成。这只是小规模设计验证，不能推导普遍易用性。

| 参与者 | 三任务完成情况 | 是否提示 | 犹豫点 / 误解 | 改进建议 |
|---|---|---|---|---|
| 待招募 1–5 | 待执行 | 待记录 | 待记录 | 待记录 |

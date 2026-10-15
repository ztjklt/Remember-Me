# Twin Android 交互整合交接（2026-10-12）

本轮把独立交互工作树 `D:/codex_work/remember-me-interaction-polish` 的提交 `d8039dbb7a47eba7837be4250f6d0cd30e96978e` 按 diff 移植到当前 Twin Android。保留当前未提交的人物理解、亲友补记、独立音频、校准及声音权限实现；没有整文件覆盖既有页面，也没有 cherry-pick。仅修改 Android 和本交接文档。

后续状态：本文件保留 r1 当时的构建与争用历史。原来待验的 13 项组件检查已在 **r2 的独占窗口**实跑通过，并与第二批音频/页面检查合计 23/23；r2 两角色只读验收也已通过。最新包、截图与限制见 [r2 交接](TWIN_INTERACTION_R2_CLIENTS_2026-10-12.md)，不再把这里的历史“待独占”当作当前 r2 状态。

## 包与配置

输出目录：`apps/android/output/twin-integrated-20261012/`。

| 文件 | SHA256 |
| --- | --- |
| `RememberMe-twin-integrated-20261012.apk` | `2e232ed24d3d91f09fd3fc2dfc47e113ba0d30ab52609f0c096cd4a4493717a9` |
| `RememberMe-twin-integrated-20261012-androidTest.apk` | `1b85674ecc67e1d9bfc4ca8990edea7f95424275228412f5730438d4ce6f3481` |
| `RememberMe-persona-local-before-integration.apk`（保留上一版） | `1071f195973b5f3f46c21421b6e5e3defa676215102b05eaea58b34a88771062` |

生成的 `BuildConfig` 已核查：包名 `me.remember.app`、版号 `0.9.3-internal-twin-integrated-20261012`、versionCode `20261017`、debug 服务 `http://10.0.2.2:8891`。未加入交互预览 Activity/包名，未改 internal 的服务默认值。未提交、推送、部署、重启后端或修改服务数据。

## 改动与行为

- 复用 `InteractionComponents` 与 `ActionFeedback`：保留按钮文字、稳定触控区，提供按压反馈、真实请求的等待/返回/失败状态；普通按钮至少 52dp，简明模式至少 60dp。减少动效及系统动画关闭设置得到保留。
- 请求反馈按单次操作 ID 与当前账号/人物关联。打开确认框不会提前显示成功；真正确认后才绑定所发请求。取消、失败、另一项请求和账号切换不会冒充本按钮成功。
- 设置、登录、故事录制、上传/核对、分享、问答接入统一组件；亲友补记的上传/转写/核对/提交/处理/撤回、信件、校准对照、声音开关及权限也接入。控制型开关使用保存后返回的真实状态，等待时防止重复提交。
- 成功文案限定于已返回的请求，例如“已提交整理”“对照已返回”“声音已取回”，不表示后续整理完成、声音播放完成或模型业务全部完成。ASR 返回 `failed` 的音频仍保留在草稿中，并进入失败反馈。
- 危险操作先明确确认；普通确认按钮始终可用。非简明模式额外提供 1.5 秒长按确认，松开/拖离/进入后台取消，不以系统动画时长代替实际计时。
- “看原文”独立调用已有 `GET .../companion/contributions/{id}`，显示返回的实际作者、分类、全文及原音入口。不调用 Twin 问答，也不以双方模型使用许可为阅读开关。刷新发现原文已不可访问、撤回或版本变化时关闭旧详情。
- 兼容可选 `coverage` / `omitted_points`，不依赖它们才能显示旧答案。仅 `coverage=partial` 时补充一行“已回答有依据的部分”；若正文已有该句或固定尾句“部分问题尚未回答。”则不重复。旧答案的 null 不被解释为完整。
- 原有花田、简明模式、左右翻单条人物理解、来源/条件详情、evidence/persona 模式、音频核对、校准比较及手动人物确认边界保留。

来源 hunk 清单在输出目录 `port-hunks.json`：29 个 hunk 原样可应用，3 个 `NativeWorkbenchScreen` hunk 因 Twin 后续代码而手工对齐。该清单的 `applied=false` 表示原 hunk 无法直接套用，其对应功能已手工合入，并非丢弃。其余扩展是当前 Twin 新页面的请求反馈接线。

## 验证结果

最终执行：

```powershell
$env:JAVA_HOME = 'D:/codex_work/remember-me-toolchain/jdk/jdk-17.0.20.1+1'
$env:ANDROID_HOME = 'D:/codex_work/remember-me-toolchain/sdk'
$env:GRADLE_USER_HOME = 'D:/codex_work/remember-me-toolchain/gradle'
./gradlew.bat testDebugUnitTest assembleDebug assembleDebugAndroidTest --console=plain
```

执行目录 `apps/android`，最终 `BUILD SUCCESSFUL in 28s`。JUnit XML 汇总：**97 tests / 22 suites，0 failures / 0 errors / 0 skipped**。日志：`apps/android/output/twin-integrated-20261012/final-build.log`。Android 范围 `git diff --check` 通过；仅已有文件的 LF/CRLF 提示。

新增有意义回归包括：操作 ID 与成功/失败反馈隔离；“看原文”只发送一次有身份的 GET，模型许可均为 false 仍可读取；撤回、权限或内容版本变化关闭旧原文；旧答案、完整答案、部分答案及已含尾句的提示行为。

`InteractionComponentsTest` 的 **13 项设备组件测试已编译，设备验收待独占窗口完成**。覆盖按钮请求对应关系、确认后的请求绑定、失败不翻转开关、长按取消/后台/一次提交、简明模式与减少动效等。它们是隔离组件测试，不是服务验收证据。主协调已允许安装和仅运行该测试类，实际经历如下：

- 首跑 13 项均因测试宿主直接在测试线程调用 Activity `setContent` 而失败，尚未进入断言。已仅将测试宿主改为 Compose rule 的 `ui.setContent`；原日志 `interaction-device-tests.log` 保留。
- 测试 APK 单独重建成功（47 秒）。第二次已进入断言，但 10:26:23–27 UTC 设备同时运行另一个 `me.remember.app.interaction` 的 `InteractionGalleryActivity`，并有 shell 打开主 Activity，导致测试宿主被切走、截图连接争用及生命周期超时。该次日志 `interaction-device-tests-after-harness-fix.log`，争用摘录 `device-contention.log`；不计为通过。
- 主 APK 没有因测试宿主修正而改变；两次均只 `adb install -r`，没有卸载或清空已有应用数据。测试类本身没有业务 API/账号/麦克风调用。
- 随后核查 `D:/codex_work/remember-me-toolchain/avds`，仅有正在使用的 `remember-me-integration`（5554），没有第二个空闲 AVD；没有启动、复制或停止其他模拟器及对话进程。等待独占，不反复重试。
- 主协调随后批准创建独立临时 AVD `remember-me-twin-review-20261012`，条件是复用已安装映像、5556 端口、资源足够。实际创建前再次检查发现 5556 已被另一个 `experience-ui` AVD 占用（emulator PID 58912 / qemu PID 51464），且可用物理内存约 385 MiB / 总 16 GiB。因此按资源不足条件停止新增计划，**本任务没有创建新的 AVD 路径/磁盘**，未接管两台现有设备。

可在主协调确认设备独占后运行（目录 `apps/android`）：

```powershell
& 'D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe' -s emulator-5554 install -r 'output/twin-integrated-20261012/RememberMe-twin-integrated-20261012.apk'
& 'D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe' -s emulator-5554 install -r 'output/twin-integrated-20261012/RememberMe-twin-integrated-20261012-androidTest.apk'
& 'D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe' -s emulator-5554 shell am instrument -w -r -e class me.remember.app.InteractionComponentsTest me.remember.app.test/androidx.test.runner.AndroidJUnitRunner
```

以上命令保持已有应用数据、不卸载。不要无筛选运行所有设备测试：同目录另有需要明确授权、私有账号及阶段参数的真实服务验收测试。

## 待主协调统一进行的设备验收

本轮已替换安装新 APK，并按明确授权运行隔离组件测试；尚未生成本轮新的真实业务页面截图，也未主动打开业务页面。此前 `PERSONA_CLIENTS_2026-10-12.md` 中的页面/播放截图属于上一版，不可充作本包新反馈验收。

建议正常字号 1.0 取这些实际页面状态：

1. 登录中及失败后的可重试按钮；成功登录后的花田与左右切换人物理解。
2. 已接受补记卡的“看原文”，实际作者、正文、原音；模型许可关闭仍能按已有阅读权限读取。
3. 问答提交中的完整按钮文字、实际返回状态；有真实 partial 答案时仅出现一次短提示。
4. 亲友上传/转写/核对的真实请求状态，以及校准比较返回页面。写流程须由主协调单独排程。
5. 声音权限保存时不提前翻转、真实保存答案取回声音、随后实际播放；不要把“声音已取回”当作播放成功证据。
6. 简明模式和减少动效下的确认操作，保持明确“确认/取消”，且简明模式不要求长按。

本轮构建与单元测试不证明真实模型问答已修复，不替代声音、ASR、权限或当前后端版本的联调。上一轮原生贡献单问题的 502 仍按既有报告保留，后续模型结果由主协调报告。

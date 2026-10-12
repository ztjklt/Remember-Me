# Twin Android 第二批体验整合（2026-10-12）

本轮在第一版融合包之上，逐项合入右侧交互工作树提交 `ce601ac720c5d9998ffcde88f0e045a52f1ca257` 的 main 源码差异。没有引入 debug Gallery、预览数据、额外包名或服务配置；没有改共享 API、后端、模型或来源资料。

## 交付包

- `apps/android/output/twin-integrated-r2-20261012/RememberMe-twin-integrated-r2-20261012.apk`
- SHA256：`9a2e8ba1663688cb446619714623c1dcc5a8a8dba634a6a5b64539c557b81c76`
- 生成 BuildConfig 已核查：`0.9.3-internal-twin-integrated-r2-20261012`，versionCode `20261017`，包名 `me.remember.app`，debug 服务 `http://10.0.2.2:8891`。
- 第一版融合包仍在 `apps/android/output/twin-integrated-20261012/`，SHA256 `2e232ed24d3d91f09fd3fc2dfc47e113ba0d30ab52609f0c096cd4a4493717a9`，未覆盖。
- 更早 persona-local 包同样保留。internal 的包名和默认 HTTPS 服务未改。
- 最终测试 APK 为同目录 `RememberMe-twin-integrated-r2-20261012-androidTest.apk`，SHA256 `2841c3259b67b455328cdb77904f8534932d9b967d3e6312fee6f581fbbc1876`。其后的变动只涉及真实只读验收测试的定位/等待，主 APK 与组件实现未再改变。

## 本次变化

8 份 main 差异 patch 可直接对齐，`GardenMemoryReader` 依据当前 Twin 声音状态手工合并。patch 保存在 r2 输出目录供回看，未整文件覆盖已有页面。

1. 增加 `ExperienceComponents`：当前页面轻微进入、固定高度加载槽、可展开的实际失败原因、准确区分待机/录音/暂停的状态图形。没有假波形、假进度或按计时自动完成。
2. 导航切换收起键盘；页面动画只处理当前内容，不保留上一身份的离场副本。简明模式、减少动态效果和系统动画关闭时直接进入。
3. 音频拖动先本地预览，松手只 seek 一次；切换身份/来源取消旧拖动，未知时长或准备中不拖动，停止仍可用。接入花田原音、全局播放器、本机录音及核对原音。
4. 播放器增大触控区和时间/状态文字，保留真实的“AI 分身回答／亲友声音／完整原音”来源区分，不把生成声音标成原音。
5. 人物故事翻页与当前 Twin 新增的已确认理解翻页均遵循减少动态效果。
6. 补全自然色 surface 层级及字体角色，设置入口使用统一图标底板。花田、人物理解详情、Twin 模式、亲友原文/授权、专属信和校准流程保持现有实现。

第一版融合中的真实请求 ID 反馈、确认后才提交、“看原文”独立 GET、partial 单行去重提示继续保留。

## 实际验证

- `testDebugUnitTest assembleDebug assembleDebugAndroidTest`：**BUILD SUCCESSFUL in 50s**。
- JUnit XML 汇总 **97 tests / 22 suites，0 failures / errors / skipped**。
- 获得主协调独占窗口后再次检查 5554 无其他 instrumentation，使用 `adb install -r` 安装，保留应用数据。
- 在 `emulator-5554` 实跑 **23/23 组件设备测试通过，53.287 秒**：第一批 13 项，第二批源提交的 9 项非预览测试，加 1 项 Twin 声音来源标签检查。
- 回归覆盖确认后的请求绑定、失败不翻转开关、长按取消/后台/仅一次提交；音频拖动预览/释放一次 seek/无障碍进度/来源切换/取消拖动/停止加载；加载不挤动内容、错误详情、录音状态和 200% 字号深色播放器。
- 第一轮历史争用失败仍保留在第一版输出目录，不被本次成功日志覆盖。该次没有接管或终止对方测试。
- **r1 遗留的 13 项组件待验已在 r2 窗口解决**；这里证明的是当前融合实现通过这些检查，不追认历史 r1 APK 在争用期间已通过。
- 本轮只读验收测试另加原文实际点击和独立输出目录；测试 APK 增量构建 **4 秒成功**，主 APK 未改变。它不新增业务操作。

日志在 r2 输出目录：`final-build.log`、`component-device-tests.log`、`readonly-test-build.log`。组件截图属于隔离组件状态，不能当作真实业务、模型或录音成果。

## 原工作区复验

以下命令依赖原工作区保留的包和资料。新克隆应先按 [空库启动说明](TWIN_LOCAL_SETUP_2026-10-12.md) 配置；这些输出目录未上传。原工作区在 `apps/android` 目录，沿用本机既有 JDK 17、Android SDK、Gradle 缓存，并将 `adb` 放入 PATH：

```powershell
./gradlew.bat testDebugUnitTest assembleDebug assembleDebugAndroidTest --console=plain
adb -s emulator-5554 install -r 'output/twin-integrated-r2-20261012/RememberMe-twin-integrated-r2-20261012.apk'
adb -s emulator-5554 install -r 'output/twin-integrated-r2-20261012/RememberMe-twin-integrated-r2-20261012-androidTest.apk'
adb -s emulator-5554 shell am instrument -w -r -e class me.remember.app.InteractionComponentsTest,me.remember.app.ExperiencePolishTest me.remember.app.test/androidx.test.runner.AndroidJUnitRunner
```

设备操作必须先协调独占。不要无筛选启动整个 androidTest 集合，其中有另需授权的真实写流程测试。

只读业务截图入口为 `apps/android/scripts/persona_readonly_live.py`：通过私有账号文件登录，使用正常字号 1.0；只读取当前资料、既存答案/声音/亲友原文，不调用新问答或声音生成。每次使用独立输出目录，发现现有 instrumentation 或目录已存在即退出，不自动重试。

本轮没有创建额外 AVD；既有两个 AVD 的争用/资源检查过程记录于第一版交接文档。后续清理无需删除本任务新建 AVD。

## 当前真实页面与播放

在主协调完成来源改动、冻结 v8 后，使用既有本地普通账号，正常字号 **1.0**，两角色只读测试各 **OK (1 test)**。结果和实际截图位于 r2 输出目录的 `owner-final/` 与 `reader-final/`，均记录 `content_mutations=0`、`questions=0`、`fixture=false`。

| 实跑项 | 本人 | 亲友 |
| --- | --- | --- |
| 当前花田、人物理解与情境来源、人物内容、Twin 模式入口 | 通过，2 条已确认理解 / 11 段录音 | 通过，2 条已确认理解 / 10 段录音 |
| 亲友原文实际读取 | 通过 | 通过 |
| 当前保存回答 `ta_640e78e1bae6494d` | GET 读取并原生显示 | 未请求本人答案 |
| 既有声音 `va_f96425d23a5140f8` | GET 读取，实际播放器 playing=true 且 duration>0 | 未请求本人声音 |
| 亲友与专属信页面 | 通过 | 通过 |

“看原文”通过真实按钮的无障碍语义 OnClick 执行，随后等待实际 GET 返回并断言弹窗正文。不是直接填入 UI 状态。读取 `cc_10b6bd8d108749a9aafa`，两角色均显示实际作者、个人看法分类与完整正文；返回 `model_use_author_allowed=false`、`model_use_owner_allowed=false`，确认已有阅读权限不依赖模型许可。

保存回答和已有声音通过原生工作台 model 的只读加载方法调用既有 GET，然后检查实际 Compose 内容/MediaPlayer 状态；本轮没有点击生成声音按钮，也没有发起模型问答。**播放通过不代表新一轮真人听感验收**。亲友新回答/声音、上传/ASR/审批/撤回等写流程、校准再比较、真机和完整 TalkBack 操作不在本次 r2 实跑范围。

可直接使用的截图：

- [本人理解与情境依据](screenshots/twin-20261012/03-understanding-evidence.png)、第二条理解与条件（原始截图留在本地）
- [本人当前保存回答](screenshots/twin-20261012/07-saved-twin-answer.png)、[本人实际播放](screenshots/twin-20261012/08-answer-playback.png)
- [本人看署名原文](screenshots/twin-20261012/05-owner-contribution-original.png)、[亲友看署名原文](screenshots/twin-20261012/09-reader-contribution-original.png)
- [收尾真实人物页](screenshots/twin-20261012/10-reader-understandings.png)

仪器测试中曾出现三段保留过程：`reader-readonly` 使用已撤回的旧 ID，页面正确不提供原文按钮；`reader-current` 坐标点击后测试提前读取空详情；`reader-verified` 已成功显示真实原文，但断言误把背景卡片与弹窗的相同正文当成唯一节点。最终修正仅限测试的等待、语义点击和弹窗限定，未修改生产代码、服务响应或内容。这些失败目录保留，不与最终两次通过混淆。

两角色测试完成后，通过读回 UI 层级再点击原生导航，已重新打开应用并停在 **亲友阅读 → 档案 → 人物**，已确认理解为 1/2；不是本人页面。最终截图 `end-reader-person.png` 已由助手看图核查；随后不再操作设备。

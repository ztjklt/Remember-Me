# 游客暗号托付调整与验证（2026-10-16）

追加审查发现限流匹配信号、包裹暗号泄露及本机上锁竞态等尚未修复的问题，见[审查记录](GUEST_ENTRUSTMENT_AUDIT_2026_10_16.md)。以下为实现时实际执行的验证，不代表覆盖了后续发现的新场景。

Product / Integration Owner 在本会话明确要求亲友使用游客模式、仅凭具体私密暗号进入专属记忆，并要求开始调整。范围与接口记录在[获批修订](../architecture/guest-entrustment-contract-2026-10-16.md)。本轮完成本地后端、iOS 和共享契约调整；没有部署服务、执行生产迁移或覆盖安装本人手机。

## 实际行为

- Twin 右上角「留下数字托付」进入隔离的五步引导：留给谁、录入／核对暗号、预览完整来源、开放条件、明确确认保存。接收者只填写人物称呼，不填写亲友账号。人物模型中的数字托付页面管理已保存的计划。
- 暗号可输入或用本机离线语音录入。不会落入普通聊天、Episode、人物模型或音色样本；识别失败不自动改用云端，临时原音在成功、失败、取消、后台和下一次启动时清理。手机、多人录音、通话或录音豆采集中会阻止私密输入，避免已有采集录下暗号。
- 最低筛查要求12个有效字符、至少6种不同字符，并拒绝常见口令、重复和泛泛喜好句（包含“爸我知道你其实爱吃的是香蕉”这个原例）。这些规则无法证明暗号只有双方知道，保存前仍要求本人确认它包含具体的非公开细节。
- 所选来源必须已核对；保存前预览全文、整段原音和连带记忆，并校验预览版本。当前公开或所选来源中出现暗号时拒绝保存。新资料不会自动加入计划；既有明确私密／保护标记不会因托付绕过原有来源规则。
- 游客无需接收者账号。在 Twin 普通聊天中说出完整暗号会先由服务端核验，再进入给对应人物的专属来源。可使用「本次是在说暗号」模式，让失败录入也不进入普通 Twin 问答。普通问答中说错或未说完的句子无法可靠地区分于普通聊天，不声称能自动保护任意近似句。
- 花园、原音、文字／录音问答与声音输出使用同一专属范围，一次只开放一份、最长10分钟。主动锁上、范围切换、到期、撤销或来源变化会清除临时对话并停止旧输出。暗号命中的原句及语音转写在返回客户端前脱敏，控制答复不参与后续问答前文。
- 原账号托付留在独立表和旧接口中，不自动降为游客暗号。未来开放仍需预先指定的照护人记录核验；暗号不自动判断身后状态。访客不训练或修改本人模型。

## 已执行验证

| 检查 | 实际结果 |
| --- | --- |
| Backend 全套 `.venv/bin/python -m pytest --tb=short --show-capture=no` | **913 passed / 6 skipped / 4 warnings**，211.16秒，exit 0 |
| 游客／新暗号托付／旧账号托付／迁移定向组合 | **86 passed**；新暗号专项21项、迁移5项（包含从0029已有会话与旧托付数据升级） |
| `cd packages/contracts && npm test` | **59 passed**；旧版本形状保留、新托付及扩展游客形状校验通过 |
| iOS `ECSConnectionTests`、`EntrustmentDraftTests`、`GuestAccessTests` | **78 passed**（48＋13＋17），iOS 27独立模拟器，签名构建及测试通过 |
| iOS `EntrustmentUITests`、`GuestAccessUITests` | **3 passed**；无接收者账号、弱暗号不能继续、离线录入入口、游客只读和主用户密码返回入口 |
| 补充托付外观检查（浅色／实际深色） | **1 passed**（同一用例分别运行两种外观），最终 `TEST SUCCEEDED`，截图已逐张目视复核 |
| `git diff --check` | 通过 |

后端日志：`/tmp/remember-guest-entrust-backend-regression.log`。6个外部条件跳过项不记作通过；4个警告为既有 Starlette／AnyIO 和 SQLite 日期适配弃用提示。后端使用真实数据库迁移、实际HTTP路由和确定性的 Twin／STT／声音替身，不冒充真实模型或本人语音验收。

iOS 命令：`xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe -destination 'platform=iOS Simulator,id=E1BB019A-7644-4BA6-8E69-43E34EE98D0F' -derivedDataPath /tmp/remember-entrust-ios -clonedSourcePackagesDirPath /tmp/remember-guest-ios/SourcePackages CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM= -only-testing:RememberMeTests/GuestAccessTests -only-testing:RememberMeTests/EntrustmentDraftTests -only-testing:RememberMeTests/ECSConnectionTests -only-testing:RememberMeUITests/GuestAccessUITests -only-testing:RememberMeUITests/EntrustmentUITests test`。日志 `/tmp/remember-entrust-ios-final-tests.log`，实际结果为 `TEST SUCCEEDED`。

首轮界面检查的系统外观参数未改变隔离预览的实际颜色；增加仅DEBUG的显式外观参数后，补充用例虽通过但 Xcode 在结果收集阶段停滞，等待后终止该次命令（exit 143），没有把它当成一次正常完成的测试。重新启动专用模拟器、关闭并行测试及冗余诊断收集后，最终外观检查正常结束：`-parallel-testing-enabled NO -collect-test-diagnostics never -resultBundlePath /tmp/remember-entrust-ui-verified.xcresult`，日志 `/tmp/remember-entrust-ios-appearance-final.log`，exit 0／`TEST SUCCEEDED`。

实际深色截图暴露了原生输入框默认提示文字对比度不足，已为亲友称呼、暗号和照护人输入框显式使用现有配色；上述最终外观检查在此修正后运行。没有修改正式应用的主题规则。首轮模拟器在键盘弹出时还记录了 `Invalid frame dimension` 警告，未导致测试失败；不据此称构建完全无警告。

最终浅色／深色截图和上述日志已保存在本地 ignored `build/guest-entrustment-20261016/`：`setup-light.png`、`setup-dark.png`、`backend-regression.log`、`ios-unit-and-ui.log`、`ios-appearance.log`。逐张检查了布局、文字可读性、暗号输入脱敏、基础规则、语音入口和确认开关。使用的是隔离虚构设置，不包含本人秘密或实际记忆。

专用的一次性模拟器在验证后关闭并删除；命令中的UUID记录实际执行目标，复跑时应替换为当前可用模拟器。

## 已覆盖的重要边界

无接收者账号、仅有私有托付而没有公共来源、错误及未激活暗号不提示接收者、完整语音命中与显式失败脱敏、暗号不落数据库／日志／对象存储／模型请求、独立云问答与声音许可、两份计划不合并范围、生成／ASR／原音读取／TTS中发生同来源范围切换时拒绝晚到结果、撤销和来源变化、10分钟过期、照护人门槛、跨游客会话的限流、旧数据升级保留。

独立代码复核发现并修复了两项主流程问题：控制答复ID不能作为下一问前文，以及已有后台采集不能录下设置中的暗号。相关回归已纳入上述最终检查。

## 交付边界

生产后端需包含迁移 `0030_guest_entrustment` 及本轮代码，新iOS入口才可与线上联用。当前源码不是已安装包的交付声明。本人在真机录下私密细节、亲友自然说出并继续交流、真实识别误差及声音听感，尚未验证。

暗号仅按完整文字及Unicode／空格／标点规范化核验，不进行LLM猜测或语义近似授权；重述需说出同一句暗号或在专用模式输入。用户今后另行录制并主动公开含暗号的新来源，属于再次披露；本轮不声称能从所有未来资料自动找回已哈希暗号。

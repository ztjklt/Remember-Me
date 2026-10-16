# iOS 记忆花园：事件时间线、图谱与手动编辑

2026-10-16。依据本人在本聊天的[产品修订](../architecture/garden-event-story-display-2026-10-16.md)。本轮为本地 iOS 源码和模拟器验证；未安装到实体手机，未发布 Backend，未触碰本人原始录音。

## 实现

- 主用户的有效 AI 故事和 EVENT 自动展示，不需要先确认；偏好、姓名等碎片不单独成为花园条目。pending 展示不等于确认人物模型或开启资料共享。
- 图谱并入时间线，事件旁显示有关联证据的人物／事件分支。右侧复用已有十种花园素材图，保持原图比例，大字号仍保留插图。
- 详情直接提供相关原音、原文依据、手动编辑和删除。标题／正文可以手动修改，保留录音和原文。已有故事按 revision 更新，EVENT 的展示编辑复用 story 创建接口。
- 删除已整理故事复用 reject；EVENT 复用已有 Memory 删除。本人已明确选择保留原音。拒绝记录防止同一事件从回退入口重新出现；读取失败不跳过故事状态校验。
- 编辑／删除保存打开时的空间和版本，拒绝过期数据与跨空间操作；保留现有本机移出／恢复，并继承旧 episode 隐藏和 EVENT 转故事的隐藏选择。

## 验证

- MemoryGardenTests：28 项通过。包括 pending 自动展示、逐事件投影、证据关联、碎片过滤、拒绝后不重现、来源变化、空间隔离和读取失败。
- PersonReviewTests：26 项通过。包括故事编辑／创建、准确 revision、拒绝旧数据、删除保留来源、失败不重放和取消操作。
- GuestAccessTests：10 项通过。游客独立身份、只读范围、撤销与返回主用户校验保留。
- SimpleFlowUITests：6 项通过。合并时间线／图谱、关系到来源、手动编辑并保存、删除／取消、本机移出／恢复及大字号。

总计 70 项。界面测试使用隔离的虚构素材和 URLProtocol 模拟服务；它们不替代真实服务、真人原音播放或实体设备体验。十种素材图片的资源存在性由单元测试检查；截图另作视觉核对。

全部测试结束后，Xcode 的可选 simctl 诊断收集长时间未结束；仅停止该诊断子进程，xcodebuild 最终退出 0 并报告 `TEST SUCCEEDED`，xcresult 附件已成功导出。

最初禁用签名的模拟器运行因已有火山 RTC 动态库未签名而无法启动测试。随后启用模拟器 ad-hoc 签名，重新构建并完成上述测试；未修改供应商库或移除功能来跳过问题。

命令与证据：

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,id=10BAAA0D-3912-4F01-9CD6-92897F1A1695' \
  -derivedDataPath build/ios-garden-events-20261016 \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM= \
  -parallel-testing-enabled NO \
  -only-testing:RememberMeTests/MemoryGardenTests \
  -only-testing:RememberMeTests/PersonReviewTests \
  -only-testing:RememberMeTests/GuestAccessTests \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenRemovalCanCancelAndRestoreWithoutDeletingMemory \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenTimelineDatesAndGraphSourcesStayInteractive \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenStoryOffersDirectDeletionAndCancelKeepsStory \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenCombinesTimelineAndRelationshipsWithoutModeSwitch \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenStoryCanEditTitleAndTextWithoutChangingOriginal \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenLargeTextKeepsStoryAndControlsReachable \
  -resultBundlePath build/garden-events-20261016/signed-verification.xcresult test
```

日志：`build/garden-events-20261016/signed-xcodebuild.log`。源码工作区原有多项未提交修改，本轮未重置或批量提交它们。共享 API/schema/数据库未变更。

## 最终预览

通过截图核对了事件时间线、同页关系分支、右侧素材比例和编辑表单。随后仅将旧预览中的独立人物样例改为散步事件，增量模拟器构建通过，并更新截图；该样例文字调整未重复运行测试。

- [记忆花园预览](../../output/previews/garden-20261016/记忆花园.png)
- [手动编辑预览](../../output/previews/garden-20261016/手动编辑.png)

预览均使用示例资料。真实账号的资料与原音未用于测试或截图。

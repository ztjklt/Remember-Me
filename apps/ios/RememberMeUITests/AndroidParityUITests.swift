import XCTest

@MainActor
final class SimpleFlowUITests: XCTestCase {
    func testRecordingActivityStyleMatchesSharedFlowerAndColorsInLightAndDark() {
        continueAfterFailure = false
        for style in ["Light", "Dark"] {
            let app = XCUIApplication()
            app.launchArguments = ["--uitest-offline", "--uitest-recording-activity-style", "-AppleInterfaceStyle", style]
            if style == "Dark" { app.launchArguments += ["--uitest-activity-dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
            app.launch()
            XCTAssertTrue(app.staticTexts["activity.style.preview"].waitForExistence(timeout: 10))
            capture(app, "录音实时活动共享样式 " + style)
            app.swipeUp()
            XCTAssertTrue(app.staticTexts["状态过期"].exists)
            capture(app, "灵动岛与过期状态共享样式 " + style)
            app.terminate()
        }
    }

    func testSystemLiveActivityStartsAndEndsWithExplicitFixtureWithoutMicrophone() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-live-activity"]
        app.launch()
        let status = app.staticTexts["activity.preview.status"]
        XCTAssertTrue(status.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertEqual(status.label, "系统实时活动已创建")
        app.buttons["activity.preview.end"].tap()
        XCTAssertEqual(status.label, "已结束")
        capture(app, "实时活动结束后的应用界面")

    }

    func testRecordingHomePlacesBluetoothBesideMyRecordingsAndShowsRealDeviceStatus() {
        continueAfterFailure = false
        let app = launch()
        let recordings = app.buttons["flow.myRecordings"]
        let devices = app.buttons["flow.devices"]
        XCTAssertTrue(recordings.waitForExistence(timeout: 5))
        XCTAssertTrue(devices.waitForExistence(timeout: 5))
        XCTAssertTrue(recordings.isHittable); XCTAssertTrue(devices.isHittable)
        XCTAssertEqual(recordings.frame.minY, devices.frame.minY, accuracy: 1)
        XCTAssertEqual(recordings.frame.width, devices.frame.width, accuracy: 1)
        XCTAssertLessThanOrEqual(recordings.frame.maxX, devices.frame.minX)
        capture(app, "录音首页并排的我的录音与蓝牙连接")
        devices.tap()
        XCTAssertTrue(app.navigationBars["蓝牙连接"].waitForExistence(timeout: 5))
        let bean = app.descendants(matching: .any).matching(identifier: "devices.bean.status").firstMatch
        let headphones = app.descendants(matching: .any).matching(identifier: "devices.headphones.status").firstMatch
        XCTAssertTrue(bean.waitForExistence(timeout: 5)); XCTAssertTrue(headphones.exists)
        XCTAssertTrue(bean.label.contains("录音豆")); XCTAssertTrue(bean.label.contains("未连接"))
        XCTAssertTrue(headphones.label.contains("耳机")); XCTAssertTrue(headphones.label.contains("未使用"))
        capture(app, "蓝牙连接中的白底设备展示与状态")
        let scan = app.buttons["devices.scan"]
        if !scan.isHittable { app.swipeUp() }
        XCTAssertTrue(scan.exists)
        scan.tap()
        XCTAssertTrue(app.staticTexts["先登录你的记忆空间，再连接录音豆。"].waitForExistence(timeout: 3))
        capture(app, "设备连接入口与真实未连接状态")
    }

    func testRecordingLeftSwipeCancelAndDeleteKeepOtherRecording() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-recording-delete"]
        app.launch()
        app.buttons["flow.myRecordings"].tap()
        let chosen = app.buttons["recordings.local.00000000-0000-0000-0000-000000000001"]
        let kept = app.buttons["recordings.local.00000000-0000-0000-0000-000000000002"]
        XCTAssertTrue(chosen.waitForExistence(timeout: 5)); XCTAssertTrue(kept.exists)
        chosen.swipeLeft()
        XCTAssertFalse(app.alerts.firstMatch.exists)
        app.buttons["删除"].firstMatch.tap()
        XCTAssertTrue(app.alerts["删除这段录音？"].waitForExistence(timeout: 3))
        capture(app, "左滑露出删除按钮后的确认")
        app.alerts.buttons["取消"].tap()
        XCTAssertTrue(chosen.exists); XCTAssertTrue(kept.exists)
        chosen.swipeLeft(); app.buttons["删除"].firstMatch.tap()
        app.alerts.buttons["删除"].tap()
        XCTAssertTrue(chosen.waitForNonExistence(timeout: 5)); XCTAssertTrue(kept.exists)
        app.navigationBars.buttons.firstMatch.tap()
        app.buttons["flow.myRecordings"].tap()
        XCTAssertFalse(chosen.exists); XCTAssertTrue(kept.waitForExistence(timeout: 5))
    }

    func testMyRecordingsOpensPreviousTwinConversations() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-conversation", "--uitest-chat-history-memory"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["录音"].waitForExistence(timeout: 10))
        app.tabBars.buttons["录音"].tap()
        let recordings = app.buttons["flow.myRecordings"]
        XCTAssertTrue(recordings.waitForExistence(timeout: 5))
        recordings.tap()
        XCTAssertTrue(app.navigationBars["我的录音"].waitForExistence(timeout: 5))
        let savedText = app.buttons["recordings.remote.archive-saved-text"]
        XCTAssertTrue(savedText.waitForExistence(timeout: 5))
        if !savedText.isHittable { app.swipeUp() }
        savedText.tap()
        XCTAssertTrue(app.navigationBars["原话详情"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["这是一段另外保存的本人文字原话。"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["播放原音"].exists)
        XCTAssertFalse(app.buttons["暂停原音"].exists)
        XCTAssertFalse(app.sliders["原音播放进度"].exists)
        capture(app, "保存的文字原话没有原音播放器")
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.navigationBars["我的录音"].waitForExistence(timeout: 5))
        let conversation = app.buttons["recordings.conversation.old-source"]
        if !conversation.isHittable { app.swipeUp() }
        XCTAssertTrue(conversation.waitForExistence(timeout: 5)); XCTAssertTrue(conversation.isHittable)
        capture(app, "我的录音列表中的 TwinAgent 历史对话")
        conversation.tap()
        XCTAssertTrue(app.navigationBars["TwinAgent 对话"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["我喜欢橙色书签，但还没有决定去哪。"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["当时的回复已失效，不再参与记忆。"].exists)
        capture(app, "从我的录音查看以前与 TwinAgent 的对话")
    }

    func testDefaultVoiceCanStartBeforeCloneAfterPurposeConfirmation() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-enrollment", "--uitest-default-voice"]
        app.launch()
        XCTAssertTrue(app.staticTexts["当前通话声音：默认声音"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.switches["voiceCall.consent"].exists)
        XCTAssertTrue(app.staticTexts["voiceCall.startNotice"].exists)
        XCTAssertTrue(app.buttons["voiceCall.start"].isEnabled)
        XCTAssertFalse(app.buttons["voiceCall.preview"].exists)
        capture(app, "默认声音无需等待克隆即可开始")
    }
    func testDefaultVoiceKeepsStartReachableWhileScrollingAndEnrollmentOptional() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-enrollment", "--uitest-default-voice"]
        app.launch()
        let start = app.buttons["voiceCall.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 10))
        XCTAssertTrue(start.isHittable)
        app.swipeUp()
        XCTAssertTrue(start.isHittable)
        XCTAssertFalse(app.buttons["voiceCall.recordSample"].exists)
        app.buttons["voiceCall.enrollmentDetails"].tap()
        XCTAssertTrue(app.buttons["voiceCall.recordSample"].waitForExistence(timeout: 5))
        XCTAssertTrue(start.isHittable)
        capture(app, "固定通话按钮与可展开的本人音色设置")
    }
    func testDefaultVoiceLargeTextKeepsActionAndConsentReachable() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-enrollment", "--uitest-default-voice",
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        let start = app.buttons["voiceCall.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 10))
        XCTAssertTrue(start.isHittable)
        XCTAssertFalse(app.switches["voiceCall.consent"].exists)
        XCTAssertTrue(start.isEnabled)
        app.swipeUp()
        XCTAssertTrue(start.isHittable)
        capture(app, "大字号直接开始通话")
    }
    func testReadyVoiceShowsPreviewAndExplainsCallConsentGate() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-enrollment", "--uitest-voice-ready"]
        app.launch()
        XCTAssertTrue(app.staticTexts["本人音色待试听确认"].waitForExistence(timeout: 10))
        app.swipeUp()
        XCTAssertTrue(app.buttons["voiceCall.preview"].exists)
        XCTAssertTrue(app.buttons["voiceCall.acceptVoice"].exists)
        XCTAssertFalse(app.buttons["voiceCall.acceptVoice"].isEnabled)
        XCTAssertTrue(app.buttons["voiceCall.retryVoice"].exists)
        XCTAssertTrue(app.staticTexts["voiceCall.selectedVoice"].label.contains("默认声音"))
        XCTAssertFalse(app.buttons["voiceCall.cloudConsent"].exists)
        XCTAssertTrue(app.buttons["voiceCall.start"].isEnabled)
        XCTAssertTrue(app.staticTexts["voiceCall.startNotice"].exists)
        capture(app, "音色就绪与合成试听入口")
    }
    func testLegacyVoiceSampleOffersRerecordingWithoutMandatoryTyping() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-enrollment"]
        app.launch()
        XCTAssertTrue(app.staticTexts["等待提交声音样本"].waitForExistence(timeout: 10))
        app.swipeUp()
        XCTAssertTrue(app.staticTexts["voiceCall.samplePending"].waitForExistence(timeout: 10))
        app.swipeUp()
        XCTAssertTrue(app.staticTexts["voiceCall.rerecordHint"].exists)
        XCTAssertFalse(app.textViews["voiceCall.sampleTranscript"].exists)
        XCTAssertFalse(app.buttons["voiceCall.enroll"].isEnabled)
        app.swipeUp()
        XCTAssertTrue(app.buttons["voiceCall.start"].isEnabled)
        XCTAssertTrue(app.staticTexts["voiceCall.startNotice"].exists)
        capture(app, "旧样本可重新朗读，无需手打")
    }
    func testEmptyGardenDoesNotInventStories() {
        let app=launch();app.tabBars.buttons["记忆"].tap()
        XCTAssertTrue(app.staticTexts["这里还没有可展示的记录"].waitForExistence(timeout:5))
        XCTAssertFalse(app.buttons["garden.entry.story-a"].exists)
        capture(app,"空花园与来源说明")
    }
    func testGardenRemovalCanCancelAndRestoreWithoutDeletingMemory() {
        continueAfterFailure=false
        let app=XCUIApplication();app.launchArguments=["--uitest-offline","--uitest-memory-garden"];app.launch()
        let flower=app.buttons["garden.entry.story-a"]
        XCTAssertTrue(flower.waitForExistence(timeout:10));capture(app,"记忆花园虚构样例")
        flower.tap();XCTAssertTrue(app.staticTexts["当时我们一起去种树，后来每次回校都会去看看。"].waitForExistence(timeout:5))
        app.buttons["garden.remove"].tap();app.buttons["取消"].tap()
        XCTAssertTrue(app.buttons["garden.remove"].exists)
        app.buttons["garden.remove"].tap();app.buttons["移出展示"].tap()
        XCTAssertTrue(app.buttons["garden.removed"].waitForExistence(timeout:5))
        XCTAssertFalse(app.buttons["garden.entry.story-a"].exists)
        app.buttons["garden.removed"].tap();app.buttons["garden.restore.story-a"].tap();app.buttons["完成"].tap()
        XCTAssertTrue(app.buttons["garden.entry.story-a"].waitForExistence(timeout:5))
        let person = app.buttons["garden.entry.person-a"]
        for _ in 0..<4 where !person.isHittable { app.swipeUp() }
        XCTAssertTrue(person.exists);capture(app,"时间线中的人物记录")
        for _ in 0..<5 where !app.buttons["garden.link.fixture-tree.story-a"].isHittable { app.swipeDown() }
        XCTAssertTrue(app.buttons["garden.link.fixture-tree.story-a"].exists)
        XCTAssertFalse(app.segmentedControls.buttons["图谱"].exists)
        capture(app, "时间线中的图谱关系与原文依据")
    }
    func testGardenStoryOffersDirectDeletionAndCancelKeepsStory() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-memory-garden"]
        app.launch()
        let flower = app.buttons["garden.entry.story-a"]
        XCTAssertTrue(flower.waitForExistence(timeout: 10))
        flower.tap()
        let delete = app.buttons["garden.delete"]
        for _ in 0..<4 where !delete.isHittable { app.swipeUp() }
        XCTAssertTrue(delete.isHittable)
        delete.tap()
        XCTAssertTrue(app.alerts["删除这篇故事？"].waitForExistence(timeout: 3))
        app.alerts.buttons["取消"].tap()
        XCTAssertTrue(delete.exists)
        delete.tap()
        app.alerts.buttons["删除故事"].tap()
        XCTAssertTrue(app.buttons["garden.removed"].waitForExistence(timeout: 5))
        XCTAssertFalse(flower.exists)
        // This fixture exercises the native controls only; HTTP deletion is unit tested.
        capture(app, "直接删除整理故事后的花园")
    }
    func testGardenTimelineDatesAndGraphSourcesStayInteractive() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-memory-garden"]
        app.launch()
        XCTAssertTrue(app.staticTexts["录入 · 2026.10.14"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["虚构界面样例，无网络或真实授权"].exists)
        XCTAssertFalse(app.staticTexts["虚构样例"].exists)
        XCTAssertTrue(app.buttons["garden.entry.story-a"].isHittable)
        XCTAssertFalse(app.textFields["查找记忆"].exists)
        capture(app, "花环与图谱时间线")
        app.buttons["garden.link.fixture-tree.story-a"].tap()
        XCTAssertTrue(app.navigationBars["记忆联系"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["大学时一起种树"].exists)
        app.buttons["关闭"].tap()
        XCTAssertFalse(app.segmentedControls.buttons["图谱"].exists)
        app.buttons["garden.link.fixture-tree.story-a"].tap()
        XCTAssertTrue(app.navigationBars["记忆联系"].waitForExistence(timeout: 5))
        capture(app, "枝状图谱与真实来源")
        app.buttons["garden.source.story-a"].tap()
        XCTAssertTrue(app.buttons["memory.details"].waitForExistence(timeout: 5))
    }
    func testGardenCombinesTimelineAndRelationshipsWithoutModeSwitch() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-memory-garden"]
        app.launch()
        XCTAssertTrue(app.buttons["garden.entry.story-a"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["garden.entry.story-a"].isHittable)
        XCTAssertTrue(app.buttons["garden.link.fixture-tree.story-a"].exists)
        XCTAssertFalse(app.segmentedControls.buttons["时间线"].exists)
        XCTAssertFalse(app.segmentedControls.buttons["图谱"].exists)
        capture(app, "右侧素材图与时间线图谱合并")
    }
    func testGardenStoryCanEditTitleAndTextWithoutChangingOriginal() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-memory-garden"]
        app.launch(); app.buttons["garden.entry.story-a"].tap()
        let edit = app.buttons["garden.edit"]
        for _ in 0..<4 where !edit.isHittable { app.swipeUp() }
        edit.tap()
        let title = app.descendants(matching: .any)["garden.editor.title"]
        XCTAssertTrue(title.waitForExistence(timeout: 5)); title.tap(); title.typeText("手动补充")
        let text = app.textViews["garden.editor.text"]
        text.tap(); text.typeText("这是我想补充的记忆。")
        capture(app, "手动编辑标题和正文")
        app.buttons["garden.editor.save"].tap()
        XCTAssertTrue(app.buttons["garden.entry.story-a"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "手动补充")).firstMatch.exists)
        app.buttons["garden.entry.story-a"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "这是我想补充的记忆")).firstMatch.exists)
        let original = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "当时我们一起去种树，后来每次回校都会去看看。")).firstMatch
        for _ in 0..<3 where !original.isHittable { app.swipeUp() }
        XCTAssertTrue(original.exists)
    }
    func testGardenLargeTextKeepsStoryAndControlsReachable() {
        continueAfterFailure=false
        let app=XCUIApplication()
        app.launchArguments=["--uitest-offline","--uitest-memory-garden","-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.buttons["garden.removed"].waitForExistence(timeout:10))
        let story=app.buttons["garden.entry.story-a"]
        if !story.isHittable { app.swipeUp() }
        XCTAssertTrue(story.waitForExistence(timeout:5));capture(app,"大字号花园")
        story.tap();XCTAssertTrue(app.staticTexts["那年在大学种下的一棵树"].waitForExistence(timeout:5))
    }
    func testVoiceCallShowsRouteForegroundNoticeAndHangup() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-call"]
        app.launch()
        let output = app.descendants(matching: .any)["voiceCall.outputPicker"]
        XCTAssertTrue(app.staticTexts["手机扬声器（测试）"].waitForExistence(timeout: 10))
        app.swipeUp()
        XCTAssertTrue(app.staticTexts["手机扬声器（测试）"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["可直接用手机扬声器和麦克风通话，无需连接蓝牙。锁屏或切到后台时会结束。"].exists)
        XCTAssertTrue(output.exists, app.debugDescription)
        XCTAssertTrue(app.buttons["voiceCall.mute"].exists)
        capture(app, "前台语音路线与控制")
        app.buttons["voiceCall.end"].tap()
        XCTAssertTrue(app.staticTexts["准备语音通话"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["voiceCall.end"].exists)
    }
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["录音"].waitForExistence(timeout: 10))
        return app
    }
    private func capture(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }
    func testHistoricalChatMemoryShowsSummarySourcesAndCancelableClear() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-conversation", "--uitest-chat-history-memory"]
        app.launch(); app.tabBars.buttons["孪生"].tap()
        let shortcut = app.buttons["twin.historyMemoryShortcut"]
        XCTAssertTrue(shortcut.waitForExistence(timeout: 5))
        XCTAssertTrue(shortcut.isHittable)
        capture(app, "孪生聊天主页面与记忆快捷入口")
        shortcut.tap()
        XCTAssertTrue(app.staticTexts["可检索 82 段聊天"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.switches["参考旧聊天"].exists)
        XCTAssertTrue(app.staticTexts["你：我喜欢橙色书签，但还没有决定去哪。"].exists)
        XCTAssertTrue(app.staticTexts["当时的孪生回复已失效，不再参与记忆。"].exists)
        capture(app, "旧聊天摘要与原消息")
        app.buttons["清除以前的聊天记忆"].tap()
        XCTAssertTrue(app.buttons["清除聊天记忆"].waitForExistence(timeout: 5))
        app.buttons["取消"].tap()
        XCTAssertTrue(app.staticTexts["可检索 82 段聊天"].exists)
    }
    func testFourChineseTabsKeepCoreFlowAndHideUnfinishedEntries() {
        let app = launch()
        XCTAssertEqual(app.tabBars.buttons.count, 4)
        XCTAssertTrue(app.buttons["flow.record"].exists)
        XCTAssertFalse(app.tabBars.buttons["Graphs"].exists)
        XCTAssertFalse(app.tabBars.buttons["Agents"].exists)
        capture(app, "录音")
        app.tabBars.buttons["记忆"].tap()
        XCTAssertTrue(app.staticTexts["这里还没有可展示的记录"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["刷新记忆"].exists)
        capture(app, "记忆")
        app.tabBars.buttons["孪生"].tap()
        XCTAssertTrue(app.staticTexts["和另一个自己聊聊"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.textFields["twin.input"].exists)
        XCTAssertTrue(app.buttons["twin.plus"].exists)
        XCTAssertTrue(app.buttons["service.connect"].exists)
        XCTAssertFalse(app.buttons["用我的声音朗读"].exists)
        XCTAssertFalse(app.buttons["用这条回答做一次校准"].exists)
        XCTAssertFalse(app.staticTexts["只在本机的个人声音"].exists)
        capture(app, "孪生")
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.buttons["flow.connection"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["个人声音与独立授权"].exists)
        capture(app, "我的")
    }
    func testRecordingArchiveAndGardenHaveSeparateDirectEntrances() {
        let app = launch()
        XCTAssertFalse(app.staticTexts["还没有录音"].exists)
        XCTAssertFalse(app.staticTexts["原音已保存在手机，可以继续转写。"].exists)
        app.buttons["flow.myRecordings"].tap()
        XCTAssertTrue(app.navigationBars["我的录音"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["还没有录音"].exists)
        app.tabBars.buttons["记忆"].tap()
        XCTAssertTrue(app.navigationBars["记忆花园"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["garden.open"].exists)
        XCTAssertFalse(app.textFields["flow.memorySearchQuery"].exists)
        XCTAssertFalse(app.buttons["flow.memorySearch"].exists)
        XCTAssertFalse(app.textFields["garden.search"].exists)
        XCTAssertTrue(app.segmentedControls.buttons["人物与关系"].exists)
        app.segmentedControls.buttons["记忆图谱"].tap()
        XCTAssertTrue(app.staticTexts["garden.graph.empty"].waitForExistence(timeout: 5))
        capture(app, "记忆入口直接展示花园")
    }
    func testKeyboardCanDismissAndTabSwitchPreservesDraftWithoutReopening() {
        let app = launch()
        app.tabBars.buttons["孪生"].tap()
        let input = app.textFields["twin.input"]
        input.tap(); input.typeText("draft")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        app.buttons["keyboard.dismiss"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
        XCTAssertEqual(input.value as? String, "draft")
        input.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        app.buttons["twin.plus"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
        app.buttons["关闭"].tap()
        app.tabBars.buttons["录音"].tap()
        app.tabBars.buttons["孪生"].tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists)
        XCTAssertEqual(input.value as? String, "draft")
        input.tap()
        app.staticTexts["和另一个自己聊聊"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
        capture(app, "键盘可收起，草稿保留")
    }
    func testGuidedVoiceSampleCanConfirmWithoutTypingAndEditingResetsConfirmation() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-enrollment", "--uitest-guided-voice-sample"]
        app.launch()
        XCTAssertTrue(app.buttons["voiceCall.start"].waitForExistence(timeout: 10))
        for _ in 0..<5 {
            if app.switches["voiceCall.confirmSample"].isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(app.staticTexts["voiceCall.readingPrompt"].exists)
        XCTAssertFalse(app.textViews["voiceCall.sampleTranscript"].exists)
        XCTAssertFalse(app.buttons["voiceCall.enroll"].isEnabled)
        app.switches["voiceCall.confirmSample"].tap()
        XCTAssertTrue(app.buttons["voiceCall.enroll"].isEnabled)
        capture(app, "照读后直接确认，无需打字")
        app.buttons["读错了？修改文字或重新朗读"].tap()
        let editor = app.textViews["voiceCall.sampleTranscript"]
        if !editor.isHittable { app.swipeUp() }
        editor.tap(); editor.typeText("changed")
        XCTAssertFalse(app.buttons["voiceCall.enroll"].isEnabled)
        app.buttons["keyboard.dismiss"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
        XCTAssertEqual(app.switches["voiceCall.confirmSample"].value as? String, "0")
    }
    func testTwinShowsReviewedWordingAndReachableFeedbackInSimpleRoute() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-feedback"]
        app.launch(); app.tabBars.buttons["孪生"].tap()
        XCTAssertEqual(app.staticTexts["twin.answerMessage"].label, "根据记录，他会先看看情况，再做选择。")
        XCTAssertTrue(app.staticTexts["twin.expression"].exists)
        XCTAssertFalse(app.buttons["twin.feedback"].exists)
        capture(app, "左右消息与输入栏")
        app.buttons["twin.plus"].tap()
        XCTAssertTrue(app.buttons["语音提问"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["twin.review"].exists)
        XCTAssertTrue(app.buttons["twin.feedback"].exists)
        // No connection in this fixture: a displayed answer must not authorize feedback.
        XCTAssertFalse(app.buttons["twin.feedback"].isEnabled)
        capture(app, "表达与本人反馈入口")
    }
    func testCompletedFeedbackShowsDifferenceAndHumanReviewNextStep() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-feedback", "--uitest-twin-complete"]
        app.launch(); app.tabBars.buttons["孪生"].tap()
        app.buttons["twin.plus"].tap()
        app.buttons["twin.comparison"].tap()
        XCTAssertTrue(app.staticTexts["真人回答补充了时间紧时先行动的条件。"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["twin.reviewFeedback"].exists)
        XCTAssertTrue(app.staticTexts["这是一次回答的比较，不能代表整体人格还原率。新的理解仍需要你核对确认。"].exists)
        capture(app, "比较结果与本人核对")
    }
    func testChatRetainsTurnsWithUserRightAndTwinLeftAndKeyboardComposer() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-feedback", "--uitest-twin-chat"]
        app.launch(); app.tabBars.buttons["孪生"].tap()
        let users = app.staticTexts.matching(identifier: "twin.userMessage")
        let answers = app.staticTexts.matching(identifier: "twin.answerMessage")
        XCTAssertEqual(users.count, 2); XCTAssertEqual(answers.count, 2)
        XCTAssertGreaterThan(users.element(boundBy: 0).frame.minX, answers.element(boundBy: 0).frame.minX)
        XCTAssertGreaterThan(users.element(boundBy: 0).frame.maxX, answers.element(boundBy: 0).frame.maxX)
        capture(app, "多轮消息")
        let input = app.textFields["twin.input"]
        input.tap(); input.typeText("weekend")
        XCTAssertEqual(input.value as? String, "weekend")
        XCTAssertTrue(app.buttons["twin.plus"].isHittable)
        XCTAssertTrue(app.buttons["twin.send"].isHittable)
        XCTAssertFalse(app.buttons["twin.send"].isEnabled)
        capture(app, "键盘与底部输入栏")
        app.buttons["twin.plus"].tap()
        XCTAssertTrue(app.buttons["语音提问"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["语音提问"].isEnabled)
        XCTAssertFalse(app.buttons["用我的声音朗读"].exists)
        XCTAssertFalse(app.buttons["上传图片"].exists)
        capture(app, "加号功能")
    }
    func testEarlierAnswerEvidenceAndActionsStayAttachedToThatMessage() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-feedback", "--uitest-twin-chat"]
        app.launch(); app.tabBars.buttons["孪生"].tap()
        app.buttons["twin.evidence.fixture-answer"].tap()
        XCTAssertTrue(app.navigationBars["回答依据"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["时间紧时会怎么选？"].exists)
        XCTAssertFalse(app.staticTexts["为什么会这样选？"].isHittable)
        let baseAnswer = app.descendants(matching: .any).matching(identifier: "twin.baseAnswer").firstMatch
        XCTAssertTrue(baseAnswer.exists); baseAnswer.tap()
        XCTAssertTrue(app.staticTexts["根据记录，他会结合当时情况选择。"].exists)
        capture(app, "较早回答的依据")
        app.buttons["关闭"].tap()
        app.buttons["twin.answerActions.fixture-answer"].tap()
        XCTAssertTrue(app.buttons["复制回答"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["纠正这条回答"].exists)
        XCTAssertFalse(app.buttons["纠正这条回答"].isEnabled)
        capture(app, "逐条回答操作")
    }
    func testStartingNewChatCanCancelAndDoesNotDeleteMemoryOrComparison() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-feedback", "--uitest-twin-complete"]
        app.launch(); app.tabBars.buttons["孪生"].tap()
        app.buttons["twin.plus"].tap()
        app.swipeUp()
        app.buttons["twin.newChat"].tap()
        XCTAssertTrue(app.buttons["清空当前聊天并开始"].waitForExistence(timeout: 5))
        app.buttons["取消"].tap()
        XCTAssertTrue(app.buttons["twin.comparison"].exists)
        app.buttons["twin.newChat"].tap()
        app.buttons["清空当前聊天并开始"].tap()
        XCTAssertTrue(app.staticTexts["和另一个自己聊聊"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["twin.answerMessage"].exists)
        XCTAssertTrue(app.textFields["twin.input"].exists)
        app.buttons["twin.plus"].tap()
        XCTAssertTrue(app.buttons["twin.comparison"].waitForExistence(timeout: 5))
        capture(app, "新聊天保留比较结果")
    }
    func testFailedQuestionCanBeEditedWithoutAutoSendingOrInventingAnswer() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-feedback", "--uitest-twin-failure"]
        app.launch(); app.tabBars.buttons["孪生"].tap()
        XCTAssertTrue(app.staticTexts["暂时没能回答，请稍后重试。"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["重试"].isEnabled)
        app.buttons["重新编辑问题"].tap()
        XCTAssertEqual(app.textFields["twin.input"].value as? String, "这个问题还没回答。")
        XCTAssertFalse(app.buttons["twin.send"].isEnabled)
        XCTAssertEqual(app.staticTexts.matching(identifier: "twin.answerMessage").count, 1)
        app.textFields["twin.input"].typeText("new")
        let draft = app.textFields["twin.input"].value as? String
        app.buttons["重新编辑问题"].tap()
        XCTAssertTrue(app.buttons["保留当前草稿"].waitForExistence(timeout: 5))
        app.buttons["保留当前草稿"].tap()
        XCTAssertEqual(app.textFields["twin.input"].value as? String, draft)
        capture(app, "失败与重新编辑")
    }
    func testConversationLabelsAndRememberingRequireOwnWordsAndRealConnection() {
        continueAfterFailure=false
        let app=XCUIApplication()
        app.launchArguments=["--uitest-offline","--uitest-twin-conversation"]
        app.launch();app.tabBars.buttons["孪生"].tap()
        XCTAssertEqual(app.staticTexts.matching(identifier:"twin.userMessage").count,2)
        XCTAssertTrue(app.staticTexts["另一个我 · 对话回应"].firstMatch.exists)
        capture(app,"连续聊天展示")
        app.buttons["twin.plus"].tap()
        XCTAssertFalse(app.buttons["twin.feedback"].exists)
        XCTAssertTrue(app.buttons["twin.remember"].waitForExistence(timeout:5))
        app.buttons["twin.remember"].tap()
        XCTAssertTrue(app.navigationBars["选择本人描述"].waitForExistence(timeout:5))
        app.buttons["我喜欢安静的咖啡馆。"].tap()
        XCTAssertTrue(app.navigationBars["记住这句话"].waitForExistence(timeout:5))
        XCTAssertEqual(app.staticTexts["twin.rememberText"].label,"我喜欢安静的咖啡馆。")
        XCTAssertFalse(app.buttons["twin.confirmRemember"].isEnabled)
        let toggle=app.switches["twin.rememberOwnWords"]
        XCTAssertTrue(toggle.exists)
        toggle.coordinate(withNormalizedOffset:CGVector(dx:0.95,dy:0.5)).tap()
        // Fictional state cannot authorize a cloud write, even after checking.
        XCTAssertFalse(app.buttons["twin.confirmRemember"].isEnabled)
        capture(app,"本人文字记忆确认")
    }
    func testRecordingStartsFromOneTapAndDeniedMicrophoneKeepsNoAudio() {
        let app = launch()
        app.buttons["flow.record"].tap()
        capture(app, "点击一次打开录音")
        XCTAssertTrue(app.staticTexts["recorder.error"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["recorder.error"].label.contains("麦克风权限已拒绝"))
        XCTAssertFalse(app.buttons["同意并开始录音"].exists)
        XCTAssertTrue(app.navigationBars["录音与核对"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["开始录音"].exists)
        XCTAssertFalse(app.buttons["recorder.finish"].exists)
        capture(app, "一键录音与权限拒绝")
        app.buttons["关闭"].tap()
        XCTAssertTrue(app.buttons["flow.record"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["还没有录音或保存的对话原话"].exists)
        app.buttons["flow.myRecordings"].tap()
        XCTAssertTrue(app.staticTexts["还没有录音或保存的对话原话"].waitForExistence(timeout: 5))
    }
    func testAutomaticTranscriptionSettingIsChineseAndCanBeTurnedOff() {
        let app = launch()
        app.tabBars.buttons["我的"].tap()
        let toggle = app.switches["recording.autoTranscribe"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        XCTAssertEqual(toggle.value as? String, "1")
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        XCTAssertEqual(toggle.value as? String, "0")
        app.tabBars.buttons["录音"].tap()
        XCTAssertTrue(app.buttons["flow.record"].isHittable)
        app.tabBars.buttons["我的"].tap()
        XCTAssertEqual(app.switches["recording.autoTranscribe"].value as? String, "0")
        capture(app, "自动转写可关闭")
    }
    func testChineseConnectionAndAdvancedReviewRemainReachable() {
        let app = launch()
        app.tabBars.buttons["我的"].tap()
        app.buttons["更多：核对人物理解"].tap()
        XCTAssertTrue(app.buttons["portrait.review"].waitForExistence(timeout: 5))
        app.buttons["flow.connection"].tap()
        XCTAssertTrue(app.secureTextFields["ecs.password"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.segmentedControls.buttons["云端账号"].exists)
        app.segmentedControls.buttons["本机连接"].tap()
        XCTAssertTrue(app.secureTextFields["一次性配对码"].waitForExistence(timeout: 5))
        capture(app, "本机连接")
    }
}

import XCTest

@MainActor
final class RMDesignSystemUITests: XCTestCase {
    func testTwinAudioMotionUsesActualOfflinePlaybackAndClearsLevelOnPauseAndStop() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-twin-audio-motion"]
        app.launch()
        let play = app.buttons["audioMotion.play"]
        let level = app.staticTexts["audioMotion.level"]
        let state = app.staticTexts["audioMotion.state"]
        XCTAssertTrue(play.waitForExistence(timeout: 10))
        XCTAssertEqual(state.label, "未播放")
        XCTAssertEqual(level.value as? String, "无音频")
        XCTAssertTrue(app.staticTexts["合成测试音频 · 实际音量驱动"].exists)
        play.tap()
        let measured = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value.doubleValue > 0.01"), object: level)
        XCTAssertEqual(XCTWaiter.wait(for: [measured], timeout: 5), .completed)
        XCTAssertEqual(state.label, "播放中")
        capture(app, "实际合成音频驱动孪生光环")
        play.tap()
        XCTAssertEqual(state.label, "已暂停")
        XCTAssertEqual(level.value as? String, "无音频")
        app.switches["audioMotion.gold"].tap()
        capture(app, "暂停收回音量与金色样式")
        play.tap()
        XCTAssertEqual(state.label, "播放中")
        app.buttons["audioMotion.stop"].tap()
        XCTAssertEqual(state.label, "未播放")
        XCTAssertEqual(level.value as? String, "无音频")
    }

    func testMemoryDetailsKeepOriginalSourcesAndCorrectionBehindExplicitButton() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-memory-detail"]
        app.launch()
        XCTAssertTrue(app.buttons["memory.details"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["保存纠正"].exists)
        XCTAssertFalse(app.buttons["删除这条记忆"].exists)
        capture(app, "记忆简洁概览")
        app.buttons["memory.details"].tap()
        XCTAssertTrue(app.navigationBars["记忆详情"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["来源与处理详情"].exists)
        for _ in 0..<3 where !app.buttons["保存纠正"].isHittable { app.swipeUp() }
        XCTAssertTrue(app.buttons["保存纠正"].exists)
        XCTAssertFalse(app.buttons["保存纠正"].isEnabled)
        capture(app, "原文来源与纠正")
        app.buttons["关闭"].tap()
        XCTAssertTrue(app.buttons["memory.details"].waitForExistence(timeout: 5))
    }
    func testShowcaseExposesStatePickerAndRealReusableControls() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-design-system"]
        app.launch()
        XCTAssertTrue(app.navigationBars["RM 组件"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["design.flowerState"].exists)
        capture(app, "勿忘我矢量与状态")
        app.buttons["design.flowerState"].tap()
        app.buttons["倾听"].tap()
        XCTAssertTrue(app.buttons["design.flowerState"].exists)
        for _ in 0..<5 where !app.buttons["正在保存"].isHittable { app.swipeUp() }
        XCTAssertTrue(app.buttons["正在保存"].exists)
        XCTAssertFalse(app.buttons["正在保存"].isEnabled)
        XCTAssertFalse(app.buttons["暂不可用"].isEnabled)
        capture(app, "组件加载与禁用状态")
    }
    func testLargeTypeKeepsRecordingAndChatComposerReachable() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.buttons["flow.record"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["flow.record"].isHittable)
        capture(app, "大字号录音首页")
        app.tabBars.buttons["孪生"].tap()
        XCTAssertTrue(app.textFields["twin.input"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["twin.plus"].isHittable)
        XCTAssertTrue(app.textFields["twin.input"].isHittable)
        capture(app, "大字号孪生与输入栏")
    }
    func testCallDetailsAreOptionalAndHangupRemainsReachable() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-call", "--uitest-identified-speaker"]
        app.launch()
        XCTAssertTrue(app.buttons["voiceCall.end"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["voiceCall.end"].isHittable)
        XCTAssertFalse(app.staticTexts["voiceCall.answer"].exists)
        XCTAssertEqual(app.staticTexts["voiceCall.speakerIdentity"].label, "声纹匹配：小王")
        capture(app, "简洁通话与声纹姓名")
        app.buttons["voiceCall.conversationDetails"].tap()
        XCTAssertTrue(app.navigationBars["本轮对话"].waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(app.staticTexts["voiceCall.speakerIdentity"].exists)
        capture(app, "通话对话详情与结束入口")
        XCTAssertTrue(app.staticTexts["通话声音由服务提供"].exists)
        XCTAssertFalse(app.staticTexts["voiceCall.answer"].exists)
        XCTAssertTrue(app.buttons["voiceCall.details.end"].isHittable)
        app.buttons["voiceCall.details.end"].tap()
        XCTAssertTrue(app.staticTexts["准备语音通话"].waitForExistence(timeout: 5))
    }
    func testUnidentifiedSpeakerDoesNotShowAMatchedNameAtLargeType() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-voice-call", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.staticTexts["voiceCall.speakerIdentity"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["voiceCall.speakerIdentity"].label, "暂未确认说话人")
        XCTAssertTrue(app.buttons["voiceCall.end"].isHittable)
        capture(app, "大字号未识别说话人")
        app.swipeUp()
        XCTAssertTrue(app.staticTexts["手机扬声器（测试）"].isHittable)
        XCTAssertTrue(app.descendants(matching: .any)["voiceCall.outputPicker"].exists, app.debugDescription)
        XCTAssertTrue(app.buttons["voiceCall.end"].isHittable)
        capture(app, "大字号手机扬声器路线")
    }
    private func capture(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }
}

import XCTest

@MainActor
final class SpeakerRecordingUITests: XCTestCase {
    func testGroupEntranceDoesNotAddListsOrExtraButtonsToRecordingHome() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--uitest-offline"]; app.launch()
        XCTAssertFalse(app.buttons["speaker.open"].exists)
        app.buttons["flow.myRecordings"].tap()
        app.buttons["speaker.open"].tap()
        XCTAssertTrue(app.staticTexts["speaker.introduction"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.segmentedControls["speaker.count"].exists)
        XCTAssertFalse(app.switches["speaker.participantConsent"].exists)
        XCTAssertTrue(app.staticTexts["speaker.startNotice"].exists)
        XCTAssertEqual(app.textFields.count, 0)
        XCTAssertFalse(app.buttons["speaker.start"].isEnabled)
        app.buttons["关闭"].tap()
        XCTAssertTrue(app.navigationBars["我的录音"].waitForExistence(timeout: 5))
    }
    func testAutomaticallyNamedSpeakersAndUnknownSegmentsDoNotAskForManualIdentity() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--uitest-offline", "--uitest-speaker-recording"]; app.launch()
        XCTAssertTrue(app.staticTexts["本段说话人"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["说话人 1 · 小王"].exists)
        XCTAssertTrue(app.staticTexts["说话人 2 · 小李"].exists)
        XCTAssertTrue(app.staticTexts["那天我们一起去种树。"].exists)
        app.swipeUp()
        XCTAssertTrue(app.staticTexts["声音重叠，未识别"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.textFields.count, 0); XCTAssertEqual(app.textViews.count, 0)
        let screenshot = XCTAttachment(screenshot: app.screenshot()); screenshot.name = "自动关联自我介绍与后续发言（虚构样例）"; screenshot.lifetime = .keepAlways; add(screenshot)
        app.buttons["删除这段多人录音"].tap(); app.buttons["取消"].tap()
        XCTAssertTrue(app.staticTexts["本段说话人"].exists)
    }
}

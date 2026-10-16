import XCTest

@MainActor
final class CaptureWorkflowUITests: XCTestCase {
    private let machine = "虚构示例：我心清很好。"
    private let corrected = "虚构示例：我心情很好。"

    private func launch(largeText: Bool = false) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-capture-draft"]
        if largeText {
            app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        }
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["录音"].waitForExistence(timeout: 10))
        return app
    }

    private func reveal(_ element: XCUIElement, app: XCUIApplication, scrollingDown: Bool = true,
                        file: StaticString = #filePath, line: UInt = #line) {
        for _ in 0..<10 where !element.isHittable {
            if scrollingDown { app.swipeUp() } else { app.swipeDown() }
        }
        XCTAssertTrue(element.isHittable, app.debugDescription, file: file, line: line)
    }

    private func dismissKeyboard(_ app: XCUIApplication) {
        let dismiss = app.buttons["keyboard.dismiss"]
        XCTAssertTrue(dismiss.waitForExistence(timeout: 3))
        dismiss.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
    }

    private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name + " · 隔离虚构资料"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testCorrectedDraftMachineComparisonAndSupplementSurviveNavigation() {
        let app = launch()
        let text = app.textViews["capture.draft.text"]
        reveal(text, app: app)
        XCTAssertEqual(text.value as? String, corrected)
        XCTAssertEqual(app.staticTexts["capture.correction.summary"].label, "已自动校对 1 处")
        capture(app, "自动校对稿与核对入口")

        text.tap(); text.typeText(" edited")
        XCTAssertTrue((text.value as? String)?.contains("edited") == true)
        dismissKeyboard(app)
        let supplement = app.textViews["capture.draft.supplement"]
        reveal(supplement, app: app)
        supplement.tap(); supplement.typeText("A private draft supplement.")
        dismissKeyboard(app)
        XCTAssertEqual(supplement.value as? String, "A private draft supplement.")

        let original = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "机器原始转写")).firstMatch
        reveal(original, app: app, scrollingDown: false)
        original.tap()
        let restoreMachine = app.buttons["capture.restore.machine"]
        reveal(restoreMachine, app: app)
        restoreMachine.tap()
        XCTAssertEqual(text.value as? String, machine)
        let restoreCorrected = app.buttons["capture.restore.corrected"]
        reveal(restoreCorrected, app: app)
        restoreCorrected.tap()
        XCTAssertEqual(text.value as? String, corrected)
        XCTAssertEqual(supplement.value as? String, "A private draft supplement.")

        reveal(text, app: app)
        text.tap(); text.typeText(" retained")
        let retained = text.value as? String
        XCTAssertTrue(retained?.contains("retained") == true)
        dismissKeyboard(app)
        capture(app, "本人改稿与独立补充")
        let recordings = app.buttons["flow.myRecordings"]
        reveal(recordings, app: app, scrollingDown: false)
        recordings.tap()
        XCTAssertTrue(app.navigationBars["我的录音"].waitForExistence(timeout: 5))
        app.navigationBars.buttons.firstMatch.tap()
        reveal(text, app: app)
        XCTAssertEqual(text.value as? String, retained)
        XCTAssertEqual(supplement.value as? String, "A private draft supplement.")
        let save = app.buttons["capture.draft.save"]
        reveal(save, app: app)
        XCTAssertTrue(save.isEnabled)
        // This fixture has no pairing. Unit tests cover the actual authorized PATCH.
        capture(app, "返回录音首页后草稿完整保留")
    }

    func testLargestTextKeepsDraftSupplementAndSaveReachable() {
        let app = launch(largeText: true)
        let text = app.textViews["capture.draft.text"]
        reveal(text, app: app)
        XCTAssertEqual(text.value as? String, corrected)
        text.tap(); text.typeText(" large")
        XCTAssertTrue((text.value as? String)?.contains("large") == true)
        dismissKeyboard(app)
        let supplement = app.textViews["capture.draft.supplement"]
        reveal(supplement, app: app)
        supplement.tap(); supplement.typeText("Large type supplement.")
        dismissKeyboard(app)
        XCTAssertEqual(supplement.value as? String, "Large type supplement.")
        let save = app.buttons["capture.draft.save"]
        reveal(save, app: app)
        XCTAssertTrue(save.isEnabled)
        XCTAssertGreaterThanOrEqual(save.frame.height, 44)
        capture(app, "最大字号仍可编辑与到达保存操作")
    }
}

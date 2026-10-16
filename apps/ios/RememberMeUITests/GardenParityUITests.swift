import XCTest

@MainActor
final class GardenParityUITests: XCTestCase {
    private func launch(largeText: Bool = false) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-memory-garden"]
        if largeText { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launch()
        XCTAssertTrue(app.buttons["garden.entry.story-a"].waitForExistence(timeout: 10))
        return app
    }
    private func tap(_ button: XCUIElement, app: XCUIApplication) {
        for _ in 0..<6 where !button.isHittable { app.swipeUp() }
        XCTAssertTrue(button.isHittable); button.tap()
    }
    private func select(_ mode: String, app: XCUIApplication) {
        let button = app.buttons["garden.mode." + mode]
        for _ in 0..<4 where !button.isHittable { app.scrollViews["garden.modes"].swipeLeft() }
        XCTAssertTrue(button.isHittable); button.tap()
    }
    func testFlowerOpensPetalReaderWithCompleteEvidenceAndSourceManagement() {
        let app = launch()
        tap(app.buttons["garden.entry.story-a"], app: app)
        tap(app.buttons["garden.petal.story-a"], app: app)
        XCTAssertTrue(app.scrollViews["garden.reader.document"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["它的来处"].exists)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "没有可靠时间对齐时，播放完整原音")).firstMatch.exists)
        // The fixture is explicitly a text source; it must not invent playable original audio.
        XCTAssertFalse(app.descendants(matching: .any)["garden.reader.player"].exists)
        tap(app.buttons["查看来源、纠正或删除记忆"], app: app)
        XCTAssertTrue(app.buttons["memory.details"].waitForExistence(timeout: 5))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.buttons["返回花朵"].tap()
        XCTAssertTrue(app.buttons["garden.petal.story-a"].waitForExistence(timeout: 5))
    }
    func testAllEightFacetsUseRealFixtureRecordsAndFourPersonViews() {
        let app = launch()
        select("记忆侧面", app: app)
        for facet in ["EXPERIENCE", "RELATIONSHIPS", "IDENTITY", "PRACTICES", "VALUES", "FEELINGS", "WISHES", "EXPRESSION"] {
            let button = app.buttons["garden.facet." + facet]
            for _ in 0..<6 where !button.exists { app.swipeUp() }
            XCTAssertTrue(button.exists)
        }
        for _ in 0..<6 { app.swipeDown() }
        tap(app.buttons["garden.facet.RELATIONSHIPS"], app: app)
        XCTAssertTrue(app.buttons["garden.record.fixture-person"].waitForExistence(timeout: 5))
        tap(app.buttons["garden.record.fixture-person"], app: app)
        XCTAssertTrue(app.staticTexts["一起散步的老朋友"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["我们一边散步，一边聊起大学时的经历。"].exists)
    }
    func testLargeTextCanSwitchScenesAndReadExpressionWithoutClippingControls() {
        let app = launch(largeText: true)
        tap(app.buttons["garden.changeScene"], app: app)
        tap(app.buttons["garden.scene.forest"], app: app)
        XCTAssertTrue(app.navigationBars["换一处花园"].waitForNonExistence(timeout: 5))
        XCTAssertTrue(app.buttons["garden.changeScene"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["garden.changeScene"].label.contains("林间"))
        select("了解这个人", app: app)
        tap(app.buttons["garden.person.声音表达"], app: app)
        tap(app.buttons["garden.record.fixture-expression"], app: app)
        XCTAssertTrue(app.staticTexts["关于回校的原话"].waitForExistence(timeout: 5))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Android 花园功能的 iOS 大字号界面 · 隔离虚构数据"
        attachment.lifetime = .keepAlways; add(attachment)
    }
}

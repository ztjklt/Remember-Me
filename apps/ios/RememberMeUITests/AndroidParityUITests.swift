import XCTest

@MainActor
final class AndroidParityUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Portrait"].waitForExistence(timeout: 10))
        return app
    }
    private func capture(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name
        image.lifetime = .keepAlways
        add(image)
    }
    func testPortraitSearchAndRecorderKeepNativeWorkflow() {
        let app = launch()
        XCTAssertEqual(app.tabBars.buttons.count, 5)
        capture(app, "Portrait")
        let record = app.buttons["portrait.record"]
        XCTAssertTrue(record.exists)
        record.tap()
        XCTAssertTrue(app.navigationBars["留下一段声音"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["开始录音"].exists)
        capture(app, "Recorder")
        app.buttons["关闭"].tap()
        let search = app.textFields["Search portraits"]
        search.tap()
        search.typeText("Identity")
        XCTAssertTrue(app.buttons["portrait.category.identity"].exists)
        XCTAssertFalse(app.buttons["portrait.category.thing"].exists)
        app.buttons["portrait.category.identity"].tap()
        XCTAssertTrue(app.navigationBars["Identity memory"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["还没有相关记忆"].exists)
    }
    func testFiveTabsAndExistingTwinRemainReachable() {
        let app = launch()
        app.tabBars.buttons["Graphs"].tap()
        XCTAssertTrue(app.staticTexts["Event flow"].waitForExistence(timeout: 5))
        capture(app, "Graphs")
        app.tabBars.buttons["Memories"].tap()
        XCTAssertTrue(app.staticTexts["Memory control board"].waitForExistence(timeout: 5))
        app.buttons["memories.archive"].tap()
        XCTAssertTrue(app.segmentedControls.buttons["录音"].waitForExistence(timeout: 5))
        app.segmentedControls.buttons["记忆"].tap()
        capture(app, "Memories")
        app.tabBars.buttons["Agents"].tap()
        XCTAssertTrue(app.staticTexts["Memory keeper"].waitForExistence(timeout: 5))
        app.swipeUp()
        app.buttons["agents.twin"].tap()
        XCTAssertTrue(app.staticTexts["问一个关于自己的问题。"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["service.connect"].exists)
        app.tabBars.buttons["Me"].tap()
        XCTAssertTrue(app.staticTexts["Today's data"].waitForExistence(timeout: 5))
        capture(app, "Me")
        app.buttons["连接服务"].tap()
        XCTAssertTrue(app.secureTextFields["一次性配对码"].waitForExistence(timeout: 5))
        capture(app, "Connection")
    }

    func testAllFourGraphsNavigateToTheirLiveDataViews() {
        let app = launch()
        app.tabBars.buttons["Graphs"].tap()
        for (label, title) in [("Event flow", "事件时间线"), ("Mood trends", "情绪与回忆视角"),
                               ("Decision + values", "决策与价值"), ("Expression style", "表达记录")] {
            app.buttons.containing(.staticText, identifier: label).firstMatch.tap()
            XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 5))
            app.navigationBars.buttons.firstMatch.tap()
        }
        XCTAssertFalse(app.staticTexts["设计示意 · 不是你的真实关系数据"].exists)
    }
}

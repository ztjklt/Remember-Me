import XCTest

final class GuestAccessUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-guest"]
        app.launch(); return app
    }
    func testGuestHasOnlyGardenAndTwinAndReadOnlySource() {
        let app = launch()
        XCTAssertTrue(app.staticTexts["正在访问 · 爷爷"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.tabBars.buttons.count, 2)
        XCTAssertTrue(app.tabBars.buttons["记忆花园"].exists)
        XCTAssertTrue(app.tabBars.buttons["TwinAgent"].exists)
        XCTAssertFalse(app.tabBars.buttons["录音"].exists)
        XCTAssertFalse(app.tabBars.buttons["我的"].exists)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "亲友记忆花园"; shot.lifetime = .keepAlways; add(shot)
        app.staticTexts["周末和家人在河边散步"].tap()
        XCTAssertTrue(app.staticTexts["完整核对文字"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["播放整段原音"].exists)
        XCTAssertFalse(app.buttons["删除"].exists); XCTAssertFalse(app.buttons["修改"].exists)
    }
    func testGuestTwinOmitsOwnerManagementAndRequiresPasswordToReturn() {
        let app = launch()
        app.tabBars.buttons["TwinAgent"].tap()
        XCTAssertTrue(app.staticTexts["以前周末会做什么？"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["记住这句话"].exists)
        XCTAssertFalse(app.buttons["纠正这条回答，让 Twin 更了解我"].exists)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "亲友 TwinAgent"; shot.lifetime = .keepAlways; add(shot)
        app.buttons["访问"].tap()
        app.buttons["返回主用户"].tap()
        XCTAssertTrue(app.secureTextFields["guest.ownerPassword"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["guest.returnOwner"].isEnabled)
        app.buttons["取消"].tap()
        XCTAssertEqual(app.tabBars.buttons.count, 2)
    }
}

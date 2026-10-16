import XCTest
@MainActor final class PersonalModelUITests:XCTestCase {
    func testCoverageFigureAndDomainsRemainReadableAtLargeText() {
        continueAfterFailure=false
        let app=XCUIApplication();app.launchArguments=["--uitest-offline","--uitest-personal-model","-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"];app.launch()
        XCTAssertTrue(app.navigationBars["人物模型"].waitForExistence(timeout:10))
        XCTAssertTrue(app.descendants(matching:.any)["personalModel.coverage"].waitForExistence(timeout:5))
        XCTAssertFalse(app.staticTexts["100%"].exists)
        let image=XCTAttachment(screenshot:app.screenshot());image.name="人物模型人体填色与资料覆盖";image.lifetime = .keepAlways;add(image)
        app.swipeUp();app.swipeUp()
        XCTAssertTrue(app.staticTexts["身份与角色"].exists || app.staticTexts["经历与记忆"].exists)
    }
    func testTwinHasIndependentPersonalModelButton() {
        continueAfterFailure=false
        let app=XCUIApplication();app.launchArguments=["--uitest-offline"];app.launch()
        app.tabBars.buttons["孪生"].tap()
        XCTAssertTrue(app.buttons["twin.personalModel"].waitForExistence(timeout:5))
        app.buttons["twin.personalModel"].tap()
        XCTAssertTrue(app.navigationBars["人物模型"].waitForExistence(timeout:5))
    }
}

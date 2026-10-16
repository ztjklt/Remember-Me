import XCTest

@MainActor
final class EntrustmentUITests: XCTestCase {
    func testGuidedDraftNeedsNoRecipientAccountAndRejectsSimpleSecretInLightAndDark() {
        continueAfterFailure = false
        for style in ["Light", "Dark"] {
            let app = XCUIApplication()
            app.launchArguments = ["--uitest-offline", "--uitest-entrustment", "-AppleInterfaceStyle", style]
            if style == "Dark" { app.launchArguments.append("--uitest-entrustment-dark") }
            app.launch()
            let recipient = app.textFields["例如：女儿小雨、一起长大的阿明"]
            XCTAssertTrue(recipient.waitForExistence(timeout: 10), app.debugDescription)
            XCTAssertFalse(app.textFields["亲友登录账号"].exists)
            XCTAssertFalse(app.buttons["继续"].isEnabled)
            recipient.tap(); recipient.typeText("son")
            if app.buttons["收起键盘"].exists { app.buttons["收起键盘"].tap() }
            XCTAssertTrue(app.buttons["继续"].isEnabled)
            app.buttons["继续"].tap()
            let secret = app.secureTextFields["entrustment.secret"]
            XCTAssertTrue(secret.waitForExistence(timeout: 3), app.debugDescription)
            XCTAssertTrue(app.buttons["用本机离线语音录入"].exists)
            secret.tap(); secret.typeText("banana")
            if app.buttons["收起键盘"].exists { app.buttons["收起键盘"].tap() }
            XCTAssertFalse(app.buttons["继续"].isEnabled)
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "游客暗号托付本机引导 " + style; shot.lifetime = .keepAlways; add(shot)
            app.buttons["取消"].tap()
            app.terminate()
        }
    }
}

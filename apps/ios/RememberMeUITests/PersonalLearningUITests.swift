import XCTest

@MainActor
final class PersonalLearningUITests: XCTestCase {
    private func open(_ extra: [String] = []) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-offline", "--uitest-personal-learning"] + extra
        app.launch()
        XCTAssertTrue(app.navigationBars["复刻验证"].waitForExistence(timeout: 10))
        let hierarchy = XCTAttachment(string: app.debugDescription)
        hierarchy.name = "隔离验证页面 accessibility"; hierarchy.lifetime = .keepAlways; add(hierarchy)
        return app
    }
    private func capture(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }
    func testInsufficientDataShowsNoMadeUpPersonalityPercentageOrTraining() {
        let app = open()
        XCTAssertTrue(app.staticTexts["learning.noScore"].exists)
        XCTAssertFalse(app.staticTexts["learning.score"].exists)
        XCTAssertTrue(app.staticTexts["learning.sampleCounts"].exists)
        capture(app, "复刻验证：没有可靠分数")
        let enable = app.buttons["learning.enable"]
        for _ in 0..<5 where !enable.isHittable { app.swipeUp() }
        XCTAssertTrue(enable.exists); XCTAssertFalse(enable.isEnabled)
        XCTAssertFalse(app.alerts["允许训练个人模型？"].exists)
        capture(app, "独立许可与真实资料门槛")
        let bank = app.buttons["learning.questionBank"]
        for _ in 0..<6 where !bank.isHittable { app.swipeUp() }
        XCTAssertTrue(bank.isHittable)
        bank.tap()
        app.buttons["一项重要安排临时变化时，我会先考虑什么？"].tap()
        XCTAssertTrue(app.staticTexts["learning.questionPurpose"].label.contains("固定题库"))
        let question = app.descendants(matching: .any)["learning.question"]
        question.tap(); question.typeText(" 修改")
        XCTAssertTrue(app.staticTexts["learning.questionPurpose"].label.contains("只用于诊断"))
        XCTAssertFalse(app.buttons["learning.createCase"].isEnabled)
        capture(app, "修改题目后只做诊断")
    }
    func testDarkModeKeepsHonestScoreAndTrainingStatusReadable() {
        let app = open(["--uitest-dark"])
        XCTAssertTrue(app.staticTexts["learning.noScore"].exists)
        capture(app, "深色复刻验证")
        for _ in 0..<5 where !app.buttons["learning.enable"].isHittable { app.swipeUp() }
        XCTAssertTrue(app.staticTexts["learning.trainingStatus"].exists)
        XCTAssertFalse(app.buttons["learning.enable"].isEnabled)
        capture(app, "深色自动训练状态")
    }
    func testAccessibilityTextKeepsAllFiveDimensionsAndActionsReachable() {
        let app = open(["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        XCTAssertTrue(app.staticTexts["learning.noScore"].exists)
        capture(app, "极大字号复刻验证概览")
        let expression = app.descendants(matching: .any)["learning.dimension.EXPRESSION"]
        for _ in 0..<12 where !expression.isHittable { app.swipeUp() }
        XCTAssertTrue(expression.exists)
        capture(app, "极大字号五维验证")
        for _ in 0..<10 where !app.buttons["learning.enable"].isHittable { app.swipeUp() }
        XCTAssertTrue(app.buttons["learning.enable"].isHittable)
        XCTAssertFalse(app.buttons["learning.enable"].isEnabled)
        capture(app, "极大字号独立训练许可")
        for _ in 0..<8 where !app.buttons["learning.createCase"].isHittable { app.swipeUp() }
        XCTAssertTrue(app.buttons["learning.createCase"].exists)
        XCTAssertFalse(app.buttons["learning.createCase"].isEnabled)
        capture(app, "极大字号独立本人验证")
        let bank = app.buttons["learning.questionBank"]
        for _ in 0..<5 where !bank.isHittable { app.swipeDown() }
        XCTAssertTrue(bank.isHittable)
        capture(app, "极大字号题库选择")
    }
}

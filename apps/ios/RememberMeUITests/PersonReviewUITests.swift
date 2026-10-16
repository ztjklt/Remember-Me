import XCTest

@MainActor
final class PersonReviewUITests: XCTestCase {
    func testLiveLoopbackReviewAndStyleLifecycle() throws {
        continueAfterFailure = false
        guard let url = Bundle(for: Self.self).url(forResource: "review-pairing", withExtension: "json") else {
            throw XCTSkip("Run scripts/review_fixture_server.py with the approved Backend snapshot before this loopback UI test.")
        }
        let pairing = try Data(contentsOf: url)
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-review-pairing", pairing.base64EncodedString()]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["我的"].waitForExistence(timeout: 10))
        app.tabBars.buttons["我的"].tap()
        app.buttons["更多：核对人物理解"].tap()
        let entry = app.buttons["portrait.review"]
        XCTAssertTrue(entry.waitForExistence(timeout: 10)); entry.tap()
        XCTAssertTrue(app.navigationBars["核对我的理解"].waitForExistence(timeout: 10))
        let candidate = app.buttons["review.candidate.ios_fixture_candidate"]
        XCTAssertTrue(candidate.waitForExistence(timeout: 15)); candidate.tap()
        XCTAssertTrue(app.staticTexts["反例与限制"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["赶时间时我会先行动，不会总等到想清楚。"].exists)
        let evidenceScreenshot = XCTAttachment(screenshot: app.screenshot())
        evidenceScreenshot.name = "iOS actual Backend support and counter evidence"; evidenceScreenshot.lifetime = .keepAlways; add(evidenceScreenshot)
        app.swipeUp()
        app.buttons["review.confirmCandidate"].tap()
        XCTAssertTrue(app.buttons["只留原文，不采用这项理解"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["review.confirmCandidate"].waitForNonExistence(timeout: 10))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.segmentedControls.buttons["待核对"].tap()
        let style = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "review.record.")).firstMatch
        XCTAssertTrue(style.waitForExistence(timeout: 10)); style.tap()
        app.buttons["review.confirmRecord"].tap()
        XCTAssertTrue(app.buttons["review.confirmRecord"].waitForNonExistence(timeout: 10))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.swipeUp(); app.swipeUp()
        let toggle = app.switches["review.style"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 5)); XCTAssertTrue(toggle.isEnabled)
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "1"), object: toggle)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 10), .completed)
        app.buttons["向 Twin 提问并查看依据"].tap()
        let question = app.textFields["twin.input"]
        XCTAssertTrue(question.waitForExistence(timeout: 10)); question.tap(); question.typeText("下班后我会做什么？")
        app.buttons["twin.send"].tap()
        app.swipeUp()
        // The deterministic quote provider returns a source, not a semantic
        // relevance score. Source ordering is intentionally not a UI contract.
        let quote = app.staticTexts.matching(NSPredicate(format: "label == %@ OR label == %@",
            "下班后我喜欢散步，先安静一会儿再做决定。", "赶时间时我会先行动，不会总等到想清楚。")).firstMatch
        XCTAssertTrue(quote.waitForExistence(timeout: 15))
        let twinScreenshot = XCTAttachment(screenshot: app.screenshot())
        twinScreenshot.name = "iOS Twin returns actual fixture source through Backend"; twinScreenshot.lifetime = .keepAlways; add(twinScreenshot)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.swipeDown(); app.swipeDown()
        app.segmentedControls.buttons["已确认"].tap()
        XCTAssertTrue(candidate.waitForExistence(timeout: 10))
        let confirmedStyle = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "review.record.")).firstMatch
        confirmedStyle.tap()
        app.buttons["review.editRecord"].tap()
        let title = app.textFields["review.editor.title"]
        XCTAssertTrue(title.waitForExistence(timeout: 5)); title.tap(); title.typeText("（已核对）")
        app.swipeUp(); app.swipeUp(); app.swipeUp()
        let save = app.buttons["review.editor.save"]
        XCTAssertTrue(save.waitForExistence(timeout: 5)); save.tap()
        XCTAssertTrue(app.buttons["review.confirmRecord"].waitForExistence(timeout: 10))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "iOS edit requires renewed review"; attachment.lifetime = .keepAlways; add(attachment)
    }
}

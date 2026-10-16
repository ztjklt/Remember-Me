import XCTest
@testable import RememberMe

private final class VoiceReviewProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path
        let body: [String: Any]
        if path.hasSuffix("/review") {
            body = ["profile_id":"profile", "status":request.httpMethod == "POST" ? "accepted" : "pending",
                    "reviewed_at":NSNull(), "previewed_at":"2026-10-16T00:00:00+00:00"]
        } else if path.hasSuffix("/retry") {
            body = ["retired_profile_id":"different-profile", "status":"retired"]
        } else { body = [:] }
        client?.urlProtocol(self, didReceive:HTTPURLResponse(url:request.url!,statusCode:200,httpVersion:nil,
            headerFields:["Content-Type":"application/json"])!, cacheStoragePolicy:.notAllowed)
        client?.urlProtocol(self, didLoad:try! JSONSerialization.data(withJSONObject:body))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
final class VoiceReviewTests: XCTestCase {
    private func setup() throws -> (AppModel, APIClient, UserDefaults, String) {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [VoiceReviewProtocol.self]
        let client = try APIClient(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),
            token:"fixture",session:URLSession(configuration:config))
        let pairing = Pairing(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),
            token:"fixture",actorID:"actor",subjectID:"subject",consentID:"recording")
        let suite = "voice-review-" + UUID().uuidString, defaults = UserDefaults(suiteName:suite)!
        let model = AppModel(defaults:defaults,pairing:pairing,apiClientFactory:{ _ in client })
        model.realtimeVoice.enrolled(.init(ready:true,profile_id:"profile",status:"ready",model_version:"fixture",voice_consent_id:"voice"))
        return (model,client,defaults,suite)
    }
    func testReadyVoiceRequiresExplicitReviewAndReviewCannotApplyToSuccessor() async throws {
        let (model,_,defaults,suite) = try setup(); defer { defaults.removePersistentDomain(forName:suite) }
        XCTAssertFalse(model.personalVoiceAccepted)
        await model.refreshRealtimeVoiceReview()
        XCTAssertEqual(model.realtimeVoiceReview?.status,"pending"); XCTAssertFalse(model.personalVoiceAccepted)
        await model.reviewRealtimeVoice(accepted:true)
        XCTAssertTrue(model.personalVoiceAccepted)
        model.realtimeVoice.enrolled(.init(ready:true,profile_id:"successor",status:"ready",model_version:"fixture",voice_consent_id:"voice"))
        XCTAssertFalse(model.personalVoiceAccepted)
    }
    func testRetryWithWrongProfileReceiptDoesNotClearCurrentVoice() async throws {
        let (model,_,defaults,suite) = try setup(); defer { defaults.removePersistentDomain(forName:suite) }
        await model.retryRealtimeVoice()
        XCTAssertEqual(model.realtimeVoice.profile?.profile_id,"profile")
        XCTAssertNotNil(model.errorMessage)
    }
    func testApprovedVoiceIsSelectedOnReentryAndExplicitDefaultChoicePersists() async throws {
        let (model, client, defaults, suite) = try setup()
        defer { defaults.removePersistentDomain(forName: suite) }
        XCTAssertTrue(model.useDefaultRealtimeVoice)
        await model.reviewRealtimeVoice(accepted: true)
        XCTAssertFalse(model.useDefaultRealtimeVoice)
        model.useDefaultRealtimeVoice = true

        let reopened = AppModel(defaults: defaults, pairing: model.pairing, apiClientFactory: { _ in client })
        reopened.realtimeVoice.enrolled(model.realtimeVoice.profile!)
        reopened.realtimeVoiceReview = model.realtimeVoiceReview
        XCTAssertTrue(reopened.useDefaultRealtimeVoice)
        reopened.useDefaultRealtimeVoice = false
        XCTAssertFalse(model.useDefaultRealtimeVoice)
    }
    func testVoiceChoiceCannotApproveOrCarryOverToAnotherProfile() async throws {
        let (model, _, defaults, suite) = try setup()
        defer { defaults.removePersistentDomain(forName: suite) }
        model.useDefaultRealtimeVoice = false
        XCTAssertTrue(model.useDefaultRealtimeVoice)
        await model.reviewRealtimeVoice(accepted: true)
        model.useDefaultRealtimeVoice = true
        model.realtimeVoice.enrolled(.init(ready: true, profile_id: "successor", status: "ready", model_version: "fixture", voice_consent_id: "voice"))
        XCTAssertTrue(model.useDefaultRealtimeVoice)
        model.realtimeVoiceReview = .init(profile_id: "successor", status: "accepted", reviewed_at: nil, previewed_at: nil)
        XCTAssertFalse(model.useDefaultRealtimeVoice)
        model.realtimeVoiceReview = nil
        XCTAssertTrue(model.useDefaultRealtimeVoice)
    }
    func testReviewForPreviousProfileCannotEnableSuccessor() async throws {
        let (model,_,defaults,suite) = try setup(); defer { defaults.removePersistentDomain(forName:suite) }
        model.realtimeVoice.enrolled(.init(ready:true,profile_id:"successor",status:"ready",model_version:"fixture",voice_consent_id:"voice"))
        await model.refreshRealtimeVoiceReview()
        XCTAssertNil(model.realtimeVoiceReview)
        XCTAssertFalse(model.personalVoiceAccepted)
    }
}

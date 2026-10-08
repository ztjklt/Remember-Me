import XCTest
@testable import RememberMe

// Each test has its own response store and URLSession. No request leaves the test process.
private final class Responses: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: (Int, Data)] = [:]
    private var paths: [String] = []
    func set(_ path: String, status: Int = 200, json: String) {
        lock.lock(); defer { lock.unlock() }
        values[path] = (status, Data(json.utf8))
    }
    func reply(_ request: URLRequest) -> (Int, Data) {
        lock.lock(); defer { lock.unlock() }
        let key = "\(request.httpMethod ?? "GET") \(request.url!.path)"
        paths.append(key)
        return values[key] ?? (500, Data("Unexpected test request".utf8))
    }
    var requests: [String] {
        lock.lock(); defer { lock.unlock() }
        return paths
    }
}
private final class ResponseRegistry: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: Responses] = [:]
    func add(_ responses: Responses, id: String) {
        lock.lock(); defer { lock.unlock() }; values[id] = responses
    }
    func get(_ id: String) -> Responses? {
        lock.lock(); defer { lock.unlock() }; return values[id]
    }
}
private final class StubProtocol: URLProtocol, @unchecked Sendable {
    static let registry = ResponseRegistry()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let id = request.value(forHTTPHeaderField: "X-Scenario-ID"),
              let responses = Self.registry.get(id) else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse)); return
        }
        let (status, data) = responses.reply(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: status,
                                       httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
final class AgentCoreRecoveryTests: XCTestCase {
    private let base = "/api/v1/subjects/test-subject"
    private let memoryJSON = #"{"memory_item_id":"memory-one","episode_id":"episode-one","content":"我喜欢散步","memory_type":"PREFERENCE","domain":"PREFERENCES","source_type":"AI_INFERENCE","confidence":0.8,"model_version":"test-model","recorded_at":"2026-10-08T00:00:00Z","evidence":[]}"#
    private let traitJSON = #"{"trait_id":"trait-one","statement":"我喜欢散步","context":"周末","confidence":0.8,"evidence_ids":["ev-one"],"counter_evidence_ids":[],"status":"active","model_version":"test-model","source_type":"AI_INFERENCE","valid_from":"2026-10-08T00:00:00Z"}"#
    private func calibration(_ id: String = "cal-one", status: String = "awaiting_human") -> String {
        #"{"calibration_id":"\#(id)","twin_answer_id":"answer-one","question":"我喜欢什么？","locked_answer":"我喜欢散步","status":"\#(status)","human_episode_id":"human-one","dimensions":[],"summary":"校准结果"}"#
    }
    private func decode<T: Decodable>(_ json: String, as type: T.Type) throws -> T {
        try JSONDecoder().decode(type, from: Data(json.utf8))
    }
    private func makeModel(_ responses: Responses) -> AppModel {
        let id = UUID().uuidString
        StubProtocol.registry.add(responses, id: id)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        config.httpAdditionalHeaders = ["X-Scenario-ID": id]
        let session = URLSession(configuration: config)
        let pairing = Pairing(baseURL: "https://test.invalid", fingerprint: String(repeating: "a", count: 64),
                              token: "synthetic-token", actorID: "test-actor", subjectID: "test-subject", consentID: "recording-grant")
        let defaults = UserDefaults(suiteName: "AgentCoreTests-" + id)!
        return AppModel(pairing: pairing, defaults: defaults, clientFactory: {
            try APIClient(baseURL: $0.baseURL, fingerprint: $0.fingerprint, token: $0.token, session: session)
        })
    }
    private func coreResponses(_ responses: Responses) {
        responses.set("GET \(base)/memories", json: #"{"items":[\#(memoryJSON)]}"#)
        responses.set("GET \(base)/episodes", json: #"{"items":[]}"#)
        responses.set("GET \(base)/person-model", json: #"{"version":3,"domains":[{"domain":"PREFERENCES","traits":[\#(traitJSON)]}]}"#)
        responses.set("GET \(base)/questions", json: #"{"items":[]}"#)
        responses.set("GET /api/v1/consents", json: #"[{"consent_id":"cloud-grant","scope":"CLOUD_TWIN","status":"granted"}]"#)
        responses.set("GET \(base)/calibrations", json: #"{"items":[\#(calibration())]}"#)
        responses.set("GET \(base)/voice/profile", json: #"{"ready":false}"#)
    }
    func testVoiceOutageDoesNotBlockPersonModelOrCalibrationRefresh() async {
        let responses = Responses(); coreResponses(responses)
        responses.set("GET \(base)/voice/profile", status: 503, json: #"{"message":"synthetic outage"}"#)
        let model = makeModel(responses)
        await model.refresh()
        XCTAssertEqual(model.modelVersion, 3)
        XCTAssertEqual(model.domains.first?.traits.first?.id, "trait-one")
        XCTAssertEqual(model.calibrationRun?.id, "cal-one")
        XCTAssertEqual(model.cloudConsentID, "cloud-grant")
        XCTAssertNil(model.errorMessage)
        XCTAssertNotNil(model.voiceRefreshError)
    }
    func testFailedCoreRefreshDoesNotPublishMixedVersions() async throws {
        let responses = Responses(); coreResponses(responses)
        let model = makeModel(responses)
        await model.refresh()
        responses.set("GET \(base)/memories", json: #"{"items":[]}"#)
        responses.set("GET \(base)/person-model", status: 503, json: #"{"message":"unavailable"}"#)
        await model.refresh()
        XCTAssertEqual(model.memories.count, 1)
        XCTAssertEqual(model.modelVersion, 3)
        XCTAssertNotNil(model.errorMessage)
    }
    func testDeletionInvalidatesLocalUnderstandingEvenWhenRefreshFails() async throws {
        let responses = Responses(); coreResponses(responses)
        let model = makeModel(responses)
        await model.refresh()
        let memory = try XCTUnwrap(model.memories.first)
        responses.set("DELETE \(base)/memories/memory-one", json: #"{"model_version":4}"#)
        responses.set("GET \(base)/person-model", status: 503, json: #"{"message":"unavailable"}"#)
        let removed = await model.delete(memory)
        XCTAssertTrue(removed)
        XCTAssertTrue(model.memories.isEmpty)
        XCTAssertTrue(model.domains.isEmpty)
        XCTAssertNil(model.calibrationRun)
        XCTAssertNil(model.twinAnswer)
        XCTAssertNotNil(model.errorMessage)
    }
    func testComparisonFailureCanRetrySameLockedRunWithoutAnotherEpisode() async throws {
        let responses = Responses()
        let path = "POST \(base)/calibrations/cal-one/complete"
        responses.set(path, status: 503, json: #"{"message":"synthetic provider outage"}"#)
        let model = makeModel(responses)
        model.cloudConsentID = "cloud-grant"
        model.calibrationRun = try decode(calibration(), as: CalibrationRecord.self)
        await model.completeCalibration("cal-one")
        XCTAssertEqual(model.calibrationRun?.locked_answer, "我喜欢散步")
        XCTAssertEqual(model.calibrationRun?.human_episode_id, "human-one")
        XCTAssertNotNil(model.errorMessage)
        responses.set(path, json: calibration(status: "complete"))
        await model.completeCalibration("cal-one")
        XCTAssertEqual(model.calibrationRun?.status, "complete")
        XCTAssertEqual(model.calibrationRun?.locked_answer, "我喜欢散步")
        XCTAssertNil(model.errorMessage)
        XCTAssertEqual(responses.requests, [path, path])
    }
    func testRefreshKeepsSelectedCalibrationAndHidesUnavailableHistory() async throws {
        let responses = Responses(); coreResponses(responses)
        responses.set("GET \(base)/calibrations", json: #"{"items":[\#(calibration("cal-new")),\#(calibration("cal-old"))]}"#)
        let model = makeModel(responses)
        model.calibrationRun = try decode(calibration("cal-old"), as: CalibrationRecord.self)
        await model.refresh()
        XCTAssertEqual(model.calibrationRun?.id, "cal-old")
        responses.set("GET \(base)/calibrations", status: 503, json: #"{"message":"unavailable"}"#)
        await model.refresh()
        XCTAssertNil(model.calibrationRun)
        XCTAssertTrue(model.calibrationRuns.isEmpty)
        XCTAssertNotNil(model.calibrationRefreshError)
        XCTAssertEqual(model.modelVersion, 3)
    }
    func testPendingRecordingCannotBeOverwrittenByNewCalibrationCapture() async {
        let model = makeModel(Responses())
        let original = RecordingDraft(id: "saved-recording", fileURL: URL(fileURLWithPath: "/synthetic.m4a"),
                                      recordedAt: Date(), durationMS: 1000, questionID: nil,
                                      calibrationID: "cal-old", consentConfirmedAt: Date())
        model.draft = original
        await model.startRecording(calibrationID: "cal-new")
        XCTAssertEqual(model.draft?.id, original.id)
        XCTAssertEqual(model.draft?.calibrationID, "cal-old")
        XCTAssertFalse(model.isRecording)
        XCTAssertNotNil(model.errorMessage)
    }
    func testCloudRevocationRemovesLocalAnswerAndCalibrationSnapshots() async throws {
        let responses = Responses(); coreResponses(responses)
        responses.set("POST /api/v1/consents/cloud-grant/revoke", json: #"{"status":"revoked"}"#)
        let model = makeModel(responses)
        await model.refresh()
        XCTAssertNotNil(model.calibrationRun)
        await model.revokeCloudTwin()
        XCTAssertNil(model.cloudConsentID)
        XCTAssertNil(model.calibrationRun)
        XCTAssertTrue(model.calibrationRuns.isEmpty)
        XCTAssertNil(model.twinAnswer)
    }
}

import XCTest
@testable import RememberMe

// Each test has its own response store and URLSession. No request leaves the test process.
private final class Responses: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: (Int, Data)] = [:]
    private var paths: [String] = []
    private var failures: [String: URLError] = [:]
    private var timeouts: [String: TimeInterval] = [:]
    func fail(_ path: String, error: URLError) {
        lock.lock(); defer { lock.unlock() }; failures[path] = error
    }
    func failure(_ request: URLRequest) -> URLError? {
        lock.lock(); defer { lock.unlock() }
        return failures["\(request.httpMethod ?? "GET") \(request.url!.path)"]
    }
    func timeout(_ path: String) -> TimeInterval? {
        lock.lock(); defer { lock.unlock() }; return timeouts[path]
    }
    func set(_ path: String, status: Int = 200, json: String) {
        lock.lock(); defer { lock.unlock() }
        values[path] = (status, Data(json.utf8))
    }
    func reply(_ request: URLRequest) -> (Int, Data) {
        lock.lock(); defer { lock.unlock() }
        let key = "\(request.httpMethod ?? "GET") \(request.url!.path)"
        paths.append(key)
        timeouts[key] = request.timeoutInterval
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
        if let error = responses.failure(request) {
            client?.urlProtocol(self, didFailWithError: error); return
        }
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
        }, connectionFactory: {
            try APIClient(baseURL: $0, fingerprint: $1, session: session)
        }, savePairing: { _ in })
    }
    private func localDraft() throws -> RecordingDraft {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
        try Data("synthetic-test-audio".utf8).write(to: url)
        return RecordingDraft(id: UUID().uuidString, fileURL: url, recordedAt: Date(),
                              durationMS: 13000, questionID: nil, calibrationID: nil,
                              consentConfirmedAt: Date())
    }
    func testAppUpdateRecoversRecordingFromRelocatedDataContainer() throws {
        let id = UUID().uuidString
        let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Recordings", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let current = directory.appendingPathComponent(id + ".m4a")
        try Data("preserved-original-audio".utf8).write(to: current)
        let defaults = UserDefaults(suiteName: "RelocatedRecording-" + id)!
        defer {
            try? FileManager.default.removeItem(at: current)
            defaults.removePersistentDomain(forName: "RelocatedRecording-" + id)
        }
        let stale = RecordingDraft(id: id, fileURL: URL(fileURLWithPath: "/old-container/Recordings/" + id + ".m4a"),
            recordedAt: Date(), durationMS: 13000, questionID: "question", calibrationID: "calibration",
            consentConfirmedAt: Date())
        defaults.set(try JSONEncoder().encode(stale), forKey: "pending-recording")
        let model = AppModel(pairing: nil, defaults: defaults)
        XCTAssertEqual(model.draft?.id, id)
        XCTAssertEqual(model.draft?.fileURL, current)
        XCTAssertEqual(model.draft?.questionID, "question")
        XCTAssertEqual(model.draft?.calibrationID, "calibration")
        XCTAssertEqual(try Data(contentsOf: XCTUnwrap(model.draft).fileURL), Data("preserved-original-audio".utf8))
        XCTAssertEqual(AppModel(pairing: nil, defaults: defaults).draft?.fileURL, current)
    }
    func testUnuploadedRecordingCanReconnectToSamePersonWithoutLosingAudio() async throws {
        let responses = Responses(); coreResponses(responses)
        responses.set("POST /api/v1/local-pairing/claim", json: #"{"actor_token":"new-synthetic","actor_id":"test-actor","subject_id":"test-subject","recording_consent_id":"recording-grant"}"#)
        let model = makeModel(responses); let draft = try localDraft()
        defer { try? FileManager.default.removeItem(at: draft.fileURL) }
        model.draft = draft; model.pairingServer = "https://new.test.invalid"
        model.pairingFingerprint = String(repeating: "b", count: 64); model.pairingCode = "synthetic-one-time-code"
        await model.connect()
        XCTAssertNil(model.errorMessage)
        XCTAssertEqual(model.pairing?.baseURL, "https://new.test.invalid")
        XCTAssertEqual(model.draft?.id, draft.id)
        XCTAssertEqual(try Data(contentsOf: draft.fileURL), Data("synthetic-test-audio".utf8))
        XCTAssertEqual(responses.timeout("POST /api/v1/local-pairing/claim"), 15)
    }
    func testPendingRecordingCannotBeMovedToAnotherPerson() async throws {
        let responses = Responses()
        responses.set("POST /api/v1/local-pairing/claim", json: #"{"actor_token":"synthetic-other","actor_id":"other-actor","subject_id":"other-subject","recording_consent_id":"other-grant"}"#)
        let model = makeModel(responses); let original = model.pairing; let draft = try localDraft()
        defer { try? FileManager.default.removeItem(at: draft.fileURL) }
        model.draft = draft; model.pairingServer = "https://new.test.invalid"
        model.pairingFingerprint = String(repeating: "b", count: 64)
        await model.connect()
        XCTAssertEqual(model.pairing, original)
        XCTAssertEqual(model.draft?.id, draft.id)
        XCTAssertNotNil(model.errorMessage)
        XCTAssertEqual(responses.requests, ["POST /api/v1/local-pairing/claim"])
    }
    func testUploadedEpisodeCannotSwitchServices() async {
        let responses = Responses(); let model = makeModel(responses)
        model.episodeID = "already-uploaded"
        await model.connect()
        XCTAssertNotNil(model.errorMessage)
        XCTAssertTrue(responses.requests.isEmpty)
        XCTAssertEqual(model.episodeID, "already-uploaded")
    }
    func testUploadTimeoutEndsBusyStateAndPreservesRetryableRecording() async throws {
        let responses = Responses(); responses.fail("POST /api/v1/episodes", error: URLError(.timedOut))
        let model = makeModel(responses); let draft = try localDraft()
        defer { try? FileManager.default.removeItem(at: draft.fileURL) }
        model.draft = draft
        await model.sendRecording()
        XCTAssertFalse(model.isBusy)
        XCTAssertNil(model.episodeID)
        XCTAssertEqual(model.draft?.id, draft.id)
        XCTAssertEqual(model.processingStatus, "上传未完成")
        XCTAssertNotNil(model.errorMessage)
        XCTAssertTrue(model.errorMessage?.contains("本地网络") == true)
        XCTAssertEqual(responses.timeout("POST /api/v1/episodes"), 30)
        await model.sendRecording()
        XCTAssertEqual(model.draft?.id, draft.id)
        XCTAssertEqual(responses.requests.count, 2)
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
    func testGuidanceRestSurvivesRestartAndStaysWithinSubject() throws {
        let suite = "CaptureRestTests-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let own = Pairing(baseURL: "https://test.invalid", fingerprint: String(repeating: "a", count: 64),
                          token: "synthetic", actorID: "actor", subjectID: "own", consentID: "grant")
        let model = AppModel(pairing: own, defaults: defaults)
        model.questions = [try decode(#"{"question_id":"q","text":"你的经历？","target_domain":"IDENTITY","reason":"missing_domain","evidence_ids":[]}"#, as: QuestionRecord.self)]
        model.restFromGuidance()
        XCTAssertTrue(model.guidancePaused)
        XCTAssertTrue(model.suggestedQuestions.isEmpty)
        XCTAssertEqual(model.questions.count, 1)
        let reopened = AppModel(pairing: own, defaults: defaults)
        XCTAssertTrue(reopened.guidancePaused)
        let other = Pairing(baseURL: own.baseURL, fingerprint: own.fingerprint, token: "synthetic-other",
                            actorID: "other", subjectID: "other", consentID: "other-grant")
        XCTAssertFalse(AppModel(pairing: other, defaults: defaults).guidancePaused)
        model.resumeGuidance()
        XCTAssertEqual(model.suggestedQuestions.count, 1)
        XCTAssertFalse(AppModel(pairing: own, defaults: defaults).guidancePaused)
    }

    func testExpiredRestReopensSuggestions() throws {
        let model = makeModel(Responses())
        model.captureRestUntil = Date().addingTimeInterval(-1)
        XCTAssertFalse(model.guidancePaused)
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
        responses.set("GET \(base)/questions", json: #"{"items":[{"question_id":"next","text":"现在最看重什么？","target_domain":"VALUES_BELIEFS","reason":"calibration_gap"}]}"#)
        await model.completeCalibration("cal-one")
        XCTAssertEqual(model.calibrationRun?.status, "complete")
        XCTAssertEqual(model.calibrationRun?.locked_answer, "我喜欢散步")
        XCTAssertNil(model.errorMessage)
        XCTAssertEqual(responses.requests.filter { $0.hasPrefix("POST") }, [path, path])
        XCTAssertEqual(model.questions.first?.id, "next")
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

    func testPortraitFacetsJoinOnlyMatchingLiveEvidenceAndClearOnOutage() async {
        let responses = Responses(); coreResponses(responses)
        let memory = memoryJSON.replacingOccurrences(of: #""evidence":[]"#, with:
            #""evidence":[{"evidence_id":"ev-one","excerpt":"我喜欢散步","source_type":"SUBJECT","source_ref":"episode:episode-one#span:0-5"}]"#)
        responses.set("GET \(base)/memories", json: #"{"items":[\#(memory)]}"#)
        responses.set("GET /api/v1/episodes/episode-one/result", json:
            #"{"memory_items":[{"content":"我喜欢散步","evidence_ids":["ev-one"],"metadata":{"facets":[{"category":"mood","label":"散步时安心","quote":"我喜欢散步","evidence_ids":["ev-one"]},{"category":"mood","label":"虚构","quote":"从未说过","evidence_ids":["ev-one"]}]}}]}"#)
        let model = makeModel(responses)
        await model.refresh()
        XCTAssertEqual(model.facets("mood").map(\.label), ["散步时安心"])
        responses.set("GET /api/v1/episodes/episode-one/result", status: 503, json: #"{"message":"outage"}"#)
        await model.refresh()
        XCTAssertTrue(model.portraitFacets.isEmpty)
        XCTAssertNotNil(model.portraitRefreshError)
        XCTAssertEqual(model.modelVersion, 3)
        XCTAssertNil(model.errorMessage)
    }

    func testCompletedComparisonSurvivesNextPlanOutage() async throws {
        let responses = Responses()
        responses.set("POST \(base)/calibrations/cal-one/complete", json: calibration(status: "complete"))
        responses.set("GET \(base)/questions", status: 503, json: #"{"message":"outage"}"#)
        let model = makeModel(responses); model.cloudConsentID = "cloud-grant"
        await model.completeCalibration("cal-one")
        XCTAssertEqual(model.calibrationRun?.status, "complete")
        XCTAssertNil(model.errorMessage)
        XCTAssertNotNil(model.questionRefreshError)
        XCTAssertTrue(model.questions.isEmpty)
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

    func testRetryStopsAtTranscriptReviewAndResumesWithoutLocalDraft() async {
        let responses = Responses(); coreResponses(responses)
        responses.set("POST /api/v1/episodes/remote-one/retry", json: #"{"status":"extracting"}"#)
        responses.set("GET /api/v1/episodes/remote-one", json: #"{"status":"extracting"}"#)
        responses.set("GET /api/v1/episodes/remote-one/transcript-review", json:
            #"{"state":"reviewing","transcript":"我喜欢散步","stt_model_version":"test-stt"}"#)
        let model = makeModel(responses)
        await model.retryEpisode("remote-one")
        XCTAssertFalse(model.isBusy)
        XCTAssertNil(model.draft)
        XCTAssertEqual(model.episodeID, "remote-one")
        XCTAssertTrue(model.isTranscriptReviewReady)
        XCTAssertEqual(model.transcriptDraft, "我喜欢散步")
        await model.sendRecording()
        XCTAssertEqual(responses.requests.filter { $0 == "POST /api/v1/episodes/remote-one/retry" }.count, 1)
        XCTAssertFalse(responses.requests.contains("POST /api/v1/episodes"))
    }

    func testResumeCannotReplaceAnotherPendingRecording() async {
        let responses = Responses(); let model = makeModel(responses)
        model.episodeID = "current-one"
        await model.resumeEpisode("different-one")
        XCTAssertEqual(model.episodeID, "current-one")
        XCTAssertNotNil(model.errorMessage)
        XCTAssertTrue(responses.requests.isEmpty)
    }
}

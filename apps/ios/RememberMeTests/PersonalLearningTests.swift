import XCTest
@testable import RememberMe

private let learningFixture = #"{"enabled":false,"policy":"personal-learning-v1","notice":"Only confirmed owner data.","status":"disabled","trainer_available":false,"training_consent_id":null,"dataset":{"examples":0,"source_groups":0,"train":0,"validation":0,"test":0,"missing":[]},"requirements":{"min_examples":40,"min_source_groups":10},"job":null,"activation_allowed":false}"#
private let fidelityFixture = #"{"label":"未见问题上的本人一致率","status":"insufficient_data","accepted_observation_count":0,"independent_group_count":0,"excluded_observation_count":0,"dimensions":[{"dimension":"DECISION","label":"选择","status":"insufficient_data","observed_count":0,"independent_group_count":0,"matching_group_count":0,"agreement_rate":null,"confidence_interval":null,"gaps":[]},{"dimension":"REASONING","label":"理由","status":"insufficient_data","observed_count":0,"independent_group_count":0,"matching_group_count":0,"agreement_rate":null,"confidence_interval":null,"gaps":[]},{"dimension":"VALUE_PRIORITY","label":"价值优先级","status":"insufficient_data","observed_count":0,"independent_group_count":0,"matching_group_count":0,"agreement_rate":null,"confidence_interval":null,"gaps":[]},{"dimension":"EMOTIONAL_REACTION","label":"情绪反应","status":"insufficient_data","observed_count":0,"independent_group_count":0,"matching_group_count":0,"agreement_rate":null,"confidence_interval":null,"gaps":[]},{"dimension":"EXPRESSION","label":"表达","status":"insufficient_data","observed_count":0,"independent_group_count":0,"matching_group_count":0,"agreement_rate":null,"confidence_interval":null,"gaps":[]}],"overall":{"agreement_rate":null,"confidence_interval":null,"gaps":["DECISION"]},"interpretation":"Not personality completeness.","cases":[],"question_bank":[{"question_id":"bank_01","question_group_id":"tradeoff_01","question":"一项重要安排临时变化时，我会先考虑什么？"}]}"#

private final class PersonalLearningStub: @unchecked Sendable {
    let lock = NSLock()
    private var requestRecords: [(String, String, [String: Any])] = []
    private var paused: [PersonalLearningProtocol] = []
    var pauseGET = false
    var rejectRatings = false
    private var caseStatus = "awaiting_human"
    private var human = ""
    private var ratings: [String: String] = [:]
    func reset() {
        lock.lock(); defer { lock.unlock() }
        requestRecords = []; paused = []; pauseGET = false; rejectRatings = false
        caseStatus = "awaiting_human"; human = ""; ratings = [:]
    }
    func receive(_ protocolObject: PersonalLearningProtocol) {
        let request = protocolObject.request
        let path = request.url!.path, method = request.httpMethod ?? "GET"
        var data = request.httpBody
        if data == nil, let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var result = Data(), bytes = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let size = stream.read(&bytes, maxLength: bytes.count)
                if size <= 0 { break }; result.append(contentsOf: bytes.prefix(size))
            }
            data = result
        }
        let fields = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        lock.lock()
        requestRecords.append((path, method, fields))
        if pauseGET && method == "GET" { paused.append(protocolObject); lock.unlock(); return }
        let response = responseLocked(path: path, method: method, fields: fields)
        lock.unlock()
        protocolObject.finish(status: response.0, body: response.1)
    }
    private func responseLocked(path: String, method: String, fields: [String: Any]) -> (Int, String) {
        if path.hasSuffix("/consents") {
            return (200, #"{"consent_id":"training-owner","scope":"MODEL_TRAINING","status":"granted"}"#)
        }
        if path.hasSuffix("/revoke") { return (200, "{}") }
        if path.hasSuffix("/learning") {
            if method == "PUT", fields["enabled"] as? Bool == true {
                return (200, learningFixture.replacingOccurrences(of: "\"enabled\":false", with: "\"enabled\":true")
                    .replacingOccurrences(of: "\"status\":\"disabled\"", with: "\"status\":\"insufficient_data\"")
                    .replacingOccurrences(of: "\"training_consent_id\":null", with: "\"training_consent_id\":\"training-owner\""))
            }
            return (200, learningFixture)
        }
        if path.hasSuffix("/fidelity") { return (200, fidelityFixture) }
        if path.hasSuffix("/human-answer") {
            human = fields["answer"] as? String ?? ""; caseStatus = "awaiting_rating"
        }
        if path.hasSuffix("/ratings") {
            if rejectRatings { return (409, #"{"error":{"message":"source changed"}}"#) }
            ratings = fields["ratings"] as? [String: String] ?? [:]; caseStatus = "rated"
        }
        if path.contains("/fidelity/cases") {
            var result: [String: Any] = ["case_id": "fc_fixture", "question": "未见的情境？", "status": caseStatus,
                "response_type": "SIMULATION", "human_answer": human.isEmpty ? NSNull() as Any : human as Any,
                "ratings": ratings, "created_at": "2026-10-14T00:00:00Z"]
            if caseStatus != "awaiting_human" { result["locked_answer"] = "先前锁定的预测" }
            return (200, String(data: try! JSONSerialization.data(withJSONObject: result), encoding: .utf8)!)
        }
        return (503, #"{"error":{"message":"Unexpected fixture request"}}"#)
    }
    func records() -> [(String, String, [String: Any])] {
        lock.lock(); defer { lock.unlock() }; return requestRecords
    }
    func releasePaused() {
        lock.lock(); let pending = paused; paused = []; pauseGET = false; lock.unlock()
        for item in pending { item.finish(status: 200, body: item.request.url!.path.hasSuffix("/learning") ? learningFixture : fidelityFixture) }
    }
}
private final class PersonalLearningProtocol: URLProtocol, @unchecked Sendable {
    static let state = PersonalLearningStub()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { Self.state.receive(self) }
    override func stopLoading() { }
    func finish(status: Int, body: String) {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status,
            httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
}

@MainActor
final class PersonalLearningTests: XCTestCase {
    private func pairing(actor: String = "owner", token: String = "fixture") -> Pairing {
        Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                token: token, actorID: actor, subjectID: "subject", consentID: "recording")
    }
    private func client() throws -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PersonalLearningProtocol.self]
        return try APIClient(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                             token: "fixture", session: URLSession(configuration: configuration))
    }
    private func configuredModel() async throws -> PersonalLearningModel {
        PersonalLearningProtocol.state.reset()
        let model = PersonalLearningModel()
        model.configure(pairing: pairing(), client: try client()); await model.load()
        return model
    }
    func testNullScoreRemainsUnmeasuredRatherThanZeroPercent() throws {
        let report = try JSONDecoder().decode(FidelityReportRecord.self, from: Data(fidelityFixture.utf8))
        XCTAssertNil(report.measuredRate)
        XCTAssertTrue(report.dimensions.allSatisfy { $0.measuredRate == nil })
        XCTAssertEqual(report.accepted_observation_count, 0)
    }
    func testIneligibleTrainingDataRequiresReviewWithoutSuggestingTrainingSucceeded() throws {
        let payload = learningFixture.replacingOccurrences(of: "\"status\":\"disabled\"", with: "\"status\":\"ineligible_data\"")
        let record = try JSONDecoder().decode(PersonalLearningRecord.self, from: Data(payload.utf8))
        XCTAssertEqual(record.statusTitle, "训练资料需要核对")
        XCTAssertTrue(record.statusExplanation.contains("这次不会训练或生效"))
        XCTAssertFalse(record.activation_allowed); XCTAssertNil(record.job)
    }
    func testAvailableScoreRequiresFiveSufficientDimensionsAndFiniteInterval() throws {
        let zero = try JSONDecoder().decode(FidelityReportRecord.self, from: Data(fidelityFixture.utf8))
        let valid = FidelityInterval(lower: 0.70, upper: 0.95, confidence_level: 0.99)
        let dimensions = zero.dimensions.map { FidelityDimensionRecord(dimension: $0.dimension, label: $0.label,
            status: "available", observed_count: 40, independent_group_count: 40, matching_group_count: 32,
            agreement_rate: 0.8, confidence_interval: valid, gaps: []) }
        func report(_ items: [FidelityDimensionRecord], interval: FidelityInterval?) -> FidelityReportRecord {
            FidelityReportRecord(label: zero.label, status: "available", accepted_observation_count: 40,
                independent_group_count: 40, excluded_observation_count: 0, dimensions: items,
                overall: FidelityOverallRecord(agreement_rate: 0.8, confidence_interval: interval, gaps: []),
                interpretation: zero.interpretation, cases: [], question_bank: zero.question_bank)
        }
        XCTAssertEqual(report(dimensions, interval: valid).measuredRate, 0.8)
        XCTAssertNil(report(Array(dimensions.dropLast()), interval: valid).measuredRate)
        XCTAssertNil(report(dimensions, interval: FidelityInterval(lower: .nan, upper: 0.95, confidence_level: 0.95)).measuredRate)
        XCTAssertNil(report(dimensions, interval: nil).measuredRate)
    }
    func testDebugPreviewCannotReadGrantTrainOrCreateRealVerification() async throws {
        PersonalLearningProtocol.state.reset()
        let model = PersonalLearningModel(preview: true)
        model.configure(pairing: pairing(), client: try client())
        await model.load(); await model.enableTraining(acceptedPolicy: "isolated-preview")
        await model.disableTraining(); await model.revokeTraining()
        await model.createCase(question: "test", cloudConsentID: "cloud")
        await model.confirmHumanAnswer("human", confirmed: true)
        await model.submitRatings(["DECISION": "MATCH"], confirmed: true)
        XCTAssertEqual(PersonalLearningProtocol.state.records().count, 0)
        XCTAssertFalse(model.canMutate); XCTAssertFalse(model.learning?.enabled ?? true)
        XCTAssertNil(model.fidelity?.measuredRate); XCTAssertNil(model.selectedCase)
    }
    func testDisconnectedModelCannotEnableOrSendRequests() async throws {
        PersonalLearningProtocol.state.reset()
        let model = PersonalLearningModel()
        model.configure(pairing: nil, client: try client())
        await model.load(); await model.enableTraining(acceptedPolicy: "personal-learning-v1")
        await model.createCase(question: "test", cloudConsentID: "cloud")
        XCTAssertFalse(model.canMutate); XCTAssertNil(model.learning)
        XCTAssertEqual(PersonalLearningProtocol.state.records().count, 0)
    }
    func testPolicyMismatchCannotGrantTrainingPermission() async throws {
        let model = try await configuredModel()
        await model.enableTraining(acceptedPolicy: "obsolete-policy")
        XCTAssertFalse(PersonalLearningProtocol.state.records().contains { $0.0.hasSuffix("/consents") })
        XCTAssertFalse(model.learning!.enabled)
    }
    func testEnableHasSeparateConsentAndPolicyAndDisableKeepsRevokeHandle() async throws {
        let model = try await configuredModel()
        await model.enableTraining(acceptedPolicy: "personal-learning-v1")
        XCTAssertTrue(model.learning!.enabled)
        XCTAssertEqual(model.learning!.status, "insufficient_data")
        XCTAssertEqual(model.trainingConsentID, "training-owner")
        let records = PersonalLearningProtocol.state.records()
        XCTAssertEqual(records.first(where: { $0.0.hasSuffix("/consents") })?.2["scope"] as? String, "MODEL_TRAINING")
        let put = records.first(where: { $0.1 == "PUT" })!.2
        XCTAssertEqual(put["accepted_policy"] as? String, "personal-learning-v1")
        XCTAssertEqual(put["training_consent_id"] as? String, "training-owner")
        await model.disableTraining()
        XCTAssertFalse(model.learning!.enabled)
        XCTAssertEqual(model.trainingConsentID, "training-owner")
        await model.revokeTraining()
        XCTAssertNil(model.trainingConsentID)
        XCTAssertTrue(PersonalLearningProtocol.state.records().contains { $0.0.hasSuffix("/training-owner/revoke") })
    }
    func testIndependentHumanAnswerMustBeExplicitlyConfirmedBeforePredictionAppears() async throws {
        let model = try await configuredModel()
        await model.createCase(question: "新的情境？", cloudConsentID: "cloud")
        XCTAssertEqual(model.selectedCase?.status, "awaiting_human")
        XCTAssertNil(model.selectedCase?.visiblePrediction)
        await model.confirmHumanAnswer("本人回答", confirmed: false)
        XCTAssertFalse(PersonalLearningProtocol.state.records().contains { $0.0.hasSuffix("/human-answer") })
        await model.confirmHumanAnswer("本人回答", confirmed: true)
        XCTAssertEqual(model.selectedCase?.human_answer, "本人回答")
        XCTAssertEqual(model.selectedCase?.visiblePrediction, "先前锁定的预测")
        XCTAssertEqual(PersonalLearningProtocol.state.records().first(where: { $0.0.hasSuffix("/human-answer") })?.2["confirmed"] as? Bool, true)
    }
    func testCustomQuestionCannotPretendToBeAnIndependentBenchmark() async throws {
        let model = try await configuredModel()
        await model.createCase(question: "自填情境", cloudConsentID: "cloud")
        let request = PersonalLearningProtocol.state.records().last(where: { $0.0.hasSuffix("/fidelity/cases") })
        XCTAssertEqual(request?.2["question"] as? String, "自填情境")
        XCTAssertNil(request?.2["benchmark_question_id"])
        let before = PersonalLearningProtocol.state.records().count
        await model.createCase(question: "题目已被改写", cloudConsentID: "cloud", benchmarkQuestionID: "bank_01")
        XCTAssertEqual(PersonalLearningProtocol.state.records().count, before)
        XCTAssertNotNil(model.errorMessage)
        await model.createCase(question: "一项重要安排临时变化时，我会先考虑什么？", cloudConsentID: "cloud", benchmarkQuestionID: "bank_01")
        XCTAssertEqual(PersonalLearningProtocol.state.records().last?.2["benchmark_question_id"] as? String, "bank_01")
    }
    func testMalformedAwaitingHumanResponseCannotExposePrediction() throws {
        let record = try JSONDecoder().decode(FidelityCaseRecord.self, from: Data(#"{"case_id":"x","question":"q","status":"awaiting_human","response_type":"SIMULATION","human_answer":null,"locked_answer":"secret prediction","ratings":{},"created_at":"now"}"#.utf8))
        XCTAssertNil(record.visiblePrediction)
    }
    func testInitialServerCaseDecodesEmptyOrLegacyNullRatingsWithoutPrediction() throws {
        for ratings in ["{}", "null"] {
            let data = Data("{\"case_id\":\"case-new\",\"question\":\"q\",\"status\":\"awaiting_human\",\"response_type\":\"SIMULATION\",\"human_answer\":null,\"ratings\":\(ratings),\"created_at\":\"2026-10-14T00:00:00Z\"}".utf8)
            let record = try JSONDecoder().decode(FidelityCaseRecord.self, from: data)
            XCTAssertTrue(record.ratings.isEmpty)
            XCTAssertNil(record.human_answer); XCTAssertNil(record.locked_answer); XCTAssertNil(record.visiblePrediction)
        }
    }
    func testRatingRequiresAllFiveExplicitChoicesAndConfirmedSubmission() async throws {
        let model = try await configuredModel()
        await model.createCase(question: "新的情境？", cloudConsentID: "cloud")
        await model.confirmHumanAnswer("本人回答", confirmed: true)
        await model.submitRatings(["DECISION": "MATCH"], confirmed: true)
        let ratings = Dictionary(uniqueKeysWithValues: personalFidelityDimensions.map { ($0.key, "NOT_OBSERVED") })
        await model.submitRatings(ratings, confirmed: false)
        XCTAssertFalse(PersonalLearningProtocol.state.records().contains { $0.0.hasSuffix("/ratings") })
        await model.submitRatings(ratings, confirmed: true)
        XCTAssertEqual(model.selectedCase?.status, "rated")
        XCTAssertEqual(model.selectedCase?.ratings.count, 5)
        // An already sealed human answer cannot be changed through this model.
        let before = PersonalLearningProtocol.state.records().count
        await model.confirmHumanAnswer("改写", confirmed: true)
        XCTAssertEqual(PersonalLearningProtocol.state.records().count, before)
    }
    func testSourceChangeFailureCannotPretendThatRatingSucceeded() async throws {
        let model = try await configuredModel()
        await model.createCase(question: "新的情境？", cloudConsentID: "cloud")
        await model.confirmHumanAnswer("本人回答", confirmed: true)
        PersonalLearningProtocol.state.rejectRatings = true
        await model.submitRatings(Dictionary(uniqueKeysWithValues: personalFidelityDimensions.map { ($0.key, "MATCH") }), confirmed: true)
        XCTAssertEqual(model.selectedCase?.status, "awaiting_rating")
        XCTAssertNotNil(model.errorMessage); XCTAssertNil(model.fidelity?.measuredRate)
    }
    func testLatePriorOwnerReadCannotPopulateNewOwnerOrTokenScope() async throws {
        PersonalLearningProtocol.state.reset(); PersonalLearningProtocol.state.pauseGET = true
        let model = PersonalLearningModel(); model.configure(pairing: pairing(), client: try client())
        let read = Task { await model.load() }
        while PersonalLearningProtocol.state.records().count < 2 { await Task.yield() }
        model.configure(pairing: pairing(actor: "new-owner", token: "new-token"), client: try client())
        PersonalLearningProtocol.state.releasePaused(); await read.value
        XCTAssertNil(model.learning); XCTAssertNil(model.fidelity)
        XCTAssertNil(model.trainingConsentID); XCTAssertFalse(model.isLoading)
    }
    func testLiveOwnerProviderBlocksRequestsAfterTokenChangeEvenBeforeViewReconfigures() async throws {
        PersonalLearningProtocol.state.reset()
        var active = pairing()
        let model = PersonalLearningModel()
        model.configure(pairing: active, client: try client(), currentOwner: { ReviewScope(active) })
        await model.load()
        active = pairing(token: "new-login-token")
        let before = PersonalLearningProtocol.state.records().count
        await model.enableTraining(acceptedPolicy: "personal-learning-v1")
        XCTAssertFalse(model.canMutate)
        XCTAssertEqual(PersonalLearningProtocol.state.records().count, before)
    }
}

import XCTest
@testable import RememberMe

private final class ReviewProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var server: ReviewTestServer?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let server = Self.server else { return }
        let (code, data, delay) = server.respond(request)
        DispatchQueue.global().asyncAfter(deadline: .now() + delay) { [self] in
            let response = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() { }
}

private final class ReviewTestServer: @unchecked Sendable {
    private let lock = NSLock()
    private var fixture: [String: Any]
    var writeStatus = 200
    var getStatus = 200
    var delay = 0.0
    private(set) var requests: [(String, String, [String: Any]?)] = []
    init(_ fixture: [String: Any]) { self.fixture = fixture }
    func addStaleConfirmedTarget() {
        lock.lock(); defer { lock.unlock() }
        var list = fixture["candidates"] as! [String: Any]
        var rows = list["items"] as! [[String: Any]]
        var target = rows[0]
        target["candidate_id"] = "old_target"; target["status"] = "stale"; target["stored_status"] = "confirmed"
        target["source_version"] = "old-source"; rows.append(target); list["items"] = rows; fixture["candidates"] = list
    }
    func setGardenStory(revision: Int = 1, status: String = "pending", includeSourceMetadata: Bool = false) {
        lock.lock(); defer { lock.unlock() }
        var overview = fixture["overview"] as! [String: Any]
        var records = overview["records"] as! [[String: Any]]
        records[0]["kind"] = "story"; records[0]["facets"] = ["EXPERIENCE"]
        records[0]["revision"] = revision; records[0]["status"] = status
        if includeSourceMetadata {
            records[0]["time_text"] = "下班后"; records[0]["place_text"] = ""
            records[0]["aliases"] = ["我"]; records[0]["same_event"] = true
        }
        overview["records"] = records; fixture["overview"] = overview
    }
    func respond(_ request: URLRequest) -> (Int, Data, Double) {
        lock.lock(); defer { lock.unlock() }
        let path = request.url!.path, method = request.httpMethod ?? "GET"
        let body = try? JSONSerialization.jsonObject(with: readBody(request)) as? [String: Any]
        requests.append((path, method, body))
        if method != "GET" && writeStatus != 200 {
            return (writeStatus, Data(#"{"error_code":"SOURCE_CHANGED","error_message":"依据已变化，请重新核对。"}"#.utf8), delay)
        }
        if method == "GET" && getStatus != 200 { return (getStatus, Data("{}".utf8), delay) }
        let key = path.hasSuffix("/updates") ? "updates" : path.hasSuffix("/jobs") ? "jobs" : path.hasSuffix("/narrative") ? "overview" : "candidates"
        if method == "GET" { return (200, try! JSONSerialization.data(withJSONObject: fixture[key]!), delay) }
        if path.contains("profile-candidates/ios_fixture_candidate/") {
            var list = fixture["candidates"] as! [String: Any]
            var rows = list["items"] as! [[String: Any]]
            rows[0]["status"] = path.hasSuffix("confirm") ? "confirmed" : "rejected"
            list["items"] = rows; fixture["candidates"] = list
        } else if path.contains("/narrative/records/record_style") {
            var view = fixture["overview"] as! [String: Any]
            var rows = view["records"] as! [[String: Any]]
            if method == "PUT", let body {
                for (key, value) in body where key != "revision" { rows[0][key] = value }
                rows[0]["status"] = "pending"
            } else { rows[0]["status"] = path.hasSuffix("confirm") ? "confirmed" : "rejected" }
            rows[0]["revision"] = (rows[0]["revision"] as! Int) + 1
            view["records"] = rows; fixture["overview"] = view
        } else if path.hasSuffix("/narrative/records"), method == "POST", let body {
            var view = fixture["overview"] as! [String: Any]
            var rows = view["records"] as! [[String: Any]]
            var created = rows[0]
            for (key, value) in body { created[key] = value }
            created["id"] = "record_created"; created["status"] = "pending"; created["revision"] = 1
            let sources = view["source_evidence"] as! [[String: Any]]
            let evidenceIDs = body["evidence_ids"] as! [String]
            created["evidence"] = sources.filter { evidenceIDs.contains($0["evidence_id"] as! String) }
            created["source_valid"] = true; created["historical"] = false
            rows.append(created); view["records"] = rows; fixture["overview"] = view
        } else if path.hasSuffix("/style"), let body {
            var view = fixture["overview"] as! [String: Any]
            view["style"] = ["enabled": body["enabled"]!, "revision": (body["revision"] as! Int) + 1]
            fixture["overview"] = view
        }
        return (200, Data("{}".utf8), delay)
    }
    private func readBody(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var result = Data(), buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }; result.append(buffer, count: count)
        }
        return result
    }
}

@MainActor
final class PersonReviewTests: XCTestCase {
    private var server: ReviewTestServer!
    private let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                                  token: "fixture", actorID: "actor", subjectID: "subject", consentID: "consent")
    override func setUpWithError() throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "person-review-contract", withExtension: "json"))
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        server = ReviewTestServer(fixture); ReviewProtocol.server = server
    }
    private func model() -> PersonReviewModel {
        let model = PersonReviewModel { pairing in
            let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [ReviewProtocol.self]
            return try APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token,
                                 session: URLSession(configuration: config))
        }
        model.configure(pairing); return model
    }
    private func withGardenApplication(_ operation: (AppModel, PersonReviewModel) async throws -> Void) async throws {
        let suite = "garden-deletion-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(suite)
        defer { defaults.removePersistentDomain(forName: suite); try? FileManager.default.removeItem(at: root) }
        let review = model()
        let app = AppModel(recordingStore: LocalRecordingStore(root: root), defaults: defaults,
                           pairing: pairing, personReview: review, apiClientFactory: { pairing in
            let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [ReviewProtocol.self]
            return try? APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token,
                                  session: URLSession(configuration: config))
        })
        try await operation(app, review)
    }
    private func gardenEntry(_ record: ReviewRecord) -> GardenEntry {
        GardenEntry(id: "record:" + record.id, title: record.title, text: record.text,
                    label: "AI 整理的故事", date: "录入日期未知", sortDate: "", section: .stories,
                    memories: [], evidence: record.evidence)
    }
    private func gardenMemory(_ id: String = "event_a", content: String = "下班后的一次散步",
                              evidenceID: String = "evidence_a") -> MemoryRecord {
        MemoryRecord(memory_item_id: id, episode_id: "episode_a", content: content, memory_type: "EVENT",
                     domain: nil, source_type: "SUBJECT", confidence: 0.9, model_version: "fixture",
                     recorded_at: "2026-10-14T00:00:00Z", transcript: "下班后我喜欢散步，先安静一会儿再做决定。",
                     stt_model_version: "fixture", capture_source: "IOS_MIC",
                     evidence: [EvidenceRecord(evidence_id: evidenceID, excerpt: "下班后我喜欢散步，先安静一会儿再做决定。",
                                               source_type: "SUBJECT", source_ref: "episode_a", span_start: nil, span_end: nil)])
    }
    private func gardenEventEntry(_ memory: MemoryRecord, additionalMemories: [MemoryRecord] = []) -> GardenEntry {
        GardenEntry(id: "event:" + memory.id, title: memory.content, text: memory.content,
                    label: "AI 整理的事件", date: "录入日期未知", sortDate: memory.recorded_at, section: .stories,
                    memories: [memory] + additionalMemories, evidence: [])
    }
    func testDecodesActualBackendProjectionAndKeepsCounterEvidence() async throws {
        let model = model(); await model.reload()
        XCTAssertTrue(model.isReady)
        let candidate = try XCTUnwrap(model.candidates.first)
        XCTAssertEqual(candidate.counter_evidence_ids, ["evidence_b"])
        XCTAssertTrue(model.sources.contains { $0.id == "evidence_b" && $0.excerpt.contains("赶时间") })
        XCTAssertFalse(model.canUseStyle); XCTAssertFalse(model.style.enabled)
    }
    func testCandidateConfirmationAndRejectionPreserveOriginalSources() async throws {
        let model = model(); await model.reload()
        var invalidations = 0; model.onMutation = { _ in invalidations += 1 }
        let candidate = try XCTUnwrap(model.candidates.first)
        let confirmed = await model.decideCandidate(candidate, confirm: true)
        XCTAssertTrue(confirmed); XCTAssertEqual(model.candidates.first?.status, "confirmed")
        let current = try XCTUnwrap(model.candidates.first)
        let rejected = await model.decideCandidate(current, confirm: false)
        XCTAssertTrue(rejected); XCTAssertEqual(model.candidates.first?.status, "rejected")
        XCTAssertEqual(model.sources.count, 2); XCTAssertEqual(invalidations, 2)
        let writes = server.requests.filter { $0.1 == "POST" }
        XCTAssertEqual(writes.count, 2); XCTAssertNil(writes.first?.2)
        XCTAssertFalse(server.requests.contains { $0.1 == "DELETE" })
    }
    func testRevisionConflictDoesNotConfirmOrAutomaticallyReplay() async throws {
        let model = model(); await model.reload(); server.writeStatus = 409
        var invalidations = 0; model.onMutation = { _ in invalidations += 1 }
        let record = try XCTUnwrap(model.records.first)
        let saved = await model.decideRecord(record, confirm: true)
        XCTAssertFalse(saved); XCTAssertEqual(model.records.first?.status, "pending")
        XCTAssertTrue(model.errorMessage?.contains("依据已变化") == true)
        XCTAssertEqual(invalidations, 1)
        XCTAssertEqual(server.requests.filter { $0.1 == "POST" }.count, 1)
        XCTAssertEqual(server.requests.first { $0.1 == "POST" }?.2?["revision"] as? Int, 1)
    }
    func testLostWriteResponseStillInvalidatesCachedAnswerWithoutReplaying() async throws {
        let model = model(); await model.reload(); server.writeStatus = 503
        var invalidations = 0; model.onMutation = { _ in invalidations += 1 }
        let candidate = try XCTUnwrap(model.candidates.first)
        let saved = await model.decideCandidate(candidate, confirm: true)
        XCTAssertFalse(saved); XCTAssertEqual(invalidations, 1)
        XCTAssertEqual(server.requests.filter { $0.1 == "POST" }.count, 1)
        XCTAssertEqual(model.candidates.first?.status, "pending")
    }
    func testEditRetainsSourceMetadataAndReturnsToPending() async throws {
        let model = model(); await model.reload()
        let row = try XCTUnwrap(model.records.first)
        _ = await model.decideRecord(row, confirm: true)
        var input = ReviewRecordInput(try XCTUnwrap(model.records.first)); input.title = "修改后的标题"
        let saved = await model.saveRecord(input, recordID: row.id)
        XCTAssertTrue(saved); XCTAssertEqual(model.records.first?.status, "pending")
        XCTAssertEqual(model.records.first?.revision, 3); XCTAssertFalse(model.canUseStyle)
        let body = try XCTUnwrap(server.requests.first { $0.1 == "PUT" }?.2)
        XCTAssertEqual(body["revision"] as? Int, 2)
        XCTAssertEqual(body["evidence_ids"] as? [String], row.evidence_ids)
        XCTAssertEqual(body["aliases"] as? [String], row.aliases)
        XCTAssertEqual(body["time_text"] as? String, row.time_text)
        XCTAssertEqual(body["same_event"] as? Bool, row.same_event)
        XCTAssertEqual(body["recipient_label"] as? String, row.recipient_label)
    }
    func testStyleNeedsConfirmedExactOwnWordsAndRevision() async throws {
        let model = model(); await model.reload()
        let denied = await model.setStyle(true); XCTAssertFalse(denied)
        let row = try XCTUnwrap(model.records.first)
        var input = ReviewRecordInput(row); input.text = "模型编造的话"
        let fabricated = await model.saveRecord(input, recordID: row.id); XCTAssertFalse(fabricated)
        XCTAssertFalse(server.requests.contains { $0.1 != "GET" })
        _ = await model.decideRecord(row, confirm: true)
        let enabled = await model.setStyle(true); XCTAssertTrue(enabled)
        XCTAssertTrue(model.style.enabled)
        XCTAssertEqual(server.requests.first { $0.0.hasSuffix("/style") }?.2?["revision"] as? Int, 0)
    }
    func testUnavailableServerLeavesClearFallbackAndNoUsableData() async {
        let model = model(); server.getStatus = 404; await model.reload()
        XCTAssertFalse(model.isReady); XCTAssertTrue(model.sources.isEmpty)
        XCTAssertTrue(model.errorMessage?.contains("尚未提供人物审核接口") == true)
    }
    func testRevokedAccessClearsPreviouslyVisibleSources() async {
        let model = model(); await model.reload(); XCTAssertFalse(model.sources.isEmpty)
        server.getStatus = 403; await model.reload()
        XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.candidates.isEmpty)
        XCTAssertFalse(model.isReady)
    }
    func testLateResponseCannotRestoreDataAfterTokenOrSubjectSwitch() async {
        let model = model(); server.delay = 0.1
        let pending = Task { await model.reload() }
        while !model.isLoading { await Task.yield() }
        var next = pairing
        next = Pairing(baseURL: next.baseURL, fingerprint: next.fingerprint, token: "new-session",
                       actorID: next.actorID, subjectID: "other-subject", consentID: "other-consent")
        model.configure(next); await pending.value
        XCTAssertTrue(model.sources.isEmpty); XCTAssertFalse(model.isReady); XCTAssertFalse(model.isLoading)
    }
    func testCreationOmitsRevisionAndDoesNotAutomaticallyConfirm() async throws {
        let model = model(); await model.reload()
        let input = ReviewRecordInput(kind: "observation", title: "有条件的做法", text: "仅限下班后。",
                                      evidenceIDs: ["evidence_a"], facets: ["PRACTICES"])
        let saved = await model.saveRecord(input); XCTAssertTrue(saved)
        let writes = server.requests.filter { $0.1 == "POST" }
        XCTAssertEqual(writes.count, 1); XCTAssertNil(writes.first?.2?["revision"])
        XCTAssertTrue(writes.first?.0.hasSuffix("/narrative/records") == true)
    }
    func testForeignSourceNeverReachesWriteAPI() async {
        let model = model(); await model.reload()
        let input = ReviewRecordInput(kind: "story", title: "故事", text: "另一人的故事", evidenceIDs: ["foreign"], facets: ["EXPERIENCE"])
        let saved = await model.saveRecord(input); XCTAssertFalse(saved)
        XCTAssertFalse(server.requests.contains { $0.1 != "GET" })
    }
    func testChangedUnderstandingCanRelateToPreviouslyConfirmedStaleTarget() async throws {
        server.addStaleConfirmedTarget()
        let model = model(); await model.reload()
        let candidate = try XCTUnwrap(model.candidates.first { $0.id == "ios_fixture_candidate" })
        let target = try XCTUnwrap(model.candidates.first { $0.id == "old_target" })
        XCTAssertTrue(target.canBeRelationTarget)
        let missingTime = await model.proposeRelation(candidate: candidate, targetID: target.id, action: "CHANGE", reason: "情境改变了", time: "")
        XCTAssertFalse(missingTime)
        var invalidations = 0; model.onMutation = { _ in invalidations += 1 }
        let proposed = await model.proposeRelation(candidate: candidate, targetID: target.id, action: "CHANGE", reason: "情境改变了", time: "毕业后")
        XCTAssertTrue(proposed); XCTAssertEqual(invalidations, 0)
        let body = try XCTUnwrap(server.requests.first { $0.1 == "POST" }?.2)
        XCTAssertEqual(body["action"] as? String, "CHANGE"); XCTAssertEqual(body["time_text"] as? String, "毕业后")
        XCTAssertEqual(body["target_candidate_id"] as? String, target.id)
    }
    func testSameEventGroupingKeepsExplicitMembershipPending() async {
        let model = model(); await model.reload()
        var input = ReviewRecordInput(kind: "story", title: "同一件事的两次讲述", text: "本人核对这些讲述属于同一故事。",
                                      evidenceIDs: ["evidence_a", "evidence_b"], facets: ["EXPERIENCE"])
        input.same_event = true
        let saved = await model.saveRecord(input); XCTAssertTrue(saved)
        let writes = server.requests.filter { $0.1 == "POST" }
        XCTAssertEqual(writes.count, 1)
        XCTAssertEqual(writes.first?.2?["same_event"] as? Bool, true)
        XCTAssertEqual(writes.first?.2?["evidence_ids"] as? [String], ["evidence_a", "evidence_b"])
    }
    func testScopeIncludesServiceActorSubjectAndSession() {
        var other = pairing; other.connectionKind = "ecs"
        XCTAssertEqual(ReviewScope(pairing), ReviewScope(other))
        let changedToken = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: "other-token",
                                   actorID: pairing.actorID, subjectID: pairing.subjectID, consentID: pairing.consentID)
        XCTAssertNotEqual(ReviewScope(pairing), ReviewScope(changedToken))
    }
    func testReviewInvalidatesAppAnswerAndStoredPointerOnlyForCurrentScope() throws {
        let suite = "review-invalidation-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(suite)
        defer { defaults.removePersistentDomain(forName: suite); try? FileManager.default.removeItem(at: root) }
        let review = model()
        let app = AppModel(recordingStore: LocalRecordingStore(root: root), defaults: defaults, pairing: pairing, personReview: review)
        let answer = try JSONDecoder().decode(TwinAnswerRecord.self, from: Data(#"{"answer_id":"answer","question":"问题","answer":"旧回答","response_type":"ORIGINAL","evidence":[],"model_version":"fixture","person_model_version":1,"stale":false}"#.utf8))
        let key = "last-twin-answer-\(pairing.baseURL)-\(pairing.actorID)-\(pairing.subjectID)"
        app.receiveTwinAnswer(answer); defaults.set("answer", forKey: key)
        _ = app.twinChat.begin("继续说", conversationMode: true)
        let foreign = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: "other", actorID: "other", subjectID: "other", consentID: "other")
        review.onMutation?(ReviewScope(foreign)); XCTAssertNotNil(app.twinAnswer)
        review.onMutation?(ReviewScope(pairing)); XCTAssertNil(app.twinAnswer); XCTAssertNil(defaults.string(forKey: key))
        XCTAssertEqual(app.twinChat.turns.map(\.question), ["问题", "继续说"])
        XCTAssertTrue(app.twinChat.turns[0].invalidated)
        XCTAssertNotNil(app.twinChat.turns[1].failure)
        XCTAssertEqual(app.twinChat.turns[1].previousAnswerID, "answer")
    }
    func testGardenStoryDeletionRejectsExactRevisionWithoutConfirmingOrDeletingOriginal() async throws {
        server.setGardenStory(revision: 7)
        try await withGardenApplication { app, review in
            await review.reload()
            let record = try XCTUnwrap(review.records.first)
            let initialRevision = app.memoryContentRevision
            app.episodes = [EpisodeRecord(episode_id: "episode_a", status: "ready", source: "IOS_MIC",
                recorded_at: "2026-10-14T00:00:00Z", duration_ms: 10000, transcript: record.text,
                stt_backend: "fixture", stt_model_version: "fixture", model_version: "fixture", error_code: nil)]

            let deleted = await app.deleteGardenEntry(gardenEntry(record), record: record, scope: ReviewScope(pairing))

            XCTAssertTrue(deleted); XCTAssertFalse(app.isBusy)
            XCTAssertEqual(review.records.first?.status, "rejected")
            XCTAssertNotEqual(app.memoryContentRevision, initialRevision)
            XCTAssertEqual(app.episodes.map(\.id), ["episode_a"])
            XCTAssertEqual(app.episodes.first?.transcript, record.text)
            let writes = server.requests.filter { $0.1 != "GET" }
            XCTAssertEqual(writes.count, 1)
            XCTAssertEqual(writes.first?.0, "/api/v1/workbench/subjects/subject/narrative/records/record_style/reject")
            XCTAssertEqual(writes.first?.1, "POST")
            XCTAssertEqual(writes.first?.2?["revision"] as? Int, 7)
        }
    }
    func testGardenStoryDeletionDoesNotPostWhenServerRevisionChanged() async throws {
        server.setGardenStory()
        try await withGardenApplication { app, review in
            await review.reload()
            let original = try XCTUnwrap(review.records.first)
            server.setGardenStory(revision: 2)

            let deleted = await app.deleteGardenEntry(gardenEntry(original), record: original, scope: ReviewScope(pairing))

            XCTAssertFalse(deleted); XCTAssertFalse(app.isBusy)
            XCTAssertEqual(review.records.first?.revision, 2)
            XCTAssertEqual(review.records.first?.status, "pending")
            XCTAssertNotNil(app.errorMessage)
            XCTAssertFalse(server.requests.contains { $0.1 != "GET" })
        }
    }
    func testFailedGardenStoryRejectionReturnsFalseAndNeverReplaysWrite() async throws {
        server.setGardenStory()
        try await withGardenApplication { app, review in
            await review.reload()
            let record = try XCTUnwrap(review.records.first)
            let initialRevision = app.memoryContentRevision
            server.writeStatus = 503

            let deleted = await app.deleteGardenEntry(gardenEntry(record), record: record, scope: ReviewScope(pairing))

            XCTAssertFalse(deleted); XCTAssertFalse(app.isBusy)
            XCTAssertEqual(review.records.first?.status, "pending")
            XCTAssertNotNil(app.errorMessage)
            XCTAssertNotEqual(app.memoryContentRevision, initialRevision)
            let writes = server.requests.filter { $0.1 != "GET" }
            XCTAssertEqual(writes.count, 1)
            XCTAssertTrue(writes.first?.0.hasSuffix("/record_style/reject") == true)
            XCTAssertEqual(writes.first?.2?["revision"] as? Int, record.revision)
        }
    }
    func testGardenStoryDeletionFromForeignScopeMakesNoRequests() async throws {
        server.setGardenStory()
        try await withGardenApplication { app, review in
            await review.reload()
            let record = try XCTUnwrap(review.records.first)
            let requestCount = server.requests.count
            let foreign = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: "foreign-token",
                                  actorID: "other", subjectID: "other", consentID: "other")

            let deleted = await app.deleteGardenEntry(gardenEntry(record), record: record, scope: ReviewScope(foreign))

            XCTAssertFalse(deleted); XCTAssertFalse(app.isBusy)
            XCTAssertEqual(server.requests.count, requestCount)
            XCTAssertEqual(review.records.first?.status, "pending")
        }
    }
    func testGardenStoryEditPreservesSourceMetadataAndReturnsToPendingWithoutChangingOriginal() async throws {
        server.setGardenStory(revision: 4, status: "confirmed", includeSourceMetadata: true)
        try await withGardenApplication { app, review in
            await review.reload()
            let record = try XCTUnwrap(review.records.first)
            let source = gardenMemory()
            app.memories = [source]
            let originalRevision = app.memoryContentRevision

            let saved = await app.saveGardenEntry(gardenEntry(record), record: record, title: "  那次散步  ",
                                                 text: "我在散步时想清楚了接下来要做的事。", scope: ReviewScope(pairing))

            XCTAssertTrue(saved); XCTAssertFalse(app.isBusy)
            XCTAssertEqual(review.records.first?.status, "pending")
            XCTAssertEqual(review.records.first?.title, "那次散步")
            XCTAssertNotEqual(app.memoryContentRevision, originalRevision)
            XCTAssertEqual(app.memories.first?.content, source.content)
            let writes = server.requests.filter { $0.1 != "GET" }
            XCTAssertEqual(writes.count, 1)
            XCTAssertEqual(writes.first?.1, "PUT")
            XCTAssertEqual(writes.first?.0, "/api/v1/workbench/subjects/subject/narrative/records/record_style")
            let body = try XCTUnwrap(writes.first?.2)
            XCTAssertEqual(body["revision"] as? Int, 4)
            XCTAssertEqual(body["text"] as? String, "我在散步时想清楚了接下来要做的事。")
            XCTAssertEqual(body["evidence_ids"] as? [String], record.evidence_ids)
            XCTAssertEqual(body["facets"] as? [String], record.facets)
            XCTAssertEqual(body["time_text"] as? String, record.time_text)
            XCTAssertEqual(body["place_text"] as? String, record.place_text)
            XCTAssertEqual(body["aliases"] as? [String], record.aliases)
            XCTAssertEqual(body["same_event"] as? Bool, record.same_event)
            XCTAssertEqual(body["recipient_label"] as? String, record.recipient_label)
        }
    }
    func testGardenEventEditCreatesPendingStoryUsingOnlyItsOwnEvidence() async throws {
        try await withGardenApplication { app, review in
            let source = gardenMemory()
            let unrelated = gardenMemory("event_b", content: "同一录音里的另一件事", evidenceID: "evidence_b")
            app.memories = [source, unrelated]
            let originalRevision = app.memoryContentRevision

            let saved = await app.saveGardenEntry(gardenEventEntry(source, additionalMemories: [unrelated]), record: nil,
                                                 title: "散步之后", text: "那次散步让我重新考虑了自己的决定。",
                                                 scope: ReviewScope(pairing))

            XCTAssertTrue(saved); XCTAssertFalse(app.isBusy)
            XCTAssertEqual(app.memories.map(\.id), [source.id, unrelated.id])
            XCTAssertEqual(app.memories.first?.content, source.content)
            XCTAssertEqual(app.memoryContentRevision, originalRevision)
            let writes = server.requests.filter { $0.1 != "GET" }
            XCTAssertEqual(writes.count, 1)
            XCTAssertEqual(writes.first?.1, "POST")
            XCTAssertEqual(writes.first?.0, "/api/v1/workbench/subjects/subject/narrative/records")
            let body = try XCTUnwrap(writes.first?.2)
            XCTAssertEqual(body["kind"] as? String, "story")
            XCTAssertEqual(body["evidence_ids"] as? [String], ["evidence_a"])
            XCTAssertEqual(body["facets"] as? [String], ["EXPERIENCE"])
            XCTAssertEqual(body["time_text"] as? String, "")
            XCTAssertEqual(body["place_text"] as? String, "")
            XCTAssertNil(body["revision"])
            XCTAssertEqual(review.records.first(where: { $0.id == "record_created" })?.status, "pending")
        }
    }
    func testGardenStoryEditWithStaleRevisionMakesNoWrites() async throws {
        server.setGardenStory()
        try await withGardenApplication { app, review in
            await review.reload()
            let original = try XCTUnwrap(review.records.first)
            server.setGardenStory(revision: 2)

            let saved = await app.saveGardenEntry(gardenEntry(original), record: original, title: "新标题", text: "新内容",
                                                 scope: ReviewScope(pairing))

            XCTAssertFalse(saved); XCTAssertFalse(app.isBusy)
            XCTAssertNotNil(app.errorMessage)
            XCTAssertFalse(server.requests.contains { $0.1 != "GET" })
        }
    }
    func testMissingOrChangedGardenEventCannotCreateStory() async throws {
        let opened = gardenMemory()
        for current in [[], [gardenMemory(content: "内容已经修订")], [gardenMemory(evidenceID: "evidence_b")]] {
            try await withGardenApplication { app, _ in
                app.memories = current

                let saved = await app.saveGardenEntry(gardenEventEntry(opened), record: nil, title: "新标题", text: "新内容",
                                                     scope: ReviewScope(pairing))

                XCTAssertFalse(saved); XCTAssertFalse(app.isBusy)
                XCTAssertNotNil(app.errorMessage)
                XCTAssertFalse(server.requests.contains { $0.1 != "GET" })
            }
        }
    }
    func testMissingOrChangedGardenEventCannotDeleteCurrentSource() async throws {
        let opened = gardenMemory()
        for current in [[], [gardenMemory(content: "内容已经修订")], [gardenMemory(evidenceID: "evidence_b")]] {
            try await withGardenApplication { app, _ in
                app.memories = current

                let deleted = await app.deleteGardenEntry(gardenEventEntry(opened), record: nil, scope: ReviewScope(pairing))

                XCTAssertFalse(deleted); XCTAssertFalse(app.isBusy)
                XCTAssertNotNil(app.errorMessage)
                XCTAssertEqual(app.memories.map(\.id), current.map(\.id))
                XCTAssertEqual(app.memories.map(\.content), current.map(\.content))
                XCTAssertTrue(server.requests.isEmpty)
            }
        }
    }
    func testGardenEditFromForeignScopeMakesNoRequests() async throws {
        try await withGardenApplication { app, _ in
            let source = gardenMemory(); app.memories = [source]
            let foreign = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: "foreign-token",
                                  actorID: "other", subjectID: "other", consentID: "other")

            let saved = await app.saveGardenEntry(gardenEventEntry(source), record: nil, title: "新标题", text: "新内容",
                                                 scope: ReviewScope(foreign))

            XCTAssertFalse(saved); XCTAssertFalse(app.isBusy)
            XCTAssertTrue(server.requests.isEmpty)
        }
    }
    func testCancelledGardenEditMakesNoRequests() async throws {
        try await withGardenApplication { app, _ in
            let source = gardenMemory(); app.memories = [source]
            let pending = Task {
                await app.saveGardenEntry(gardenEventEntry(source), record: nil, title: "新标题", text: "新内容",
                                          scope: ReviewScope(pairing))
            }
            pending.cancel()

            let saved = await pending.value

            XCTAssertFalse(saved); XCTAssertFalse(app.isBusy)
            XCTAssertTrue(server.requests.isEmpty)
        }
    }
}

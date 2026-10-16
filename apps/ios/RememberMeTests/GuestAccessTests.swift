import XCTest
@testable import RememberMe

private final class GuestRequestProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var delay: ((URLRequest) -> TimeInterval)?
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (Int, Data))?
    nonisolated(unsafe) static var deferHandling: ((URLRequest, @escaping @Sendable () -> Void) -> Bool)?
    nonisolated(unsafe) static var deferDelivery: ((URLRequest, @escaping @Sendable () -> Void) -> Bool)?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        if Self.deferHandling?(request, { [self] in respond() }) == true { return }
        respond()
    }
    private func respond() {
        do {
            let (code, data) = try Self.handler!(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"])!
            let deliver: @Sendable () -> Void = { [self] in
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
            }
            if Self.deferDelivery?(request, deliver) == true { return }
            let delay = Self.delay?(request) ?? 0
            if delay > 0 { DispatchQueue.global().asyncAfter(deadline: .now() + delay, execute: deliver) }
            else { deliver() }
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    static func body(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var data = Data(), buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(contentsOf: buffer.prefix(count))
        }
        return data
    }
    override func stopLoading() { }
}

private final class GuestRequestGate: @unchecked Sendable {
    private let lock = NSLock()
    private var pending: [@Sendable () -> Void] = []
    private let matches: (URLRequest) -> Bool
    let held: XCTestExpectation
    init(_ description: String, matches: @escaping (URLRequest) -> Bool) {
        held = XCTestExpectation(description: description); self.matches = matches
    }
    func intercept(_ request: URLRequest, resume: @escaping @Sendable () -> Void) -> Bool {
        guard matches(request) else { return false }
        lock.lock(); pending.append(resume); lock.unlock()
        held.fulfill(); return true
    }
    func release() {
        lock.lock(); let work = pending; pending = []; lock.unlock()
        for resume in work { resume() }
    }
}
private final class GuestMicrophoneFixture: GuestQuestionRecording {
    var starts = 0
    var discards = 0
    func start() throws { starts += 1 }
    func finish() -> Data { Data([1, 2]) }
    func discard() { discards += 1 }
}
private final class GuestPlayerFixture: GuestAudioPlaying {
    var stops = 0
    func stop() { stops += 1 }
}

@MainActor
final class GuestAccessTests: XCTestCase {
    private let sessionJSON = #"{"session_token":"guest-only-bearer","session_id":"visit","subject_id":"subject","subject_label":"爷爷","expires_at":"2026-10-16T12:00:00Z","revision":1,"personal_voice_available":false,"cloud_asr_policy":null,"speech_notice":"仅本次提问","default_voice_available":true,"spoken_question_available":true}"#
    private let gardenJSON = #"{"revision":1,"items":[{"episode_id":"open-episode","recorded_at":"2026-10-16","duration_ms":1000,"transcript":"整段已核对原话","supplement":null,"memories":["开放的故事"]}]}"#
    private let answerJSON = #"{"answer_id":"guest-answer","question":"故事呢","answer":"这是开放的故事。","response_type":"ORIGINAL","evidence":[],"model_version":"fixture","person_model_version":0,"stale":false}"#
    private func client(token: String?) throws -> APIClient {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [GuestRequestProtocol.self]
        return try APIClient(baseURL: "https://127.0.0.1:8000", fingerprint: String(repeating: "a", count: 64),
                             token: token, session: URLSession(configuration: config))
    }
    private func guest(microphone: GuestMicrophoneFixture? = nil,
                       playAudio: ((Data) throws -> any GuestAudioPlaying)? = nil,
                       recordPermission: @escaping @MainActor () async -> Bool = { false }) -> GuestAccessModel {
        let model = GuestAccessModel(apiFactory: { [self] _, _, token in try client(token: token) },
            microphoneFactory: microphone.map { fixture in { fixture as any GuestQuestionRecording } }, playAudio: playAudio, recordPermission: recordPermission)
        model.configure(entry: Pairing(baseURL: "https://127.0.0.1:8000", fingerprint: String(repeating: "a", count: 64),
            token: "entry-only", actorID: "guest-entry", subjectID: "subject", consentID: "", spaceName: "爷爷"))
        return model
    }
    func testIndependentGuestBearerAndContinuousQuestionsNeverUseOwnerEndpoints() async throws {
        let session = sessionJSON, garden = gardenJSON, answer = answerJSON
        nonisolated(unsafe) var questions = 0
        GuestRequestProtocol.handler = { request in
            XCTAssertTrue(request.url!.path.hasPrefix("/api/v1/guest/"))
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-store")
            if request.url!.path.hasSuffix("/sessions") {
                XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
                let body = try JSONSerialization.jsonObject(with: GuestRequestProtocol.body(request)) as! [String: String]
                XCTAssertEqual(body, ["entry_token": "entry-only"])
                return (200, Data(session.utf8))
            }
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer guest-only-bearer")
            if request.url!.path.hasSuffix("/memories") { return (200, Data(garden.utf8)) }
            if request.url!.path.hasSuffix("/questions") {
                let body = try JSONSerialization.jsonObject(with: GuestRequestProtocol.body(request)) as! [String: String]
                XCTAssertEqual(body["previous_answer_id"], questions == 0 ? nil : "guest-answer")
                XCTAssertNil(body["subject_id"]); XCTAssertNil(body["cloud_consent_id"])
                questions += 1
                return (200, Data(answer.utf8))
            }
            return (200, Data(session.utf8))
        }
        let model = guest(); await model.begin()
        XCTAssertEqual(model.sources.first?.transcript, "整段已核对原话")
        model.question = "故事呢"; await model.ask()
        model.question = "然后呢"; await model.ask()
        XCTAssertEqual(questions, 2); XCTAssertEqual(model.chat.turns.count, 2)
    }
    func testRevocationClearsVisibleSourcesConversationAndSession() async {
        let session = sessionJSON, garden = gardenJSON, answer = answerJSON
        nonisolated(unsafe) var revoked = false
        GuestRequestProtocol.handler = { request in
            if revoked { return (403, Data(#"{"detail":"访问已撤销"}"#.utf8)) }
            if request.url!.path.hasSuffix("/memories") { return (200, Data(garden.utf8)) }
            if request.url!.path.hasSuffix("/questions") { return (200, Data(answer.utf8)) }
            return (200, Data(session.utf8))
        }
        let model = guest(); await model.begin(); model.question = "故事呢"; await model.ask()
        XCTAssertEqual(model.chat.turns.count, 1)
        revoked = true; await model.validate()
        XCTAssertNil(model.session); XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.chat.turns.isEmpty)
        XCTAssertFalse(model.isPlaying)
    }
    func testLateGardenResponseCannotRestoreContentAfterAuthorityCheckFails() async {
        let session = sessionJSON, garden = gardenJSON
        nonisolated(unsafe) var delayed = false
        nonisolated(unsafe) var failAuthority = false
        let started = expectation(description: "Delayed garden request started")
        GuestRequestProtocol.delay = { request in request.url!.path.hasSuffix("/memories") && delayed ? 0.25 : 0 }
        defer { GuestRequestProtocol.delay = nil }
        GuestRequestProtocol.handler = { request in
            if request.url!.path.hasSuffix("/memories") {
                if delayed { started.fulfill() }
                return (200, Data(garden.utf8))
            }
            if failAuthority { throw URLError(.notConnectedToInternet) }
            return (200, Data(session.utf8))
        }
        let model = guest(); await model.begin()
        XCTAssertEqual(model.sources.count, 1)
        delayed = true
        let pending = Task { await model.loadGarden() }
        await fulfillment(of: [started], timeout: 2)
        failAuthority = true; await model.validate()
        XCTAssertTrue(model.sources.isEmpty)
        await pending.value
        XCTAssertTrue(model.sources.isEmpty)
    }
    func testBackgroundStopCancelsPendingMicrophonePermission() async {
        let session = sessionJSON, garden = gardenJSON
        GuestRequestProtocol.handler = { request in
            (200, Data((request.url!.path.hasSuffix("/memories") ? garden : session).utf8))
        }
        var permission: CheckedContinuation<Bool, Never>?
        let model = guest(recordPermission: { await withCheckedContinuation { permission = $0 } })
        await model.begin()
        let start = Task { await model.startQuestionRecording() }
        while permission == nil { await Task.yield() }
        model.stopTransientAudio()
        permission?.resume(returning: true)
        await start.value
        XCTAssertFalse(model.isRecording)
    }
    func testEndingVisitClearsMemoryAndUsesOnlyGuestSessionDelete() async {
        let session = sessionJSON, garden = gardenJSON
        nonisolated(unsafe) var deleted = false
        GuestRequestProtocol.handler = { request in
            if request.httpMethod == "DELETE" {
                XCTAssertEqual(request.url!.path, "/api/v1/guest/session")
                XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer guest-only-bearer")
                deleted = true; return (200, Data("{\"ended\":true}".utf8))
            }
            return (200, Data((request.url!.path.hasSuffix("/memories") ? garden : session).utf8))
        }
        let model = guest(); await model.begin(); model.question = "临时草稿"; await model.end()
        XCTAssertTrue(deleted); XCTAssertNil(model.session); XCTAssertTrue(model.question.isEmpty)
        XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.chat.turns.isEmpty)
    }
    func testRestartRetainsGuestAndBlocksOwnerDeepLinksConnectionRecordingAndLocalFiles() throws {
        let name = "GuestAccessTests-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        defaults.set(true, forKey: "guest-access-mode")
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        defer { try? FileManager.default.removeItem(at: root) }
        let owner = Pairing(baseURL: "https://127.0.0.1:8000", fingerprint: String(repeating: "a", count: 64),
            token: "owner-secret", actorID: "owner", subjectID: "subject", consentID: "consent")
        let model = AppModel(recordingStore: LocalRecordingStore(root: root), defaults: defaults, pairing: owner)
        XCTAssertTrue(model.isGuestMode); XCTAssertNil(model.pairing); XCTAssertNil(model.dialogueClient())
        XCTAssertFalse(model.applyConnection(owner, persist: false)); XCTAssertFalse(model.prepareNewRecording())
        model.importPairingLink(URL(string: "rememberme://pair?server=https://other&code=123&sha256=abc")!)
        XCTAssertFalse(model.showConnection); XCTAssertTrue(model.visibleLocalRecordings.isEmpty)
        XCTAssertTrue(model.guestAccess.chat.turns.isEmpty)
    }
    func testWrongPasswordOrDifferentActorCannotUpgradeGuestMode() async throws {
        let name = "GuestReauth-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        defer {
            defaults.removePersistentDomain(forName: name)
            try? FileManager.default.removeItem(at: root)
            PairingStore.clear(account: "guest-owner-recovery")
        }
        defaults.set(true, forKey: "guest-access-mode")
        let owner = Pairing(baseURL: "https://127.0.0.1:8000", fingerprint: String(repeating: "a", count: 64),
            token: "isolated-original-owner", actorID: "original-owner", subjectID: "subject", consentID: "", connectionKind: "cloudbase")
        try PairingStore.save(owner, account: "guest-owner-recovery")
        let model = AppModel(recordingStore: LocalRecordingStore(root: root), defaults: defaults, pairing: owner,
            apiClientFactory: { [self] in try? client(token: $0.token) })
        GuestRequestProtocol.handler = { request in
            XCTAssertEqual(request.url!.path, "/api/v1/accounts/reauth")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer isolated-original-owner")
            return (401, Data(#"{"detail":"密码不正确"}"#.utf8))
        }
        await model.returnToOwner(password: "wrong")
        XCTAssertTrue(model.isGuestMode); XCTAssertNil(model.pairing); XCTAssertNotNil(model.errorMessage)
        GuestRequestProtocol.handler = { request in
            XCTAssertEqual(request.url!.path, "/api/v1/accounts/login")
            return (200, Data(#"{"actor_token":"other-user-token","actor_id":"other-user","display_name":"其他人"}"#.utf8))
        }
        await model.returnToOwner(password: "valid-other-password", username: "another-user")
        XCTAssertTrue(model.isGuestMode); XCTAssertNil(model.pairing)
        XCTAssertTrue(defaults.bool(forKey: "guest-access-mode"))
    }
    func testCorrectPasswordRestoresOnlyOriginalActorAndOwnedSubject() async throws {
        let name = "GuestReauthSuccess-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        defer {
            defaults.removePersistentDomain(forName: name); try? FileManager.default.removeItem(at: root)
            PairingStore.clear(account: "guest-owner-recovery"); PairingStore.clear()
        }
        defaults.set(true, forKey: "guest-access-mode")
        let owner = Pairing(baseURL: "https://127.0.0.1:8000", fingerprint: String(repeating: "a", count: 64),
            token: "isolated-original-owner", actorID: "original-owner", subjectID: "subject", consentID: "", connectionKind: "cloudbase")
        try PairingStore.save(owner, account: "guest-owner-recovery")
        let model = AppModel(recordingStore: LocalRecordingStore(root: root), defaults: defaults, pairing: owner,
            apiClientFactory: { [self] in try? client(token: $0.token) })
        GuestRequestProtocol.handler = { request in
            switch request.url!.path {
            case "/api/v1/accounts/reauth":
                return (200, Data(#"{"actor_token":"reauthenticated-owner","actor_id":"original-owner","display_name":"本人"}"#.utf8))
            case "/api/v1/workbench/spaces":
                XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer reauthenticated-owner")
                return (200, Data(#"{"actor_id":"original-owner","display_name":"本人","items":[{"subject_id":"subject","display_name":"本人空间","role":"owner"}]}"#.utf8))
            case "/api/v1/workbench/capabilities":
                return (200, Data(#"{"stt":"fixture","stt_processing":"local","stt_configured":false,"ai_available":true}"#.utf8))
            default: return (200, Data(#"{"items":[]}"#.utf8))
            }
        }
        await model.returnToOwner(password: "correct")
        XCTAssertFalse(model.isGuestMode); XCTAssertEqual(model.pairing?.actorID, "original-owner")
        XCTAssertEqual(model.pairing?.subjectID, "subject"); XCTAssertEqual(model.pairing?.token, "reauthenticated-owner")
        XCTAssertFalse(defaults.bool(forKey: "guest-access-mode"))
        XCTAssertTrue(model.guestAccess.chat.turns.isEmpty)
    }
    func testBackendVersionCompatibilityIncludesCurrentContract() {
        XCTAssertTrue(AppModel.supportsBackendVersion("0.7.0")); XCTAssertTrue(AppModel.supportsBackendVersion("0.12.0"))
        XCTAssertFalse(AppModel.supportsBackendVersion("0.6.0")); XCTAssertFalse(AppModel.supportsBackendVersion("1.0.0"))
        XCTAssertFalse(AppModel.supportsBackendVersion("oops")); XCTAssertFalse(AppModel.supportsBackendVersion("0.x.12.0"))
    }
    func testCrashLeftoverQuestionAudioIsRemovedOnInitialization() throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("guest-question-\(UUID().uuidString).m4a")
        try Data([1, 2, 3]).write(to: file)
        _ = GuestAccessModel()
        XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    }
    private func scopedSession(_ version: String, recipient: String? = nil, expires: Date? = nil) throws -> Data {
        var value = try JSONSerialization.jsonObject(with: Data(sessionJSON.utf8)) as! [String: Any]
        value["scope_version"] = version
        if let recipient {
            let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            value["entrustment"] = ["recipient_label": recipient, "expires_at": formatter.string(from: expires ?? Date().addingTimeInterval(600))]
        }
        return try JSONSerialization.data(withJSONObject: value)
    }
    private func scopedGarden(_ version: String, id: String = "open-episode") throws -> Data {
        var value = try JSONSerialization.jsonObject(with: Data(gardenJSON.utf8)) as! [String: Any]
        value["scope_version"] = version
        var item = (value["items"] as! [[String: Any]])[0]; item["episode_id"] = id; value["items"] = [item]
        return try JSONSerialization.data(withJSONObject: value)
    }
    private func controlAnswer(success: Bool) throws -> Data {
        try JSONSerialization.data(withJSONObject: ["answer_id": "control", "question": success ? "[暗号已核验]" : "[暗号未核验]",
            "answer": success ? "给小雨的专属记忆已打开。" : "暗号未核验。", "response_type": "CONVERSATION", "evidence": [],
            "model_version": "guest-entrustment-control", "person_model_version": 0, "stale": false])
    }
    func testNaturalSecretIsNeverAppendedBeforeReplyAndControlClearsPreviousScope() async throws {
        let publicSession = try scopedSession("public"), privateSession = try scopedSession("private", recipient: "小雨")
        let publicGarden = try scopedGarden("public"), privateGarden = try scopedGarden("private", id: "private-episode")
        let answer = Data(answerJSON.utf8), control = try controlAnswer(success: true)
        let secret = "那年雨夜你把蓝围巾藏进饼干盒里"
        nonisolated(unsafe) var unlocked = false
        nonisolated(unsafe) var askingSecret = false
        let sent = expectation(description: "Private secret sent only to dedicated guest question endpoint")
        GuestRequestProtocol.delay = { request in request.url!.path.hasSuffix("/questions") && askingSecret ? 0.2 : 0 }
        defer { GuestRequestProtocol.delay = nil }
        GuestRequestProtocol.handler = { request in
            if request.url!.path.hasSuffix("/memories") { return (200, unlocked ? privateGarden : publicGarden) }
            if request.url!.path.hasSuffix("/questions") {
                if askingSecret {
                    let body = try JSONSerialization.jsonObject(with: GuestRequestProtocol.body(request)) as! [String: Any]
                    XCTAssertEqual(body["question"] as? String, secret)
                    XCTAssertEqual(body["entrustment_attempt"] as? Bool, true)
                    unlocked = true; sent.fulfill(); return (200, control)
                }
                return (200, answer)
            }
            return (200, unlocked ? privateSession : publicSession)
        }
        let model = guest(); await model.begin(); model.question = "故事呢"; await model.ask()
        XCTAssertEqual(model.chat.turns.count, 1)
        askingSecret = true; model.entrustmentAttempt = true; model.question = secret
        let pending = Task { await model.ask() }
        await fulfillment(of: [sent], timeout: 2)
        XCTAssertFalse(model.chat.turns.contains { $0.question.contains(secret) }); XCTAssertTrue(model.question.isEmpty)
        await pending.value
        XCTAssertTrue(model.chat.turns.isEmpty)
        XCTAssertEqual(model.sources.map(\.id), ["private-episode"])
        XCTAssertEqual(model.entrustedRecipient, "小雨"); XCTAssertFalse(model.entrustmentAttempt)
        XCTAssertEqual(model.notice, "给小雨的专属记忆已打开。")
    }
    func testFailedExplicitSecretUsesSanitizedControlQuestionAndNoRawError() async throws {
        let session = try scopedSession("public"), garden = try scopedGarden("public"), control = try controlAnswer(success: false)
        GuestRequestProtocol.handler = { request in
            if request.url!.path.hasSuffix("/memories") { return (200, garden) }
            if request.url!.path.hasSuffix("/questions") { return (200, control) }
            return (200, session)
        }
        let model = guest(); await model.begin(); model.entrustmentAttempt = true; model.question = "输入错了的私密细节也不可进入聊天"
        await model.ask()
        XCTAssertTrue(model.chat.turns.isEmpty)
        XCTAssertNil(model.entrustedRecipient)
        XCTAssertFalse(model.notice?.contains("输入错了") ?? true)
        GuestRequestProtocol.handler = { request in
            if request.url!.path.hasSuffix("/questions") { return (422, Data(#"{"detail":"不要显示这段错误里的私密暗号"}"#.utf8)) }
            if request.url!.path.hasSuffix("/memories") { return (200, garden) }
            return (200, session)
        }
        model.entrustmentAttempt = true; model.question = "不要显示这段错误里的私密暗号"; await model.ask()
        XCTAssertTrue(model.chat.turns.isEmpty); XCTAssertTrue(model.question.isEmpty)
        XCTAssertFalse(model.notice?.contains("私密暗号") ?? true)
    }
    func testScopeVersionChangeClearsAnswersEvenWhenPublicRevisionIsUnchanged() async throws {
        let firstSession = try scopedSession("first", recipient: "小雨"), secondSession = try scopedSession("second", recipient: "阿明")
        let firstGarden = try scopedGarden("first", id: "first-private"), secondGarden = try scopedGarden("second", id: "second-private")
        let answer = Data(answerJSON.utf8)
        nonisolated(unsafe) var switched = false
        GuestRequestProtocol.handler = { request in
            if request.url!.path.hasSuffix("/memories") { return (200, switched ? secondGarden : firstGarden) }
            if request.url!.path.hasSuffix("/questions") { return (200, answer) }
            return (200, switched ? secondSession : firstSession)
        }
        let model = guest(); await model.begin(); model.question = "故事呢"; await model.ask()
        XCTAssertEqual(model.chat.turns.count, 1)
        switched = true; await model.validate()
        XCTAssertTrue(model.chat.turns.isEmpty); XCTAssertEqual(model.sources.map(\.id), ["second-private"])
        XCTAssertEqual(model.entrustedRecipient, "阿明"); XCTAssertFalse(model.isPlaying)
    }
    func testExplicitSecretCannotBeShownAsOrdinaryAnswerByOlderService() async throws {
        let session = try scopedSession("public"), garden = try scopedGarden("public")
        let raw = "不能让旧服务把这句私密暗号直接显示"
        var value = try JSONSerialization.jsonObject(with: Data(answerJSON.utf8)) as! [String: Any]
        value["question"] = raw; value["answer"] = raw
        let unsafeReply = try JSONSerialization.data(withJSONObject: value)
        GuestRequestProtocol.handler = { request in
            if request.url!.path.hasSuffix("/memories") { return (200, garden) }
            if request.url!.path.hasSuffix("/questions") { return (200, unsafeReply) }
            return (200, session)
        }
        let model = guest(); await model.begin(); model.entrustmentAttempt = true; model.question = raw; await model.ask()
        XCTAssertTrue(model.chat.turns.isEmpty); XCTAssertTrue(model.question.isEmpty)
        XCTAssertFalse(model.notice?.contains(raw) ?? true)
    }
    func testQuestionAfterSuccessfulSecretHasNoControlAnswerParent() async throws {
        let publicSession = try scopedSession("public"), privateSession = try scopedSession("private", recipient: "小雨")
        let publicGarden = try scopedGarden("public"), privateGarden = try scopedGarden("private", id: "private-episode")
        let control = try controlAnswer(success: true), answer = Data(answerJSON.utf8)
        nonisolated(unsafe) var count = 0
        GuestRequestProtocol.handler = { request in
            if request.url!.path.hasSuffix("/questions") {
                count += 1
                let body = try JSONSerialization.jsonObject(with: GuestRequestProtocol.body(request)) as! [String: Any]
                XCTAssertNil(body["previous_answer_id"])
                return (200, count == 1 ? control : answer)
            }
            if request.url!.path.hasSuffix("/memories") { return (200, count > 0 ? privateGarden : publicGarden) }
            return (200, count > 0 ? privateSession : publicSession)
        }
        let model = guest(); await model.begin(); model.question = "那年雨夜你把蓝围巾藏进饼干盒里"; await model.ask()
        XCTAssertTrue(model.chat.turns.isEmpty)
        model.question = "故事呢"; await model.ask()
        XCTAssertEqual(count, 2); XCTAssertEqual(model.chat.turns.count, 1)
        XCTAssertEqual(model.chat.turns.first?.answer?.id, "guest-answer")
    }
    func testLocalExpiryHidesContentBeforeDelayedAuthorityResponseReturns() async throws {
        let session = try scopedSession("private", recipient: "小雨", expires: Date().addingTimeInterval(0.25))
        let garden = try scopedGarden("private", id: "private-episode")
        GuestRequestProtocol.handler = { request in (200, request.url!.path.hasSuffix("/memories") ? garden : session) }
        GuestRequestProtocol.delay = { request in request.url!.path == "/api/v1/guest/session" ? 0.5 : 0 }
        defer { GuestRequestProtocol.delay = nil }
        let model = guest(); await model.begin(); XCTAssertEqual(model.sources.count, 1)
        try await Task.sleep(for: .milliseconds(350))
        XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.chat.turns.isEmpty)
        XCTAssertNil(model.entrustedRecipient); XCTAssertFalse(model.isPlaying)
        await model.end()
    }
    func testLockClearsPrivateContentImmediatelyAndReloadsPublicScope() async throws {
        let privateSession = try scopedSession("private", recipient: "小雨"), publicSession = try scopedSession("public")
        let privateGarden = try scopedGarden("private", id: "private-episode"), publicGarden = try scopedGarden("public")
        nonisolated(unsafe) var locked = false
        let deletion = expectation(description: "Explicit guest lock request")
        GuestRequestProtocol.delay = { request in request.httpMethod == "DELETE" && request.url!.path.hasSuffix("/entrustment") ? 0.2 : 0 }
        defer { GuestRequestProtocol.delay = nil }
        GuestRequestProtocol.handler = { request in
            if request.httpMethod == "DELETE" {
                XCTAssertEqual(request.url!.path, "/api/v1/guest/entrustment")
                locked = true; deletion.fulfill(); return (200, Data("{}".utf8))
            }
            if request.url!.path.hasSuffix("/memories") { return (200, locked ? publicGarden : privateGarden) }
            return (200, locked ? publicSession : privateSession)
        }
        let model = guest(); await model.begin(); XCTAssertEqual(model.sources.map(\.id), ["private-episode"])
        let pending = Task { await model.lockEntrustment() }
        await fulfillment(of: [deletion], timeout: 2)
        XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.chat.turns.isEmpty); XCTAssertFalse(model.isPlaying)
        await pending.value
        XCTAssertEqual(model.sources.map(\.id), ["open-episode"]); XCTAssertNil(model.entrustedRecipient)
    }

    func testLocalLockBlocksPollingAndInteractionBeforeDeleteIsProcessed() async throws {
        let privateSession = try scopedSession("private", recipient: "小雨"), publicSession = try scopedSession("public")
        let privateGarden = try scopedGarden("private", id: "private-episode"), publicGarden = try scopedGarden("public")
        let answer = Data(answerJSON.utf8), microphone = GuestMicrophoneFixture()
        nonisolated(unsafe) var locked = false
        nonisolated(unsafe) var requests = 0
        var plays = 0
        let delete = GuestRequestGate("DELETE has not reached the server") { $0.httpMethod == "DELETE" }
        GuestRequestProtocol.handler = { request in
            requests += 1
            if request.httpMethod == "DELETE" { locked = true; return (200, Data("{}".utf8)) }
            if request.url!.path.hasSuffix("/questions") { return (200, answer) }
            if request.url!.path.hasSuffix("/memories") { return (200, locked ? publicGarden : privateGarden) }
            return (200, locked ? publicSession : privateSession)
        }
        GuestRequestProtocol.deferHandling = { delete.intercept($0, resume: $1) }
        defer { GuestRequestProtocol.deferHandling = nil; delete.release() }
        let model = guest(microphone: microphone, playAudio: { _ in plays += 1; return GuestPlayerFixture() }, recordPermission: { true })
        await model.begin(); model.question = "故事呢"; await model.ask()
        let pending = Task { await model.lockEntrustment() }
        await fulfillment(of: [delete.held], timeout: 2)
        XCTAssertFalse(locked); XCTAssertTrue(model.isLocking); XCTAssertTrue(model.isBusy)
        XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.chat.turns.isEmpty); XCTAssertNil(model.entrustedRecipient)
        let before = requests
        await model.validate(); await model.loadGarden()
        model.question = "不可在锁定中发送"; await model.ask(); model.question = ""
        await model.playSource("private-episode"); await model.playAnswer("guest-answer", personal: false)
        await model.startQuestionRecording()
        XCTAssertEqual(requests, before); XCTAssertEqual(microphone.starts, 0); XCTAssertEqual(plays, 0)
        XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.chat.turns.isEmpty)
        delete.release(); await pending.value
        XCTAssertTrue(locked); XCTAssertFalse(model.isLocking); XCTAssertFalse(model.isBusy)
        XCTAssertEqual(model.sources.map(\.id), ["open-episode"]); XCTAssertNil(model.entrustedRecipient)
    }

    func testLockFailureOrUnconfirmedPublicScopeEndsLocalSession() async throws {
        let session = try scopedSession("private", recipient: "小雨"), garden = try scopedGarden("private", id: "private-episode")
        for failDelete in [true, false] {
            GuestRequestProtocol.handler = { request in
                if request.httpMethod == "DELETE" {
                    if failDelete { throw URLError(.notConnectedToInternet) }
                    return (200, Data("{}".utf8))
                }
                return (200, request.url!.path.hasSuffix("/memories") ? garden : session)
            }
            let model = guest(); await model.begin(); await model.lockEntrustment()
            XCTAssertNil(model.session); XCTAssertTrue(model.sources.isEmpty); XCTAssertTrue(model.chat.turns.isEmpty)
            XCTAssertFalse(model.isLocking); XCTAssertFalse(model.isBusy); XCTAssertFalse(model.isPlaying)
            await model.validate(); await model.loadGarden()
            XCTAssertTrue(model.sources.isEmpty)
        }
    }

    func testPreLockAuthorityGardenAnswersAndAudioCannotRestoreOldScope() async throws {
        let privateSession = try scopedSession("private", recipient: "小雨"), publicSession = try scopedSession("public")
        let privateGarden = try scopedGarden("private", id: "private-episode"), publicGarden = try scopedGarden("public")
        let answer = Data(answerJSON.utf8)
        let spoken = try JSONSerialization.data(withJSONObject: ["text": "晚到语音", "answer": JSONSerialization.jsonObject(with: answer)])
        for operation in ["authority", "garden", "question", "spoken", "source", "answer"] {
            nonisolated(unsafe) var locked = false
            var plays = 0
            GuestRequestProtocol.handler = { request in
                if request.httpMethod == "DELETE" { locked = true; return (200, Data("{}".utf8)) }
                let path = request.url!.path
                if path.hasSuffix("/questions") { return (200, answer) }
                if path.hasSuffix("/spoken-question") { return (200, spoken) }
                if path.hasSuffix("/audio") || path.contains("/speech/") { return (200, Data([1, 2])) }
                if path.hasSuffix("/memories") { return (200, locked ? publicGarden : privateGarden) }
                return (200, locked ? publicSession : privateSession)
            }
            let model = guest(microphone: GuestMicrophoneFixture(), playAudio: { _ in plays += 1; return GuestPlayerFixture() }, recordPermission: { true })
            await model.begin(); model.question = "故事呢"; await model.ask()
            let old = GuestRequestGate("Old \(operation) response is already generated") { request in
                let path = request.url!.path
                switch operation {
                case "authority": return path == "/api/v1/guest/session"
                case "garden": return path.hasSuffix("/memories")
                case "question": return path.hasSuffix("/questions")
                case "spoken": return path.hasSuffix("/spoken-question")
                case "source": return path.hasSuffix("/audio")
                default: return path.contains("/speech/")
                }
            }
            GuestRequestProtocol.deferDelivery = { old.intercept($0, resume: $1) }
            let pending = Task {
                switch operation {
                case "authority": await model.validate()
                case "garden": await model.loadGarden()
                case "question": model.question = "晚到问题"; await model.ask()
                case "spoken": await model.startQuestionRecording(); await model.finishQuestionRecording()
                case "source": await model.playSource("private-episode")
                default: await model.playAnswer("guest-answer", personal: false)
                }
            }
            await fulfillment(of: [old.held], timeout: 2)
            GuestRequestProtocol.deferDelivery = nil
            await model.lockEntrustment()
            XCTAssertEqual(model.sources.map(\.id), ["open-episode"], operation)
            old.release(); await pending.value
            XCTAssertEqual(model.sources.map(\.id), ["open-episode"], operation)
            XCTAssertTrue(model.chat.turns.isEmpty, operation); XCTAssertNil(model.entrustedRecipient, operation)
            XCTAssertEqual(plays, 0, operation); XCTAssertFalse(model.isPlaying, operation)
        }
    }

    func testRecordingReservesAudioBeforePermissionAndBlocksSourceAndAnswerPlayback() async {
        let session = Data(sessionJSON.utf8), garden = Data(gardenJSON.utf8), answer = Data(answerJSON.utf8)
        nonisolated(unsafe) var downloads = 0
        GuestRequestProtocol.handler = { request in
            let path = request.url!.path
            if path.hasSuffix("/audio") || path.contains("/speech/") { downloads += 1; return (200, Data([1, 2])) }
            if path.hasSuffix("/questions") { return (200, answer) }
            return (200, path.hasSuffix("/memories") ? garden : session)
        }
        let microphone = GuestMicrophoneFixture(), player = GuestPlayerFixture()
        var plays = 0
        var permission: CheckedContinuation<Bool, Never>?
        let model = guest(microphone: microphone, playAudio: { _ in plays += 1; return player },
            recordPermission: { await withCheckedContinuation { permission = $0 } })
        await model.begin(); model.question = "故事呢"; await model.ask(); await model.playSource("open-episode")
        XCTAssertTrue(model.isPlaying); XCTAssertEqual(plays, 1)
        let pending = Task { await model.startQuestionRecording() }
        while permission == nil { await Task.yield() }
        XCTAssertTrue(model.isStartingRecording); XCTAssertFalse(model.isPlaying); XCTAssertEqual(player.stops, 1)
        let before = downloads
        await model.playSource("open-episode"); await model.playAnswer("guest-answer", personal: false)
        await model.startQuestionRecording()
        XCTAssertEqual(downloads, before); XCTAssertEqual(plays, 1); XCTAssertEqual(microphone.starts, 0)
        permission?.resume(returning: true); await pending.value
        XCTAssertTrue(model.isRecording); XCTAssertFalse(model.isStartingRecording); XCTAssertEqual(microphone.starts, 1)
        await model.playSource("open-episode"); await model.playAnswer("guest-answer", personal: false)
        XCTAssertEqual(downloads, before); XCTAssertEqual(plays, 1); XCTAssertTrue(model.isRecording)
        model.stopTransientAudio(); XCTAssertEqual(microphone.discards, 1)
    }

    func testRecordingCancelsPlaybackWaitingAtEveryNetworkBoundary() async {
        let session = Data(sessionJSON.utf8), garden = Data(gardenJSON.utf8), answer = Data(answerJSON.utf8)
        GuestRequestProtocol.handler = { request in
            let path = request.url!.path
            if path.hasSuffix("/audio") || path.contains("/speech/") { return (200, Data([1, 2])) }
            if path.hasSuffix("/questions") { return (200, answer) }
            return (200, path.hasSuffix("/memories") ? garden : session)
        }
        for playAnswer in [false, true] {
            for boundary in ["initial-authority", "download", "final-authority"] {
                let microphone = GuestMicrophoneFixture()
                var plays = 0
                let model = guest(microphone: microphone, playAudio: { _ in plays += 1; return GuestPlayerFixture() }, recordPermission: { true })
                await model.begin(); model.question = "故事呢"; await model.ask()
                nonisolated(unsafe) var authorityCalls = 0
                let gate = GuestRequestGate("Playback paused at \(boundary)") { request in
                    let path = request.url!.path
                    if path == "/api/v1/guest/session" {
                        authorityCalls += 1
                        return boundary == "initial-authority" || boundary == "final-authority" && authorityCalls == 2
                    }
                    return boundary == "download" && (path.hasSuffix("/audio") || path.contains("/speech/"))
                }
                GuestRequestProtocol.deferDelivery = { gate.intercept($0, resume: $1) }
                let pending = Task {
                    if playAnswer { await model.playAnswer("guest-answer", personal: false) }
                    else { await model.playSource("open-episode") }
                }
                await fulfillment(of: [gate.held], timeout: 2)
                GuestRequestProtocol.deferDelivery = nil
                await model.startQuestionRecording()
                XCTAssertTrue(model.isRecording); XCTAssertEqual(microphone.starts, 1)
                gate.release(); await pending.value
                XCTAssertEqual(plays, 0, boundary); XCTAssertFalse(model.isPlaying, boundary); XCTAssertTrue(model.isRecording, boundary)
                model.stopTransientAudio()
            }
        }
    }

    func testLockCancelsPendingMicrophonePermission() async throws {
        let privateSession = try scopedSession("private", recipient: "小雨"), publicSession = try scopedSession("public")
        let privateGarden = try scopedGarden("private", id: "private-episode"), publicGarden = try scopedGarden("public")
        nonisolated(unsafe) var locked = false
        GuestRequestProtocol.handler = { request in
            if request.httpMethod == "DELETE" { locked = true; return (200, Data("{}".utf8)) }
            return (200, request.url!.path.hasSuffix("/memories") ? (locked ? publicGarden : privateGarden) : (locked ? publicSession : privateSession))
        }
        let microphone = GuestMicrophoneFixture()
        var permission: CheckedContinuation<Bool, Never>?
        let model = guest(microphone: microphone, recordPermission: { await withCheckedContinuation { permission = $0 } })
        await model.begin()
        let pending = Task { await model.startQuestionRecording() }
        while permission == nil { await Task.yield() }
        await model.lockEntrustment(); permission?.resume(returning: true); await pending.value
        XCTAssertEqual(microphone.starts, 0); XCTAssertFalse(model.isRecording); XCTAssertFalse(model.isStartingRecording)
        XCTAssertEqual(model.sources.map(\.id), ["open-episode"])
    }

    func testSecretRequestNotYetHandledCannotReopenScopeAfterLock() async throws {
        let privateSession = try scopedSession("private", recipient: "小雨"), publicSession = try scopedSession("public")
        let privateGarden = try scopedGarden("private", id: "private-episode"), publicGarden = try scopedGarden("public")
        let control = try controlAnswer(success: true)
        nonisolated(unsafe) var scope = "private"
        nonisolated(unsafe) var unlocks = 0
        nonisolated(unsafe) var staleRequests = 0
        let question = GuestRequestGate("Correct secret request has not reached authentication") { $0.url!.path.hasSuffix("/questions") }
        GuestRequestProtocol.handler = { request in
            let path = request.url!.path
            if request.httpMethod == "DELETE" || path.hasSuffix("/questions") {
                guard request.value(forHTTPHeaderField: "X-Guest-Scope-Version") == scope else {
                    staleRequests += 1
                    return (409, Data(#"{"detail":"开放范围已变化"}"#.utf8))
                }
                if request.httpMethod == "DELETE" { scope = "public"; return (200, Data("{}".utf8)) }
                unlocks += 1; scope = "private"; return (200, control)
            }
            if path == "/api/v1/guest/session" { XCTAssertNil(request.value(forHTTPHeaderField: "X-Guest-Scope-Version")) }
            return (200, path.hasSuffix("/memories") ? (scope == "private" ? privateGarden : publicGarden) : (scope == "private" ? privateSession : publicSession))
        }
        let model = guest(); await model.begin()
        GuestRequestProtocol.deferHandling = { question.intercept($0, resume: $1) }
        defer { GuestRequestProtocol.deferHandling = nil; question.release() }
        model.question = "那年雨夜你把蓝围巾藏进饼干盒里"
        let pending = Task { await model.ask() }
        await fulfillment(of: [question.held], timeout: 2)
        await model.lockEntrustment()
        XCTAssertEqual(scope, "public"); XCTAssertNil(model.entrustedRecipient)
        question.release(); await pending.value; await model.validate()
        XCTAssertEqual(staleRequests, 1); XCTAssertEqual(unlocks, 0); XCTAssertEqual(scope, "public")
        XCTAssertEqual(model.sources.map(\.id), ["open-episode"]); XCTAssertTrue(model.chat.turns.isEmpty)
        XCTAssertNil(model.entrustedRecipient)
    }

    func testQuestionDoesNotUpgradeItsStartingScopeAfterInitialValidation() async throws {
        let first = try scopedSession("first", recipient: "小雨"), next = try scopedSession("next")
        let firstGarden = try scopedGarden("first", id: "private-episode"), nextGarden = try scopedGarden("next")
        nonisolated(unsafe) var changed = false
        nonisolated(unsafe) var questions = 0
        GuestRequestProtocol.handler = { request in
            let path = request.url!.path
            if path.hasSuffix("/questions") { questions += 1; return (500, Data()) }
            return (200, path.hasSuffix("/memories") ? (changed ? nextGarden : firstGarden) : (changed ? next : first))
        }
        let model = guest(); await model.begin(); changed = true
        model.question = "不要把旧范围的问题升级发送到新范围"; await model.ask()
        XCTAssertEqual(questions, 0); XCTAssertTrue(model.chat.turns.isEmpty)
        XCTAssertEqual(model.sources.map(\.id), ["open-episode"])
    }

    func testSpokenQuestionBindsCurrentScopeBeforeSendingAudio() async throws {
        let session = try scopedSession("private", recipient: "小雨"), garden = try scopedGarden("private", id: "private-episode")
        let answer = try JSONSerialization.jsonObject(with: Data(answerJSON.utf8))
        let spoken = try JSONSerialization.data(withJSONObject: ["text": "故事呢", "answer": answer])
        nonisolated(unsafe) var questions = 0
        GuestRequestProtocol.handler = { request in
            let path = request.url!.path
            if path.hasSuffix("/spoken-question") {
                questions += 1
                XCTAssertEqual(request.value(forHTTPHeaderField: "X-Guest-Scope-Version"), "private")
                return (200, spoken)
            }
            return (200, path.hasSuffix("/memories") ? garden : session)
        }
        let model = guest(microphone: GuestMicrophoneFixture(), recordPermission: { true })
        await model.begin(); await model.startQuestionRecording(); await model.finishQuestionRecording()
        XCTAssertEqual(questions, 1); XCTAssertEqual(model.chat.turns.count, 1)
    }
}

import XCTest
import LiveKit
@testable import RememberMe

private enum PreparationReply {
    case response(Int, Data)
    case failure(URLError.Code)
    case hold
}

/// Each test owns a hostname and response queue, including requests held across state changes.
private final class PreparationFixture: @unchecked Sendable {
    let host = UUID().uuidString.lowercased() + ".fixture.invalid"
    private let lock = NSLock()
    private var replies: [String: [PreparationReply]] = [:]
    private var held: [String: [PreparationProtocol]] = [:]
    private var counts: [String: Int] = [:]
    var defaultCapabilities = PreparationFixture.capabilities()

    static func capabilities(policy: String = "fixture-policy", available: Bool = true,
                             profile: String = "profile", transport: String? = nil) -> Data {
        var value: [String: Any] = ["available": available, "default_voice_available": true,
            "policy": policy, "notice": "fixture notice", "profile": profileValue(profile),
            "natural_voice_preparation": true]
        if let transport { value["transport"] = transport }
        return try! JSONSerialization.data(withJSONObject: value)
    }
    static func profileValue(_ id: String) -> [String: Any] {
        ["ready": true, "profile_id": id, "status": "ready", "model_version": "fixture", "voice_consent_id": "voice"]
    }
    static func profile(_ id: String) -> Data { try! JSONSerialization.data(withJSONObject: profileValue(id)) }
    func enqueue(_ endpoint: String, _ reply: PreparationReply) {
        lock.lock(); defer { lock.unlock() }
        replies[endpoint, default: []].append(reply)
    }
    func count(_ endpoint: String) -> Int {
        lock.lock(); defer { lock.unlock() }; return counts[endpoint, default: 0]
    }
    func takeHeld(_ endpoint: String) -> PreparationProtocol? {
        lock.lock(); defer { lock.unlock() }
        guard held[endpoint]?.isEmpty == false else { return nil }
        return held[endpoint]?.removeFirst()
    }
    func respond(to request: PreparationProtocol) {
        let path = request.request.url!.path
        let endpoint = path.hasSuffix("/capabilities") ? "capabilities" : path.hasSuffix("/profile") ? "profile" : "call"
        lock.lock()
        counts[endpoint, default: 0] += 1
        let reply: PreparationReply
        if replies[endpoint]?.isEmpty == false { reply = replies[endpoint]!.removeFirst() }
        else if endpoint == "capabilities" { reply = .response(200, defaultCapabilities) }
        else if endpoint == "profile" { reply = .response(200, Self.profile("profile")) }
        else if path.hasSuffix("/calls"), request.request.httpMethod == "POST" {
            let ticket: [String: Any] = ["call_id": "vc_fixture", "room": "vc_fixture",
                "participant_identity": "user_vc_fixture", "livekit_url": "wss://fixture.invalid",
                "token": "fixture", "voice_mode": "personal",
                "expires_at": ISO8601DateFormatter().string(from: Date().addingTimeInterval(600))]
            reply = .response(200, try! JSONSerialization.data(withJSONObject: ticket))
        } else { reply = .response(200, Data("{}".utf8)) }
        if case .hold = reply { held[endpoint, default: []].append(request) }
        lock.unlock()
        if case .hold = reply { return }
        request.complete(reply)
    }
}

private final class PreparationProtocol: URLProtocol, @unchecked Sendable {
    private static let registryLock = NSLock()
    nonisolated(unsafe) private static var fixtures: [String: PreparationFixture] = [:]
    private let completionLock = NSLock()
    private var completed = false
    static func register(_ fixture: PreparationFixture) {
        registryLock.lock(); defer { registryLock.unlock() }; fixtures[fixture.host] = fixture
    }
    static func unregister(_ fixture: PreparationFixture) {
        registryLock.lock(); defer { registryLock.unlock() }; fixtures[fixture.host] = nil
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.registryLock.lock()
        let fixture = Self.fixtures[request.url!.host!]
        Self.registryLock.unlock()
        guard let fixture else { complete(.failure(.cannotFindHost)); return }
        fixture.respond(to: self)
    }
    func complete(_ reply: PreparationReply) {
        completionLock.lock()
        guard !completed else { completionLock.unlock(); return }
        completed = true
        completionLock.unlock()
        switch reply {
        case let .response(status, data):
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status,
                httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        case let .failure(code): client?.urlProtocol(self, didFailWithError: URLError(code))
        case .hold: preconditionFailure("Held responses must be completed with a result")
        }
    }
    override func stopLoading() { completionLock.lock(); completed = true; completionLock.unlock() }
}

@MainActor
final class VoicePreparationTests: XCTestCase {
    private func connection(_ fixture: PreparationFixture, owner: String = "owner") throws -> (Pairing, APIClient) {
        PreparationProtocol.register(fixture)
        addTeardownBlock { PreparationProtocol.unregister(fixture) }
        let url = "https://" + fixture.host
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PreparationProtocol.self]
        let pairing = Pairing(baseURL: url, fingerprint: String(repeating: "a", count: 64),
                              token: "token-" + owner, actorID: owner, subjectID: "subject-" + owner, consentID: "recording")
        let api = try APIClient(baseURL: url, fingerprint: pairing.fingerprint, token: pairing.token,
                                session: URLSession(configuration: configuration))
        return (pairing, api)
    }
    private func prepared(_ fixture: PreparationFixture) async throws -> TwinVoiceCallModel {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        let (pairing, api) = try connection(fixture)
        call.configure(pairing, client: api); await call.prepare()
        XCTAssertEqual(call.capabilities?.available, true)
        return call
    }
    private func held(_ endpoint: String, in fixture: PreparationFixture) async throws -> PreparationProtocol {
        for _ in 0..<200 {
            if let result = fixture.takeHeld(endpoint) { return result }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTFail("Expected an in-flight " + endpoint + " request")
        throw URLError(.timedOut)
    }
    private func start(_ call: TwinVoiceCallModel) async {
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        call.receive(VoiceCallEvent(type: "state", turn_id: nil, text: nil, state: "listening", answer: nil, message: nil))
        XCTAssertEqual(call.state, .listening)
    }
    private func assertReady(_ call: TwinVoiceCallModel, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(call.capabilities?.available, true, file: file, line: line)
        XCTAssertEqual(call.profile?.profile_id, "profile", file: file, line: line)
        XCTAssertNil(call.notice, file: file, line: line)
    }

    func testAlreadyCancelledPrepareDoesNotRequestOrClearReadiness() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        let count = fixture.count("capabilities")
        await Task {
            withUnsafeCurrentTask { $0?.cancel() }
            await call.prepare()
        }.value
        XCTAssertEqual(fixture.count("capabilities"), count)
        assertReady(call); XCTAssertFalse(call.isPreparing)
    }

    func testCancellingInFlightPreparePreservesReadinessWithoutFailureNotice() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("capabilities", .hold)
        let pending = Task { await call.prepare() }
        _ = try await held("capabilities", in: fixture)
        pending.cancel(); await pending.value
        assertReady(call); XCTAssertFalse(call.isPreparing)
    }

    func testURLSessionCancelledPrepareIsSilentEvenWhenTaskIsNotCancelled() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("capabilities", .failure(.cancelled))
        await call.prepare()
        assertReady(call); XCTAssertFalse(call.isPreparing)
    }

    func testCancellingProfileRefreshPreservesReadiness() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("profile", .hold)
        let pending = Task { await call.refreshProfile() }
        _ = try await held("profile", in: fixture)
        pending.cancel(); await pending.value
        assertReady(call)
    }

    func testURLSessionCancelledProfileRefreshIsSilent() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("profile", .failure(.cancelled))
        await call.refreshProfile()
        assertReady(call)
    }

    func testDomesticProfileRefreshUpdatesBothProfilesWithoutRequestingCapabilities() async throws {
        let fixture = PreparationFixture()
        fixture.defaultCapabilities = PreparationFixture.capabilities(transport: "volcengine")
        let call = try await prepared(fixture)
        let capabilitiesCount = fixture.count("capabilities")
        fixture.enqueue("profile", .response(200, PreparationFixture.profile("refreshed")))
        await call.refreshProfile()
        XCTAssertEqual(fixture.count("capabilities"), capabilitiesCount)
        XCTAssertEqual(call.profile?.profile_id, "refreshed")
        XCTAssertEqual(call.capabilities?.profile.profile_id, "refreshed")
        XCTAssertEqual(call.capabilities?.available, true)
        XCTAssertEqual(call.capabilities?.transport, "volcengine")
        XCTAssertEqual(call.capabilities?.policy, "fixture-policy")
        XCTAssertNil(call.notice)
    }

    func testDomesticProfileRefreshPreservesExistingHangupReason() async throws {
        let fixture = PreparationFixture()
        fixture.defaultCapabilities = PreparationFixture.capabilities(transport: "volcengine")
        let call = try await prepared(fixture)
        await call.end(message: "语音连接已中断，请重新开始。")
        let capabilitiesCount = fixture.count("capabilities")
        fixture.enqueue("profile", .response(200, PreparationFixture.profile("refreshed")))
        await call.refreshProfile()
        XCTAssertEqual(fixture.count("capabilities"), capabilitiesCount)
        XCTAssertEqual(call.profile?.profile_id, "refreshed")
        XCTAssertEqual(call.capabilities?.profile.profile_id, "refreshed")
        XCTAssertEqual(call.state, .failed)
        XCTAssertEqual(call.notice, "语音连接已中断，请重新开始。")
    }

    func testConcurrentProfileRefreshesShareOneRequestAndAllowLaterRefresh() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("profile", .hold)
        let pending = Task { await call.refreshProfile() }
        let first = try await held("profile", in: fixture)
        defer { first.complete(.failure(.cancelled)) }
        await call.refreshProfile()
        XCTAssertEqual(fixture.count("profile"), 1)
        first.complete(.response(200, PreparationFixture.profile("first")))
        await pending.value
        XCTAssertEqual(call.profile?.profile_id, "first")
        XCTAssertEqual(call.capabilities?.profile.profile_id, "first")
        fixture.enqueue("profile", .response(200, PreparationFixture.profile("second")))
        await call.refreshProfile()
        XCTAssertEqual(fixture.count("profile"), 2)
        XCTAssertEqual(call.profile?.profile_id, "second")
        XCTAssertEqual(call.capabilities?.profile.profile_id, "second")
        XCTAssertEqual(fixture.count("capabilities"), 1)
        XCTAssertNil(call.notice)
    }

    func testActiveCallSkipsPreparationAndProfileRequests() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        await start(call)
        let capabilities = fixture.count("capabilities"), profile = fixture.count("profile")
        await call.prepare(); await call.refreshProfile()
        XCTAssertEqual(fixture.count("capabilities"), capabilities)
        XCTAssertEqual(fixture.count("profile"), profile)
        XCTAssertEqual(call.state, .listening); assertReady(call)
        await call.end()
    }

    func testPriorPreparationSuccessCannotOverwriteActiveCall() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("capabilities", .hold)
        let pending = Task { await call.prepare() }
        let old = try await held("capabilities", in: fixture)
        await start(call)
        old.complete(.response(200, PreparationFixture.capabilities(policy: "old", available: false, profile: "old")))
        await pending.value
        XCTAssertEqual(call.state, .listening); assertReady(call)
        XCTAssertEqual(call.capabilities?.policy, "fixture-policy")
        await call.end()
    }

    func testPriorPreparationFailureCannotOverwriteActiveCall() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("capabilities", .hold)
        let pending = Task { await call.prepare() }
        let old = try await held("capabilities", in: fixture)
        await start(call)
        old.complete(.failure(.timedOut)); await pending.value
        XCTAssertEqual(call.state, .listening); assertReady(call)
        await call.end()
    }

    func testPriorProfileRefreshCannotOverwriteActiveCall() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("profile", .hold)
        let pending = Task { await call.refreshProfile() }
        let old = try await held("profile", in: fixture)
        await start(call)
        old.complete(.response(200, PreparationFixture.profile("old"))); await pending.value
        XCTAssertEqual(call.state, .listening); assertReady(call)
        await call.end()
    }

    func testChangingOwnerAllowsNewPreparationAndDiscardsOldCompletion() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("capabilities", .hold)
        let pending = Task { await call.prepare() }
        let old = try await held("capabilities", in: fixture)
        defer { old.complete(.failure(.cancelled)) }
        let (pairing, api) = try connection(fixture, owner: "new-owner")
        call.configure(pairing, client: api)
        fixture.enqueue("capabilities", .response(200, PreparationFixture.capabilities(profile: "new-owner")))
        await call.prepare()
        old.complete(.response(200, PreparationFixture.capabilities(profile: "old-owner")))
        await pending.value
        XCTAssertEqual(call.profile?.profile_id, "new-owner"); XCTAssertNil(call.notice)
        XCTAssertFalse(call.isPreparing)
    }

    func testResetToSameOwnerDiscardsOldResponseWithoutClearingNewPreparationFlag() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("capabilities", .hold)
        let previous = Task { await call.prepare() }
        let old = try await held("capabilities", in: fixture)
        defer { old.complete(.failure(.cancelled)) }
        call.resetConnection()
        let (pairing, api) = try connection(fixture)
        call.configure(pairing, client: api)
        fixture.enqueue("capabilities", .hold)
        let pending = Task { await call.prepare() }
        let fresh = try await held("capabilities", in: fixture)
        defer { fresh.complete(.failure(.cancelled)) }
        old.complete(.response(200, PreparationFixture.capabilities(profile: "old")))
        await previous.value
        XCTAssertNil(call.profile); XCTAssertTrue(call.isPreparing)
        fresh.complete(.response(200, PreparationFixture.capabilities(profile: "fresh")))
        await pending.value
        XCTAssertEqual(call.profile?.profile_id, "fresh"); XCTAssertFalse(call.isPreparing)
    }

    func testLatePreparationCannotReplaceHangupReasonAfterCallEnds() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        fixture.enqueue("capabilities", .hold)
        let pending = Task { await call.prepare() }
        let old = try await held("capabilities", in: fixture)
        await start(call); await call.end(message: "语音连接已中断，请重新开始。")
        old.complete(.failure(.timedOut)); await pending.value
        XCTAssertEqual(call.state, .failed)
        XCTAssertEqual(call.notice, "语音连接已中断，请重新开始。")
    }

    func testFreshSuccessfulAndFailedRefreshesPreserveActualHangupReason() async throws {
        let fixture = PreparationFixture(), call = try await prepared(fixture)
        await start(call); await call.end(message: "耳机已断开，请重新开始。")
        await call.prepare(); await call.refreshProfile()
        XCTAssertEqual(call.notice, "耳机已断开，请重新开始。")
        fixture.enqueue("capabilities", .failure(.timedOut)); await call.prepare()
        fixture.enqueue("profile", .response(503, Data("{}".utf8))); await call.refreshProfile()
        XCTAssertEqual(call.notice, "耳机已断开，请重新开始。")
        XCTAssertEqual(call.state, .failed)
    }

    func testUnavailableCapabilityIsDistinctFromLoginTimeoutAndServiceFailures() async throws {
        let cases: [(PreparationReply, String)] = [
            (.response(401, Data("{}".utf8)), "登录已失效，请重新登录后再开始通话。"),
            (.failure(.timedOut), "检查通话服务超时，请稍后重试。"),
            (.response(503, Data("{}".utf8)), "通话服务暂时异常（503），请稍后重试。"),
            (.response(404, Data("{}".utf8)), "当前服务未提供此通话接口，请检查服务版本或空间权限。"),
            (.response(200, PreparationFixture.capabilities(available: false)), "此服务尚未启用实时声音通话，文字孪生仍可使用。")
        ]
        for (reply, expected) in cases {
            let fixture = PreparationFixture(), call = try await prepared(fixture)
            fixture.enqueue("capabilities", reply); await call.prepare()
            XCTAssertEqual(call.notice, expected)
            XCTAssertFalse(call.isActive); XCTAssertFalse(call.isPreparing)
        }
    }
}

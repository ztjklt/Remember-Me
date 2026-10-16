import XCTest
import LiveKit
import AVFoundation
@testable import RememberMe

private final class VoiceProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var calls = 0
    nonisolated(unsafe) static var holdConsents = false
    nonisolated(unsafe) static var heldConsent: VoiceProtocol?
    nonisolated(unsafe) static var tickets = false
    nonisolated(unsafe) static var policy = "fixture-policy"
    nonisolated(unsafe) static var ready = true
    nonisolated(unsafe) static var defaultVoice = false
    nonisolated(unsafe) static var ticketMode = "personal"
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path
        let status: Int
        let body: String
        if path.hasSuffix("/consents"), Self.holdConsents { Self.heldConsent = self; return }
        if path.hasSuffix("/capabilities") {
            status = 200
            body = "{\"available\":true,\"default_voice_available\":\(Self.defaultVoice),\"policy\":\"\(Self.policy)\",\"notice\":\"fixture notice\",\"profile\":{\"ready\":\(Self.ready),\"profile_id\":\"profile\",\"status\":\"ready\",\"model_version\":\"fixture\",\"voice_consent_id\":\"voice\"}}"
        } else if path.hasSuffix("/profile/review"), request.httpMethod == "GET" {
            status = 200
            body = #"{"profile_id":"profile","status":"pending","reviewed_at":null,"previewed_at":null}"#
        } else if Self.tickets && path.hasSuffix("/calls") && request.httpMethod == "POST" {
            Self.calls += 1; status = 200
            body = String(data: try! JSONSerialization.data(withJSONObject: ["call_id":"vc_fixture", "room":"vc_fixture",
                "participant_identity":"user_vc_fixture", "livekit_url":"wss://fixture.invalid", "token":"fixture", "voice_mode":Self.ticketMode,
                "expires_at":ISO8601DateFormatter().string(from: Date().addingTimeInterval(600))]), encoding:.utf8)!
        } else { Self.calls += 1; status = 503; body = #"{"error_message":"fixture must not connect"}"# }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type":"application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    func completeHeldConsent() {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("[]".utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }

}

private final class ProfileRefreshPlan: @unchecked Sendable {
    private let lock = NSLock()
    private var profileCount = 0, capabilityCount = 0
    private var held: [VoiceProfileProtocol] = []
    func reset() { lock.lock(); defer { lock.unlock() }; profileCount = 0; capabilityCount = 0; held = [] }
    func record(_ request: VoiceProfileProtocol, isProfile: Bool) {
        lock.lock(); defer { lock.unlock() }
        if isProfile { profileCount += 1; held.append(request) } else { capabilityCount += 1 }
    }
    var hasPendingProfile: Bool { lock.lock(); defer { lock.unlock() }; return !held.isEmpty }
    func finishProfiles() {
        lock.lock(); let pending = held; held = []; lock.unlock()
        for request in pending { request.finish() }
    }
    var profiles: Int { lock.lock(); defer { lock.unlock() }; return profileCount }
    var capabilities: Int { lock.lock(); defer { lock.unlock() }; return capabilityCount }
}
private final class VoiceProfileProtocol: URLProtocol, @unchecked Sendable {
    static let plan = ProfileRefreshPlan()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let isProfile = request.url!.path.hasSuffix("/profile")
        Self.plan.record(self, isProfile: isProfile)
        if !isProfile {
            finish(#"{"transport":"volcengine","available":true,"default_voice_available":true,"policy":"fixture","notice":"fixture","profile":{"ready":false,"status":"enrolling","profile_id":"profile","voice_consent_id":"voice"}}"#)
        }
    }
    func finish(_ body: String = #"{"ready":true,"status":"ready","profile_id":"profile","voice_consent_id":"voice"}"#) {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type":"application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
final class TwinVoiceCallTests: XCTestCase {
    func testConcurrentProfileRefreshUsesOneProviderRequestAndUpdatesSnapshot() async throws {
        VoiceProfileProtocol.plan.reset()
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [VoiceProfileProtocol.self]
        let client = try APIClient(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),token:"fixture",session:URLSession(configuration:config))
        let pairing = Pairing(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),token:"fixture",actorID:"actor",subjectID:"subject",consentID:"recording")
        let call = TwinVoiceCallModel()
        call.configure(pairing, client: client); await call.prepare()
        XCTAssertEqual(call.profile?.status, "enrolling")
        let first = Task { await call.refreshProfile() }
        for _ in 0..<100 { if VoiceProfileProtocol.plan.hasPendingProfile { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertTrue(VoiceProfileProtocol.plan.hasPendingProfile)
        let second = Task { await call.refreshProfile() }
        try await Task.sleep(for:.milliseconds(50))
        XCTAssertEqual(VoiceProfileProtocol.plan.profiles, 1)
        VoiceProfileProtocol.plan.finishProfiles(); await first.value; await second.value
        XCTAssertEqual(call.profile?.ready, true)
        XCTAssertEqual(call.capabilities?.profile.ready, true)
        XCTAssertEqual(VoiceProfileProtocol.plan.capabilities, 1)
    }
    private func setup(_ call: TwinVoiceCallModel) async throws {
        VoiceProtocol.calls = 0
        VoiceProtocol.tickets = false
        VoiceProtocol.policy = "fixture-policy"; VoiceProtocol.ready = true
        VoiceProtocol.defaultVoice = false; VoiceProtocol.ticketMode = "personal"
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [VoiceProtocol.self]
        let client = try APIClient(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64), token: "fixture", session: URLSession(configuration: config))
        let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                              token: "fixture", actorID: "actor", subjectID: "subject", consentID: "recording")
        call.configure(pairing, client: client); await call.prepare()
        XCTAssertEqual(call.profile?.ready, true)
    }
    private func event(_ json: String) throws -> VoiceCallEvent {
        try JSONDecoder().decode(VoiceCallEvent.self, from: Data(json.utf8))
    }
    func testLiveKitMeterRequiresReadyCurrentRoomAndClearsOnHangup() async throws {
        var connectedRoom: Room?
        let actions = VoiceRoomActions(connect: { room, _ in connectedRoom = room },
                                       microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        let firstRoom = try XCTUnwrap(connectedRoom)
        call.room(firstRoom, didUpdateSpeakingParticipants: [])
        for _ in 0..<5 { await Task.yield() }
        XCTAssertNil(call.displayedAudioLevel)
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        call.room(firstRoom, didUpdateSpeakingParticipants: [])
        for _ in 0..<5 { await Task.yield() }
        XCTAssertEqual(call.microphoneAudioLevel, 0)
        await call.end()
        XCTAssertNil(call.microphoneAudioLevel)
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        call.room(firstRoom, didUpdateSpeakingParticipants: [])
        for _ in 0..<5 { await Task.yield() }
        XCTAssertNil(call.microphoneAudioLevel)
        await call.end()
    }
    func testLeavingWhileStartGrantsAreLoadingCannotStartMicrophoneLater() async throws {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [VoiceProtocol.self]
        let api = try APIClient(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64), token: "fixture", session: URLSession(configuration: config))
        let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64), token: "fixture", actorID: "actor", subjectID: "subject", consentID: "recording")
        let suite = "natural-start-cancel-" + UUID().uuidString; let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite); VoiceProtocol.holdConsents = false; VoiceProtocol.heldConsent = nil }
        VoiceProtocol.calls = 0; VoiceProtocol.defaultVoice = true; VoiceProtocol.ready = false
        let model = AppModel(defaults: defaults, pairing: pairing, apiClientFactory: { _ in api })
        await model.prepareRealtimeVoice()
        VoiceProtocol.holdConsents = true
        let task = Task { await model.startNaturalVoiceCall(useDefault: true) }
        for _ in 0..<200 { if VoiceProtocol.heldConsent != nil { break }; try await Task.sleep(for: .milliseconds(10)) }
        let held = try XCTUnwrap(VoiceProtocol.heldConsent)
        model.cancelNaturalCallStart(); held.completeHeldConsent(); await task.value
        XCTAssertFalse(model.realtimeVoice.isActive); XCTAssertFalse(model.isBusy); XCTAssertEqual(VoiceProtocol.calls, 0)
    }
    func testDefaultVoiceDoesNotRequireReadyCloneButStillWaitsForAgent() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call)
        VoiceProtocol.ready = false; VoiceProtocol.defaultVoice = true; VoiceProtocol.ticketMode = "default"
        VoiceProtocol.tickets = true; await call.prepare()
        await call.start(cloudConsent: "cloud", voiceConsent: "voice", voiceMode: "default")
        XCTAssertEqual(call.state, .connecting); XCTAssertEqual(VoiceProtocol.calls, 1)
        XCTAssertEqual(call.activeVoiceMode, "default")
        XCTAssertEqual(call.profile?.ready, false)
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        XCTAssertEqual(call.state, .listening)
        await call.end()
        XCTAssertNil(call.activeVoiceMode)
    }
    func testRefusesPlainWebSocketAndCrossRoomTickets() throws {
        func ticket(url: String, room: String = "vc_fixture") throws -> VoiceCallTicket {
            try JSONDecoder().decode(VoiceCallTicket.self, from: JSONSerialization.data(withJSONObject: [
                "call_id":"vc_fixture", "room":room, "participant_identity":"user_vc_fixture",
                "livekit_url":url, "token":"fixture", "expires_at":ISO8601DateFormatter().string(from: Date().addingTimeInterval(120))]))
        }
        XCTAssertThrowsError(try TwinVoiceCallModel.validate(ticket(url:"ws://fixture.invalid")))
        XCTAssertThrowsError(try TwinVoiceCallModel.validate(ticket(url:"wss://fixture.invalid",room:"other")))
        XCTAssertThrowsError(try TwinVoiceCallModel.validate(ticket(url:"wss://user:secret@fixture.invalid")))
        XCTAssertNoThrow(try TwinVoiceCallModel.validate(ticket(url:"wss://fixture.invalid")))
    }
    func testDeniedMicrophoneNeverRequestsCallOrTransmitsAudio() async throws {
        let call = TwinVoiceCallModel(recordPermission: { false }); try await setup(call)
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        XCTAssertEqual(call.state, .failed); XCTAssertEqual(VoiceProtocol.calls, 0)
        XCTAssertFalse(call.isActive)
    }
    func testLoginCanApplyPreparedConnectionWhileBusyButVoiceStateIsCleared() async throws {
        let model = AppModel(pairing: nil)
        let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                              token: "fixture", actorID: "actor", subjectID: "subject", consentID: "recording")
        model.isBusy = true
        XCTAssertTrue(model.applyConnection(pairing, persist: false))
        XCTAssertEqual(model.pairing?.subjectID, "subject")
        XCTAssertNil(model.realtimeVoice.profile)
    }
    func testWrongVoiceGrantCannotStartCall() async throws {
        let call = TwinVoiceCallModel(recordPermission: { XCTFail("Wrong consent must not request microphone"); return true })
        try await setup(call); await call.start(cloudConsent:"cloud",voiceConsent:"another-person")
        XCTAssertEqual(call.state, .idle); XCTAssertEqual(VoiceProtocol.calls, 0)
    }
    func testHangupDuringPermissionPromptCannotResumeConnection() async throws {
        var prompt: CheckedContinuation<Bool, Never>?
        let call = TwinVoiceCallModel(recordPermission: { await withCheckedContinuation { prompt = $0 } })
        try await setup(call)
        let pending = Task { await call.start(cloudConsent:"cloud",voiceConsent:"voice") }
        while prompt == nil { await Task.yield() }
        XCTAssertEqual(call.state,.connecting)
        await call.end(); prompt?.resume(returning:true); await pending.value
        XCTAssertEqual(call.state,.idle); XCTAssertEqual(VoiceProtocol.calls,0)
    }
    func testCancelledPermissionWaitCannotStartCallLater() async throws {
        var prompt: CheckedContinuation<Bool, Never>?
        let call = TwinVoiceCallModel(recordPermission: { await withCheckedContinuation { prompt = $0 } })
        try await setup(call)
        let pending = Task { await call.start(cloudConsent:"cloud",voiceConsent:"voice") }
        while prompt == nil { await Task.yield() }
        pending.cancel(); prompt?.resume(returning:true); await pending.value
        XCTAssertEqual(call.state,.idle); XCTAssertEqual(VoiceProtocol.calls,0)
        XCTAssertNil(call.notice)
    }
    func testScheduledBackgroundHangupCannotEndReplacementCall() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        call.endCurrentCallOnBackground()
        await call.end()
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        for _ in 0..<10 { await Task.yield() }
        XCTAssertEqual(call.state,.connecting)
        XCTAssertTrue(call.isActive)
        await call.end()
    }
    func testMediaServicesResetEndsCurrentCallWithVisibleCause() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        NotificationCenter.default.post(name:AVAudioSession.mediaServicesWereResetNotification,object:nil)
        for _ in 0..<100 { if call.state == .failed { break }; await Task.yield() }
        XCTAssertFalse(call.isActive)
        XCTAssertTrue(call.notice?.contains("音频服务已重置") == true)
    }
    func testDelayedMediaServicesResetCannotEndReplacementCall() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        NotificationCenter.default.post(name:AVAudioSession.mediaServicesWereResetNotification,object:nil)
        await call.end()
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        for _ in 0..<10 { await Task.yield() }
        XCTAssertEqual(call.state,.connecting); XCTAssertTrue(call.isActive)
        await call.end()
    }
    func testLatePriorTurnCannotReplaceNewQuestionOrRestartSpeech() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        call.receive(try event(#"{"type":"question","turn_id":"old","text":"旧问题"}"#))
        call.receive(try event(#"{"type":"question","turn_id":"new","text":"新问题"}"#))
        call.receive(try event(#"{"type":"state","turn_id":"old","state":"speaking"}"#))
        XCTAssertEqual(call.question,"新问题"); XCTAssertEqual(call.state,.thinking)
        call.receive(try event(#"{"type":"question","turn_id":"old","text":"过期问题"}"#))
        XCTAssertEqual(call.question,"新问题")
        await call.end()
    }
    func testInterruptDuringConnectingDoesNotBypassAgentReadiness() async throws {
        var connection: CheckedContinuation<Void, Error>?
        let actions = VoiceRoomActions(connect: { _, _ in try await withCheckedThrowingContinuation { connection = $0 } },
                                       microphone: { _, _ in }, interrupt: { _, _ in XCTFail("No turn exists") })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        let pending = Task { await call.start(cloudConsent:"cloud", voiceConsent:"voice") }
        while connection == nil { await Task.yield() }
        await call.interrupt(); XCTAssertEqual(call.state, .connecting)
        await call.end(); connection?.resume(); await pending.value
        XCTAssertEqual(call.state, .idle)
    }
    func testRapidMuteTapsHaveOneMicrophoneOperationAndOneTargetState() async throws {
        var mutation: CheckedContinuation<Void, Error>?; var disabling = 0
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, enabled in
            if !enabled { disabling += 1; try await withCheckedThrowingContinuation { mutation = $0 } }
        }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud", voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        let first = Task { await call.toggleMute() }
        while mutation == nil { await Task.yield() }
        await call.toggleMute(); XCTAssertEqual(disabling,1); XCTAssertTrue(call.isChangingMute)
        mutation?.resume(); await first.value
        XCTAssertTrue(call.muted); XCTAssertFalse(call.isChangingMute)
        await call.end()
    }
    func testOldMuteFailureCannotEndANewCall() async throws {
        var mutation: CheckedContinuation<Void, Error>?
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, enabled in
            if !enabled { try await withCheckedThrowingContinuation { mutation = $0 } }
        }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud", voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        let old = Task { await call.toggleMute() }
        while mutation == nil { await Task.yield() }
        await call.end(); await call.start(cloudConsent:"cloud", voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        mutation?.resume(throwing: APIError.invalidResponse); await old.value
        XCTAssertEqual(call.state,.listening); XCTAssertFalse(call.muted); XCTAssertFalse(call.isChangingMute)
        await call.end()
    }
    func testOldInterruptPublishFailureCannotEndANewCall() async throws {
        var publication: CheckedContinuation<Void, Error>?
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in },
            interrupt: { _, _ in try await withCheckedThrowingContinuation { publication = $0 } })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud", voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        call.receive(try event(#"{"type":"question","turn_id":"old","text":"旧问题"}"#))
        let old = Task { await call.interrupt() }
        while publication == nil { await Task.yield() }
        await call.end(); await call.start(cloudConsent:"cloud", voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        call.receive(try event(#"{"type":"question","turn_id":"new","text":"新问题"}"#))
        publication?.resume(throwing: APIError.invalidResponse); await old.value
        XCTAssertEqual(call.state,.thinking); XCTAssertEqual(call.question,"新问题")
        await call.end()
    }

    func testEventsCannotBypassRecognitionReadiness() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        call.receive(try event(#"{"type":"question","turn_id":"early","text":"未就绪"}"#))
        call.receive(try event(#"{"type":"state","state":"speaking","turn_id":"early"}"#))
        XCTAssertEqual(call.state,.connecting); XCTAssertEqual(call.question,"")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        XCTAssertEqual(call.state,.listening)
        await call.end()
    }

    func testPolicyChangeRequiresNewAcceptanceBeforeRequestingTicket() async throws {
        let call = TwinVoiceCallModel(recordPermission: { true })
        try await setup(call); VoiceProtocol.policy = "changed-policy"
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        XCTAssertEqual(VoiceProtocol.calls,0); XCTAssertEqual(call.state,.failed)
        XCTAssertEqual(call.capabilities?.policy,"changed-policy")
    }

    func testRevokedProfileCannotUseCachedReadyState() async throws {
        let call = TwinVoiceCallModel(recordPermission: { true })
        try await setup(call); VoiceProtocol.ready = false
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        XCTAssertEqual(VoiceProtocol.calls,0); XCTAssertEqual(call.state,.failed)
    }

    func testReconnectionEndsCallAndLateCallbacksCannotRestartIt() async throws {
        var connectedRoom: Room?
        let actions = VoiceRoomActions(connect: { room, _ in connectedRoom = room }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        let old = try XCTUnwrap(connectedRoom)
        call.roomIsReconnecting(old)
        while call.isActive { await Task.yield() }
        XCTAssertEqual(call.state,.failed)
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        call.roomDidReconnect(old); await Task.yield()
        XCTAssertEqual(call.state,.connecting)
        await call.end()
    }

    func testRemovingAudioDeviceStopsCallAndRejectsLateEvents() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        await call.selectSpeaker(false)
        await call.audioRouteChanged(reason: .oldDeviceUnavailable, previousOutputs: [.bluetoothHFP])
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        XCTAssertEqual(call.state,.failed); XCTAssertFalse(call.isActive)
    }

    func testCallSelectsPhoneSpeakerAfterMicrophoneWithoutRequiringBluetooth() async throws {
        var operations: [String] = []
        var ports: [AVAudioSession.Port] = [.bluetoothHFP]
        let actions = VoiceRoomActions(connect: { _, _ in operations.append("connect") },
            microphone: { _, enabled in operations.append(enabled ? "microphone" : "mute") },
            interrupt: { _, _ in }, selectSpeaker: { enabled in
                operations.append(enabled ? "speaker" : "system")
                ports = enabled ? [.builtInSpeaker] : [.builtInReceiver]
            }, releaseAudioRoute: { operations.append("release") }, outputPorts: { ports })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        XCTAssertEqual(operations, ["connect", "microphone", "speaker"])
        XCTAssertEqual(call.audioRoute, "手机扬声器"); XCTAssertTrue(call.speakerEnabled)
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        await call.toggleMute()
        XCTAssertTrue(call.speakerEnabled); XCTAssertEqual(call.audioRouteSymbol, "speaker.wave.2.fill")
        await call.selectSpeaker(false)
        XCTAssertFalse(call.speakerEnabled); XCTAssertEqual(call.audioRoute, "手机听筒")
        await call.audioRouteChanged(reason: .oldDeviceUnavailable, previousOutputs: [.builtInReceiver])
        XCTAssertEqual(call.state, .listening)
        await call.selectSpeaker(true)
        XCTAssertTrue(call.speakerEnabled); XCTAssertEqual(call.audioRoute, "手机扬声器")
        await call.end()
        XCTAssertEqual(operations.last, "release"); XCTAssertFalse(call.canSelectAudioOutput)
    }

    func testBluetoothRemovalKeepsSpeakerCallAndRestoresClearedOverrideWithoutLooping() async throws {
        var ports: [AVAudioSession.Port] = [.builtInSpeaker]
        var selections = 0
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in },
            selectSpeaker: { _ in selections += 1; ports = [.builtInSpeaker] }, outputPorts: { ports })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        await call.audioRouteChanged(reason: .oldDeviceUnavailable)
        XCTAssertEqual(call.state, .listening); XCTAssertEqual(selections, 1)
        ports = [.builtInReceiver]
        await call.audioRouteChanged(reason: .categoryChange)
        XCTAssertEqual(selections, 2); XCTAssertEqual(call.audioRoute, "手机扬声器")
        await call.audioRouteChanged(reason: .override)
        XCTAssertEqual(selections, 2); XCTAssertEqual(call.state, .listening)
        await call.end()
    }

    func testOutputCannotChangeBeforeMicrophoneIsReadyOrAfterHangup() async throws {
        var connection: CheckedContinuation<Void, Error>?
        var selections: [Bool] = []
        let actions = VoiceRoomActions(connect: { _, _ in try await withCheckedThrowingContinuation { connection = $0 } },
            microphone: { _, _ in }, interrupt: { _, _ in }, selectSpeaker: { selections.append($0) })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        let start = Task { await call.start(cloudConsent: "cloud", voiceConsent: "voice") }
        while connection == nil { await Task.yield() }
        await call.selectSpeaker(false)
        XCTAssertTrue(selections.isEmpty); XCTAssertFalse(call.canSelectAudioOutput)
        await call.end(); connection?.resume(); await start.value
        await call.selectSpeaker(true)
        XCTAssertTrue(selections.isEmpty); XCTAssertEqual(call.state, .idle)
    }

    func testSpeakerRoutingFailureEndsCallAndReleasesAudioSettings() async throws {
        var released = 0
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in },
            selectSpeaker: { _ in throw APIError.invalidResponse }, releaseAudioRoute: { released += 1 })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        XCTAssertEqual(call.state, .failed); XCTAssertFalse(call.isActive)
        XCTAssertEqual(released, 1); XCTAssertFalse(call.canSelectAudioOutput)
    }

    func testAutomaticBargeInCancelsActiveTurnAndRejectsLateSpeech() async throws {
        var cancelled: [String] = []
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, turn in cancelled.append(turn) })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent:"cloud",voiceConsent:"voice")
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        call.receive(try event(#"{"type":"question","turn_id":"old","text":"旧问题"}"#))
        await call.userBeganSpeaking()
        call.receive(try event(#"{"type":"state","turn_id":"old","state":"speaking"}"#))
        XCTAssertEqual(cancelled,["old"]); XCTAssertEqual(call.state,.listening)
        await call.end()
    }
    func testSpeakerNamesRequireCurrentReadyTurnAndClearOnNewSpeechAndHangup() async throws {
        let actions = VoiceRoomActions(connect: { _, _ in }, microphone: { _, _ in }, interrupt: { _, _ in })
        let call = TwinVoiceCallModel(recordPermission: { true }, roomActions: actions)
        try await setup(call); VoiceProtocol.tickets = true
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        call.receive(try event(#"{"type":"speaker","turn_id":"early","speaker_names":["过早姓名"]}"#))
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        call.receive(try event(#"{"type":"state","state":"listening"}"#))
        call.receive(try event(#"{"type":"question","turn_id":"one","text":"你好"}"#))
        call.receive(try event(#"{"type":"speaker","turn_id":"one","speaker_names":[" 小王 ","小王"," ","小李"]}"#))
        XCTAssertEqual(call.identifiedSpeakerNames, ["小王", "小李"])
        call.receive(try event(#"{"type":"state","turn_id":"one","state":"listening"}"#))
        await call.userBeganSpeaking()
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        call.receive(try event(#"{"type":"speaker","turn_id":"one","speaker_names":["小王"]}"#))
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        call.receive(try event(#"{"type":"question","turn_id":"two","text":"换个人"}"#))
        call.receive(try event(#"{"type":"speaker","turn_id":"one","speaker_names":["旧姓名"],"message":"旧提示"}"#))
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty); XCTAssertNotEqual(call.notice, "旧提示")
        call.receive(try event(#"{"type":"speaker","turn_id":"two","speaker_names":["小李"]}"#))
        XCTAssertEqual(call.identifiedSpeakerNames, ["小李"])
        call.receive(try event(#"{"type":"speaker","turn_id":"two","message":"旧服务只有提示"}"#))
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        call.receive(try event(#"{"type":"speaker","turn_id":"two","speaker_names":["小李"]}"#))
        await call.interrupt()
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        call.receive(try event(#"{"type":"speaker","turn_id":"two","speaker_names":["小李"]}"#))
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        call.receive(try event(#"{"type":"question","turn_id":"three","text":"再说一句"}"#))
        call.receive(try event(#"{"type":"speaker","turn_id":"three","speaker_names":["小王"]}"#))
        await call.end()
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        await call.start(cloudConsent: "cloud", voiceConsent: "voice")
        XCTAssertTrue(call.identifiedSpeakerNames.isEmpty)
        await call.end()
    }

}

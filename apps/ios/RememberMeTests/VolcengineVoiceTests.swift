import XCTest
import VolcEngineRTC
@testable import RememberMe

private final class DomesticFailurePlan: @unchecked Sendable {
    private let lock = NSLock()
    private var leaseFailures = 0, statusFailures = 0, leaseCode = 503
    private var calls = 0
    private var turn: String?
    private var mode = "default", responseType: String?, stale = false, failed = false
    func reset(lease: Int = 0, status: Int = 0, code: Int = 503, turn: String? = nil,
               mode: String = "default", responseType: String? = nil, stale: Bool = false, failed: Bool = false) {
        lock.lock(); defer { lock.unlock() }
        leaseFailures = lease; statusFailures = status; leaseCode = code; calls = 0
        self.turn = turn
        self.mode = mode; self.responseType = responseType; self.stale = stale
        self.failed = failed
    }
    func failNextLeases(_ count: Int, code: Int = 503) {
        lock.lock(); defer { lock.unlock() }
        leaseFailures = count; leaseCode = code
    }
    func response(_ path: String) -> Int {
        lock.lock(); defer { lock.unlock() }
        if path.hasSuffix("/lease") {
            calls += 1
            if leaseFailures > 0 { leaseFailures -= 1; return leaseCode }
        }
        if path.hasSuffix("/status"), statusFailures > 0 { statusFailures -= 1; return 503 }
        return 200
    }
    var leaseCalls: Int { lock.lock(); defer { lock.unlock() }; return calls }
    var statusTurn: String? { lock.lock(); defer { lock.unlock() }; return turn }
    var voiceMode: String { lock.lock(); defer { lock.unlock() }; return mode }
    var statusFailed: Bool { lock.lock(); defer { lock.unlock() }; return failed }
    var statusAnswer: [String: Any]? {
        lock.lock(); defer { lock.unlock() }
        guard let responseType else { return nil }
        return ["answer_id":"answer_fixture", "question":"已识别的问题", "answer":"不可当成人物原话播放的未知内容",
                "response_type":responseType, "evidence":[], "model_version":"fixture", "person_model_version":1, "stale":stale]
    }
}
private final class DomesticResponseGate: @unchecked Sendable {
    private let lock = NSLock()
    private var suffix: String?
    private var pending: (DomesticProtocol, Data)?
    func hold(_ suffix: String) { lock.lock(); defer { lock.unlock() }; self.suffix = suffix; pending = nil }
    func capture(_ request: DomesticProtocol, body: Data) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard let suffix, request.request.url!.path.hasSuffix(suffix), pending == nil else { return false }
        pending = (request, body); return true
    }
    var hasPending: Bool { lock.lock(); defer { lock.unlock() }; return pending != nil }
    func release(status: Int = 200) {
        lock.lock(); let held = pending; pending = nil; suffix = nil; lock.unlock()
        if let held { held.0.finish(status: status, body: held.1) }
    }
}
private final class DomesticProtocol: URLProtocol, @unchecked Sendable {
    static let failures = DomesticFailurePlan()
    static let gate = DomesticResponseGate()
    static let callID = "vc_" + String(repeating: "a", count: 32)
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url!.path
        let body: [String: Any]
        if path.contains("/speech/") {
            client?.urlProtocol(self,didReceive:HTTPURLResponse(url:request.url!,statusCode:200,httpVersion:nil,
                headerFields:["Content-Type":"audio/pcm", "X-Audio-Sample-Rate":"24000", "X-Audio-Channels":"1"])!,cacheStoragePolicy:.notAllowed)
            client?.urlProtocol(self,didLoad:Data([1,2,3,4]));client?.urlProtocolDidFinishLoading(self)
            return
        }
        if path.hasSuffix("/capabilities") {
            body = ["transport":"volcengine", "available":true, "default_voice_available":true,
                    "policy":"test-only", "notice":"synthetic test", "profile":["ready":true,"status":"ready","voice_consent_id":"voice"]]
        } else if path.hasSuffix("/calls"), request.httpMethod == "POST" {
            let id = Self.callID, app = String(repeating:"b",count:24)
            body = ["transport":"volcengine", "call_id":id, "room":id, "participant_identity":"user_"+id,
                    "bot_identity":"twin_"+id, "app_id":app, "token":"001"+app+"fixture", "voice_mode":Self.failures.voiceMode,
                    "expires_at":ISO8601DateFormatter().string(from:Date().addingTimeInterval(600))]
        } else if (path.hasSuffix("/heartbeat") || path.hasSuffix("/status")) {
            if let turn = Self.failures.statusTurn {
                var result: [String: Any] = ["call_id":Self.callID,"turn_id":turn,"question":"已经识别的原话","failed":Self.failures.statusFailed]
                if let answer = Self.failures.statusAnswer { result["answer"] = answer }
                body = result
            } else { body = ["call_id":Self.callID,"question":"","failed":false] }
        } else if path.hasSuffix("/lease") { body = ["call_id":Self.callID] } else { body = [:] }
        let data = try! JSONSerialization.data(withJSONObject:body)
        if Self.gate.capture(self,body:data) { return }
        finish(status:Self.failures.response(path),body:data)
    }
    func finish(status: Int, body: Data) {
        client?.urlProtocol(self,didReceive:HTTPURLResponse(url:request.url!,statusCode:status,httpVersion:nil,headerFields:["Content-Type":"application/json"])!,cacheStoragePolicy:.notAllowed)
        client?.urlProtocol(self,didLoad:body);client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
private final class DomesticStub: DomesticVoiceTransport {
    var onConversation: (@MainActor (VolcengineVoiceTransport.Conversation) -> Void)?
    var onAgentConnected: (@MainActor () -> Void)?
    var onFailure: (@MainActor () -> Void)?
    var onCaptured: (@MainActor (String, Data) -> Void)?
    var onSample: (@MainActor (String, Data) -> Void)?
    var onSpeechBegan: (@MainActor () -> Void)?
    var onConnectionChanged: (@MainActor (DomesticVoiceConnectionState) -> Void)?
    var onAudioLevels: (@MainActor (Double?, Double?) -> Void)?
    var played = 0, resumed = 0
    func playPersonalAudio(_ bytes: URLSession.AsyncBytes) async throws { played += 1 }
    func stopPersonalAudio() {}
    func diagnostic(_ code: String) {}
    func captureTurn(_ round: Int) {}
    var botJoins = true
    var microphoneEnabled = false
    var disconnected = false
    func connect(_ ticket: VoiceCallTicket) async throws { if botJoins { onAgentConnected?() } }
    func microphone(_ enabled: Bool) throws { microphoneEnabled = enabled }
    func resumeAfterReconnect(microphone enabled: Bool) throws { resumed += 1; microphoneEnabled = enabled }
    func selectSpeaker(_ enabled: Bool) throws {}
    func volume(_ value: Double) {}
    func disconnect() async { disconnected = true; microphoneEnabled = false; onConversation = nil; onAgentConnected = nil; onFailure = nil; onConnectionChanged = nil; onAudioLevels = nil }
    func changeConnection(_ state: DomesticVoiceConnectionState) {
        if case .recovering = state { microphoneEnabled = false }
        onConnectionChanged?(state)
    }
    func emit(_ code: Int, round: Int = 1) {
        onConversation?(.init(TaskId:DomesticProtocol.callID,RoundID:round,EventTime:1234+Int64(code),Stage:.init(Code:code)))
    }
}

@MainActor
final class VolcengineVoiceTests: XCTestCase {
    func testNativeRoomWarningPreservesCallButTerminalRoomErrorFails() {
        let transport = VolcengineVoiceTransport()
        var failures = 0
        transport.onFailure = { failures += 1 }
        for warning in [-2002,-2003,-2004,-2013] { transport.receiveRoomState(warning) }
        XCTAssertEqual(failures,0); XCTAssertNil(transport.failureMessage)
        transport.receiveRoomState(-1004) // Duplicate login is a terminal departure.
        XCTAssertEqual(failures,1)
        XCTAssertTrue(transport.failureMessage?.contains("-1004") == true)
    }
    func testAsynchronousCaptureFailureCannotRemainSilentlyListening() async {
        for error: ByteRTCLocalAudioStreamError in [.deviceNoPermission, .recordFailure, .encodeFailure] {
            let transport = VolcengineVoiceTransport()
            var failures = 0
            transport.onFailure = { failures += 1 }
            transport.receiveLocalAudioState(state:.recording,error:.ok)
            transport.receiveLocalAudioState(state:.stopped,error:.ok)
            XCTAssertEqual(failures,0)
            transport.receiveLocalAudioState(state:.failed,error:error)
            XCTAssertEqual(failures,1)
            XCTAssertTrue(transport.failureMessage?.contains("麦克风") == true)
            await transport.disconnect()
            transport.receiveLocalAudioState(state:.failed,error:error)
            XCTAssertEqual(failures,1)
        }
    }
    func testPriorDomesticInterruptFailureCannotEndReplacementCall() async throws {
        DomesticProtocol.gate.hold("/interrupt")
        defer { DomesticProtocol.gate.release(status:503) }
        let stub = DomesticStub(), call = try await start(stub)
        stub.emit(2)
        let interrupt = Task { await call.interrupt() }
        for _ in 0..<100 { if DomesticProtocol.gate.hasPending { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertTrue(DomesticProtocol.gate.hasPending)
        await call.end()
        await call.start(cloudConsent:"cloud",voiceConsent:"voice",voiceMode:"default")
        stub.emit(2,round:2)
        DomesticProtocol.gate.release(status:503); await interrupt.value
        XCTAssertEqual(call.state,.thinking); XCTAssertTrue(call.isActive)
        await call.end()
    }
    func testOlderFailedStatusCannotResetNewerSpeakingTurn() async throws {
        DomesticProtocol.gate.hold("/status")
        defer { DomesticProtocol.gate.release() }
        let stub = DomesticStub(), call = try await start(stub,statusTurn:"ve_1",failed:true)
        for _ in 0..<100 { if DomesticProtocol.gate.hasPending { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertTrue(DomesticProtocol.gate.hasPending)
        stub.emit(2,round:2); stub.emit(3,round:2)
        XCTAssertEqual(call.state,.speaking)
        DomesticProtocol.gate.release()
        try await Task.sleep(for:.milliseconds(50))
        XCTAssertEqual(call.state,.speaking)
        XCTAssertNil(call.notice)
        await call.end()
    }
    func testConnectionResetFinishesLocallyBeforeSlowBackendDelete() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        DomesticProtocol.gate.hold("/" + DomesticProtocol.callID)
        defer { DomesticProtocol.gate.release() }
        let ending = Task { await call.end(resetConnectionAfter:true) }
        for _ in 0..<100 { if DomesticProtocol.gate.hasPending { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertTrue(DomesticProtocol.gate.hasPending)
        XCTAssertEqual(call.state,.idle); XCTAssertNil(call.capabilities); XCTAssertNil(call.profile)
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [DomesticProtocol.self]
        let client = try APIClient(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),token:"replacement",session:URLSession(configuration:config))
        let pairing = Pairing(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),token:"replacement",actorID:"replacement",subjectID:"subject",consentID:"recording")
        call.configure(pairing,client:client); await call.prepare()
        XCTAssertNotNil(call.capabilities)
        DomesticProtocol.gate.release(); await ending.value
        XCTAssertNotNil(call.capabilities); XCTAssertEqual(call.profile?.ready,true)
    }
    private func start(_ stub: DomesticStub, leaseFailures: Int = 0, statusFailures: Int = 0,
                       leaseCode: Int = 503, grace: Duration = .seconds(8), statusTurn: String? = nil,
                       mode: String = "default", responseType: String? = nil, stale: Bool = false, failed: Bool = false) async throws -> TwinVoiceCallModel {
        DomesticProtocol.failures.reset(lease: leaseFailures, status: statusFailures, code: leaseCode, turn: statusTurn,
                                       mode: mode, responseType: responseType, stale: stale, failed: failed)
        let config = URLSessionConfiguration.ephemeral;config.protocolClasses = [DomesticProtocol.self]
        let client = try APIClient(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),token:"fixture",session:URLSession(configuration:config))
        let pairing = Pairing(baseURL:"https://fixture.invalid",fingerprint:String(repeating:"a",count:64),token:"fixture",actorID:"actor",subjectID:"subject",consentID:"recording")
        let call = TwinVoiceCallModel(recordPermission:{true},domesticFactory:{stub},agentReadyTimeout:.milliseconds(30),domesticRetryGrace:grace)
        call.configure(pairing,client:client);await call.prepare()
        await call.start(cloudConsent:"cloud",voiceConsent:"voice",voiceMode:mode)
        return call
    }
    func testMeasuredAudioSelectsListeningAndSpeakingSourcesAndHonorsMute() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        XCTAssertNil(call.displayedAudioLevel)
        stub.onAudioLevels?(0.35, 0.8)
        XCTAssertEqual(call.microphoneAudioLevel, 0.35)
        XCTAssertNil(call.playbackAudioLevel)
        XCTAssertEqual(call.displayedAudioLevel, 0.35)
        stub.emit(2)
        XCTAssertNil(call.displayedAudioLevel)
        stub.emit(3)
        XCTAssertNil(call.displayedAudioLevel) // A speaking state alone is not a sound measurement.
        stub.onAudioLevels?(-0.2, 1.2)
        XCTAssertEqual(call.microphoneAudioLevel, 0)
        XCTAssertEqual(call.displayedAudioLevel, 1)
        await call.toggleMute()
        XCTAssertNil(call.microphoneAudioLevel)
        XCTAssertEqual(call.displayedAudioLevel, 1) // Muting capture preserves audible remote playback.
        stub.emit(5)
        XCTAssertNil(call.playbackAudioLevel)
        XCTAssertNil(call.displayedAudioLevel)
        stub.onAudioLevels?(0.8, 0.7)
        XCTAssertNil(call.microphoneAudioLevel)
        XCTAssertNil(call.displayedAudioLevel)
        await call.toggleMute()
        XCTAssertNil(call.displayedAudioLevel) // Wait for a fresh post-unmute report.
        stub.onAudioLevels?(0, nil)
        XCTAssertEqual(call.displayedAudioLevel, 0)
        await call.end()
        XCTAssertNil(call.microphoneAudioLevel); XCTAssertNil(call.playbackAudioLevel)
    }
    func testLateAudioCallbackCannotReviveEndedOrReplacementCall() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        let oldReport = stub.onAudioLevels
        oldReport?(0.9, 0.9)
        await call.end()
        oldReport?(0.9, 0.9)
        XCTAssertNil(call.microphoneAudioLevel); XCTAssertNil(call.playbackAudioLevel)
        await call.start(cloudConsent: "cloud", voiceConsent: "voice", voiceMode: "default")
        stub.onAudioLevels?(0.2, nil)
        oldReport?(0.9, 0.9)
        XCTAssertEqual(call.displayedAudioLevel, 0.2)
        await call.end()
    }
    func testRecoveryAndMissingAudioReportsClearAmplitude() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        stub.onAudioLevels?(0.6, nil)
        stub.changeConnection(.recovering)
        XCTAssertNil(call.microphoneAudioLevel)
        stub.onAudioLevels?(0.9, 0.9)
        XCTAssertNil(call.displayedAudioLevel)
        stub.changeConnection(.connected)
        for _ in 0..<100 { if stub.resumed > 0 { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertNil(call.displayedAudioLevel)
        stub.onAudioLevels?(0.4, nil)
        XCTAssertEqual(call.displayedAudioLevel, 0.4)
        try await Task.sleep(for: .milliseconds(450))
        XCTAssertNil(call.displayedAudioLevel)
        await call.end()
    }
    func testAudioNormalizationRejectsInvalidValuesAndMeasuresSignedPCM() throws {
        XCTAssertNil(VoiceAudioMeter.normalized(.nan)); XCTAssertNil(VoiceAudioMeter.normalized(.infinity))
        XCTAssertEqual(VoiceAudioMeter.decibels(-127), 0)
        XCTAssertEqual(VoiceAudioMeter.decibels(-30), 0.5)
        XCTAssertEqual(VoiceAudioMeter.decibels(20), 1)
        var silence = VoicePCM16AudioMeter()
        XCTAssertEqual(silence.append(Data(repeating: 0, count: 4800)), 0)
        for sample: Int16 in [16384, -16384] {
            var value = sample.littleEndian
            let frame = withUnsafeBytes(of: &value) { Data($0) }
            var meter = VoicePCM16AudioMeter()
            let halfWindow = (0..<1200).reduce(into: Data()) { data, _ in data.append(frame) }
            XCTAssertNil(meter.append(halfWindow))
            XCTAssertNil(meter.append(Data([0]))) // Partial samples are not interpreted.
            XCTAssertEqual(try XCTUnwrap(meter.append(halfWindow)), (20 * log10(0.5) + 60) / 60, accuracy: 0.00001)
        }
    }
    func testRTCInterruptionRecoversOnlyAfterFreshLease() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        // Wait for the independent initial lease before simulating the media break.
        for _ in 0..<100 { if DomesticProtocol.failures.leaseCalls > 0 { break }; try await Task.sleep(for:.milliseconds(10)) }
        let previousLeases = DomesticProtocol.failures.leaseCalls
        stub.changeConnection(.recovering)
        XCTAssertEqual(call.state,.reconnecting); XCTAssertFalse(stub.microphoneEnabled)
        stub.emit(2); XCTAssertEqual(call.state,.reconnecting)
        stub.changeConnection(.connected)
        for _ in 0..<100 { if stub.resumed > 0 { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(call.state,.awaitingSpeech); XCTAssertTrue(stub.microphoneEnabled)
        XCTAssertGreaterThan(DomesticProtocol.failures.leaseCalls,previousLeases)
        XCTAssertFalse(stub.disconnected)
        await call.end()
    }
    func testRTCRecoveryPreservesUserMute() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        await call.toggleMute(); XCTAssertTrue(call.muted)
        stub.changeConnection(.recovering); stub.changeConnection(.connected)
        for _ in 0..<100 { if stub.resumed > 0 { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertTrue(call.muted); XCTAssertFalse(stub.microphoneEnabled)
        XCTAssertEqual(stub.resumed,1)
        await call.end()
    }
    func testRepeatedRTCRecoveryEventsDoNotExtendDeadline() async throws {
        let stub = DomesticStub(), call = try await start(stub,grace:.milliseconds(150))
        stub.changeConnection(.recovering)
        try await Task.sleep(for:.milliseconds(100))
        stub.changeConnection(.recovering)
        try await Task.sleep(for:.milliseconds(100))
        XCTAssertEqual(call.state,.failed); XCTAssertTrue(stub.disconnected)
        XCTAssertEqual(stub.resumed,0)
    }
    func testRTCReconnectWithRevokedLeaseNeverRestoresMicrophone() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        stub.changeConnection(.recovering)
        DomesticProtocol.failures.failNextLeases(99,code:403)
        stub.changeConnection(.connected)
        for _ in 0..<100 { if call.state == .failed { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(call.state,.failed); XCTAssertFalse(stub.microphoneEnabled)
        XCTAssertEqual(stub.resumed,0); XCTAssertTrue(stub.disconnected)
    }
    func testLateRTCRecoveryAfterEndCannotRestoreOldCall() async throws {
        let stub = DomesticStub(), call = try await start(stub,grace:.milliseconds(50))
        let lateEvent = stub.onConnectionChanged
        stub.changeConnection(.recovering)
        await call.end()
        lateEvent?(.connected)
        try await Task.sleep(for:.milliseconds(100))
        XCTAssertEqual(call.state,.idle); XCTAssertFalse(stub.microphoneEnabled)
        XCTAssertEqual(stub.resumed,0)
    }
    func testRTCRecoveryDoesNotReplayRetiredTurnFromStatus() async throws {
        let stub = DomesticStub(), call = try await start(stub,statusTurn:"ve_1")
        for _ in 0..<100 { if call.state == .thinking { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(call.state,.thinking)
        stub.changeConnection(.recovering); stub.changeConnection(.connected)
        for _ in 0..<100 { if stub.resumed > 0 { break }; try await Task.sleep(for:.milliseconds(10)) }
        try await Task.sleep(for:.milliseconds(850))
        stub.emit(3)
        XCTAssertEqual(call.state,.listening); XCTAssertEqual(stub.played,0)
        await call.end()
    }
    func testUnknownPersonalTurnPlaysFixedServerFeedbackOnceAndFinishes() async throws {
        let stub = DomesticStub(), call = try await start(stub,statusTurn:"ve_1",mode:"personal",responseType:"UNKNOWN")
        for _ in 0..<100 { if stub.played > 0 && call.state == .listening { break }; try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(stub.played,1); XCTAssertEqual(call.state,.listening)
        XCTAssertEqual(call.notice,"现有资料还不足以回答这个问题。你可以补充相关经历，或换个问题。")
        try await Task.sleep(for:.milliseconds(850))
        XCTAssertEqual(stub.played,1); XCTAssertEqual(call.state,.listening)
        await call.end()
    }
    func testStaleUnknownAnswerCannotStartPersonalFeedback() async throws {
        let stub = DomesticStub(), call = try await start(stub,statusTurn:"ve_1",mode:"personal",responseType:"UNKNOWN",stale:true)
        try await Task.sleep(for:.milliseconds(100))
        XCTAssertEqual(stub.played,0)
        await call.end()
    }
    func testRecognizedServerTurnDoesNotDependOnInitialConversationEvent() async throws {
        let stub = DomesticStub(), call = try await start(stub,statusTurn:"ve_1")
        for _ in 0..<120 { if call.state == .thinking { break };try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(call.state,.thinking);XCTAssertEqual(call.question,"已经识别的原话")
        XCTAssertFalse(stub.disconnected)
        await call.end()
    }
    func testTemporaryLeaseFailureRetriesWithoutEndingCall() async throws {
        let stub = DomesticStub(), call = try await start(stub,leaseFailures:1)
        try await Task.sleep(for:.milliseconds(750))
        XCTAssertEqual(call.state,.awaitingSpeech);XCTAssertFalse(stub.disconnected)
        XCTAssertGreaterThanOrEqual(DomesticProtocol.failures.leaseCalls,2)
        XCTAssertNil(call.notice)
        await call.end()
    }
    func testSlowAnswerStatusCannotStopIndependentLease() async throws {
        let stub = DomesticStub(), call = try await start(stub,statusFailures:99)
        try await Task.sleep(for:.milliseconds(2200))
        XCTAssertEqual(call.state,.awaitingSpeech);XCTAssertFalse(stub.disconnected)
        XCTAssertGreaterThanOrEqual(DomesticProtocol.failures.leaseCalls,2)
        await call.end()
    }
    func testWorkingStatusRenewalPreventsFalseLeaseTimeout() async throws {
        let stub = DomesticStub(), call = try await start(stub,leaseFailures:99,grace:.seconds(1))
        // /status authenticates and renews the call lease too. Its successful
        // receipts keep the call valid while the separate lease path retries.
        try await Task.sleep(for:.milliseconds(1250))
        XCTAssertEqual(call.state,.awaitingSpeech); XCTAssertFalse(stub.disconnected)
        XCTAssertGreaterThanOrEqual(DomesticProtocol.failures.leaseCalls,3)
        await call.end()
    }
    func testRevokedLeaseStopsWithoutRetrying() async throws {
        let stub = DomesticStub(), call = try await start(stub,leaseFailures:99,leaseCode:403)
        for _ in 0..<100 { if call.state == .failed { break };try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(call.state,.failed);XCTAssertTrue(stub.disconnected)
        XCTAssertEqual(DomesticProtocol.failures.leaseCalls,1)
    }
    func testPersistentNetworkFailureStopsWithinGrace() async throws {
        let stub = DomesticStub(), call = try await start(stub,leaseFailures:99,statusFailures:99,grace:.milliseconds(30))
        for _ in 0..<100 { if call.state == .failed { break };try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(call.state,.failed);XCTAssertTrue(stub.disconnected)
    }
    func testMicrophoneBufferDiscardsSilenceAndClearsOnMute() {
        let buffer = DomesticMicrophoneBuffer();buffer.setEnabled(true)
        buffer.append(Data(repeating:0,count:16000*2*65))
        var sample = Int16(5000).littleEndian
        let speech = withUnsafeBytes(of:&sample) { Data($0) }
        buffer.append(Data(repeating:0,count:0) + (0..<16000).reduce(into:Data()) { data,_ in data.append(speech) })
        let pcm = buffer.drain()
        XCTAssertEqual(pcm?.count,41600)
        XCTAssertEqual(DomesticMicrophoneBuffer.wave(pcm!).count,41644)
        buffer.setEnabled(false);buffer.append(pcm!)
        XCTAssertNil(buffer.drain())
    }
    func testLongSpeechCannotUseTruncatedAudioToVerifyWholeTurn() {
        let buffer = DomesticMicrophoneBuffer();buffer.setEnabled(true)
        let loud = Data(repeating:0x30,count:960002)
        buffer.append(loud);XCTAssertNil(buffer.drain())
        buffer.append(loud.prefix(32000));XCTAssertEqual(buffer.drain()?.count,32000)
    }
    func testConnectedSilentDomesticCallDoesNotFailWaitingForFirstSpeech() async throws {
        let stub = DomesticStub(), call = try await start(stub)
        XCTAssertEqual(call.state,.awaitingSpeech);XCTAssertTrue(stub.microphoneEnabled)
        try await Task.sleep(for:.milliseconds(100))
        XCTAssertEqual(call.state,.awaitingSpeech);XCTAssertFalse(stub.disconnected)
        await call.toggleMute();XCTAssertTrue(call.muted);XCTAssertFalse(stub.microphoneEnabled)
        await call.toggleMute();XCTAssertFalse(call.muted)
        // A thinking event itself proves ASR progress even if initial listening was missed.
        stub.emit(2);XCTAssertEqual(call.state,.thinking)
        stub.emit(3);XCTAssertEqual(call.state,.speaking)
        stub.emit(5);XCTAssertEqual(call.state,.listening)
        await call.end();XCTAssertTrue(stub.disconnected)
    }
    func testDomesticRoomJoinWithoutAgentStillTimesOut() async throws {
        let stub = DomesticStub();stub.botJoins = false
        let call = try await start(stub)
        XCTAssertEqual(call.state,.connecting)
        for _ in 0..<100 { if call.state == .failed { break };try await Task.sleep(for:.milliseconds(10)) }
        XCTAssertEqual(call.state,.failed);XCTAssertTrue(stub.disconnected)
    }
    func testDomesticTicketRequiresBoundAppBotAndProvider() throws {
        let identifier = "vc_" + String(repeating: "a", count: 32)
        let appID = String(repeating: "b", count: 24)
        var payload: [String: Any] = ["transport":"volcengine", "call_id":identifier, "room":identifier,
            "participant_identity":"user_" + identifier, "bot_identity":"twin_" + identifier,
            "app_id":appID, "token":"001" + appID + "fixture",
            "expires_at":ISO8601DateFormatter().string(from: Date().addingTimeInterval(600)), "voice_mode":"default"]
        func ticket() throws -> VoiceCallTicket {
            try JSONDecoder().decode(VoiceCallTicket.self, from: JSONSerialization.data(withJSONObject: payload))
        }
        XCTAssertNoThrow(try TwinVoiceCallModel.validate(ticket()))
        payload["bot_identity"] = "unbound-bot"
        XCTAssertThrowsError(try TwinVoiceCallModel.validate(ticket()))
        payload["bot_identity"] = "twin_" + identifier; payload["livekit_url"] = "wss://other.invalid"
        XCTAssertThrowsError(try TwinVoiceCallModel.validate(ticket()))
        payload.removeValue(forKey: "livekit_url"); payload["transport"] = "unknown-provider"
        XCTAssertThrowsError(try TwinVoiceCallModel.validate(ticket()))
    }
    func testConversationTLVRequiresExactFrameLengthAndKnownState() throws {
        let json = try JSONSerialization.data(withJSONObject: ["TaskId":"vc_fixture", "RoundID":2,
            "EventTime":1234, "Stage":["Code":3]])
        var packet = Data("conv".utf8)
        let length = UInt32(json.count)
        packet.append(contentsOf: [UInt8(length >> 24), UInt8((length >> 16) & 255), UInt8((length >> 8) & 255), UInt8(length & 255)])
        packet.append(json)
        let event = VolcengineVoiceTransport.decode(packet)
        XCTAssertEqual(event?.Stage.Code, 3); XCTAssertEqual(event?.RoundID, 2)
        XCTAssertNil(VolcengineVoiceTransport.decode(packet + Data([0])))
        XCTAssertNil(VolcengineVoiceTransport.decode(packet.dropLast()))
        packet[0] = 0
        XCTAssertNil(VolcengineVoiceTransport.decode(packet))
    }
    func testProviderTaskFailureAcceptsActualAndDocumentedNumericErrorCodeKeys() throws {
        for key in ["ErrorCode", "Code"] {
            let json = try JSONSerialization.data(withJSONObject: ["TaskId":"vc_fixture", "RoundID":0,
                "EventTime":1234, "Stage":["Code":0],
                "ErrorInfo":[key:1000002,"Reason":"private provider detail is not a displayed message"]])
            var packet = Data("conv".utf8)
            let length = UInt32(json.count)
            packet.append(contentsOf:[UInt8(length >> 24),UInt8((length >> 16) & 255),UInt8((length >> 8) & 255),UInt8(length & 255)])
            packet.append(json)
            XCTAssertEqual(VolcengineVoiceTransport.decode(packet)?.ErrorInfo?.numericCode,1000002)
        }
    }
}

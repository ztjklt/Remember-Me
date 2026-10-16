import XCTest
import AVFoundation
@testable import RememberMe

@MainActor
private final class SpeakerRecorderFixture: SpeakerAudioRecording {
    var currentTime: TimeInterval = 42
    var startCount = 0
    var stopCount = 0
    var file: URL?
    var finished: (@MainActor (Bool) -> Void)?
    var prepareAction: (() throws -> Void)?
    func prepare() throws {
        if let file { try DomesticMicrophoneBuffer.wave(Data(repeating: 0, count: 64000)).write(to: file) }
        try prepareAction?()
    }
    func start() -> Bool { startCount += 1; return true }
    func stop() { stopCount += 1 }
}

@MainActor
private final class SpeakerPlayerFixture: SpeakerAudioPlayback {
    var currentTime: TimeInterval = 0
    let duration: TimeInterval = 2
    var stopCount = 0
    func play() -> Bool { true }
    func stop() { stopCount += 1 }
}

private final class SpeakerAPIProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var body = Data()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        if let body = request.httpBody { Self.body = body }
        else if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }; var bytes = [UInt8](repeating: 0, count: 4096), body = Data()
            while stream.hasBytesAvailable { let count = stream.read(&bytes, maxLength: bytes.count); if count <= 0 { break }; body.append(bytes, count: count) }
            Self.body = body
        }
        let data = Data(#"{"recording_id":"fixture-group","status":"uploaded","recorded_at":"2026-10-15T00:00:00Z","duration_ms":10000,"consent_id":"speaker-consent","policy":"speaker-policy","error":null,"report":null}"#.utf8)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 201, httpVersion: nil, headerFields: ["Content-Type":"application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }
}

@MainActor
final class SpeakerRecordingTests: XCTestCase {
    private func pairing(_ subject: String = "subject") -> Pairing {
        Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64), token: "fixture", actorID: "actor", subjectID: subject, consentID: "recording")
    }
    func testArchiveRestoresRequestAndSeparatesPeopleAndServices() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let archive = SpeakerLocalArchive(root: root); try archive.prepare()
        let record = LocalSpeakerRecording(id: UUID().uuidString, owner: RecordingOwner(pairing()), recordedAt: Date(), durationMS: 10000,
            speakerCount: 3, participantsConsentedAt: Date(), consentID: "separate-speaker-grant", policy: "bound-policy", remoteID: "remote")
        try Data("synthetic-audio".utf8).write(to: archive.file(record.id)); try archive.save(record)
        let restored = SpeakerLocalArchive(root: root)
        XCTAssertEqual(restored.visible(to: pairing()).first?.remoteID, "remote")
        XCTAssertEqual(restored.records.first?.speakerCount, 3)
        XCTAssertTrue(restored.visible(to: pairing("other")).isEmpty)
        XCTAssertTrue(restored.visible(to: nil).isEmpty)
        XCTAssertEqual(restored.records.first?.consentID, "separate-speaker-grant")
        try restored.remove(record.id); XCTAssertTrue(restored.records.isEmpty)
    }
    func testParticipantConsentAndDeniedMicrophoneCannotCreateAudio() async {
        let workspace = SpeakerRecordingWorkspace(permission: { false })
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let archive = SpeakerLocalArchive(root: root)
        await workspace.start(pairing: pairing(), archive: archive, consented: false)
        XCTAssertNil(workspace.local)
        await workspace.start(pairing: pairing(), archive: archive, consented: true)
        XCTAssertNil(workspace.local); XCTAssertFalse(workspace.recording)
        XCTAssertTrue(workspace.error?.contains("麦克风") == true)
    }
    func testBackgroundCancellationPreventsRecordingAfterPermissionReturns() async {
        var prompt: CheckedContinuation<Bool, Never>?
        let workspace = SpeakerRecordingWorkspace(permission: { await withCheckedContinuation { prompt = $0 } })
        let archive = SpeakerLocalArchive(root: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let task = Task { await workspace.start(pairing: pairing(), archive: archive, consented: true) }
        while prompt == nil { await Task.yield() }
        workspace.cancelPendingStart(); prompt?.resume(returning: true); await task.value
        XCTAssertNil(workspace.local); XCTAssertFalse(workspace.recording)
    }
    func testPermissionCompletionOutsideForegroundCannotOpenMicrophone() async {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let workspace = SpeakerRecordingWorkspace(permission: { true }, isApplicationActive: { false },
            recorderFactory: { _, _ in XCTFail("Must not create a recorder in background"); return SpeakerRecorderFixture() })
        await workspace.start(pairing: pairing(), archive: SpeakerLocalArchive(root: root), consented: true)
        XCTAssertNil(workspace.local); XCTAssertFalse(workspace.captureActive); XCTAssertFalse(workspace.busy)
    }
    func testSystemResetFinalizesActualOriginalAndReleasesCaptureState() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let archive = SpeakerLocalArchive(root: root), recorder = SpeakerRecorderFixture()
        let workspace = SpeakerRecordingWorkspace(permission: { true }, isApplicationActive: { true }, recorderFactory: { file, finished in
            recorder.file = file; recorder.finished = finished; return recorder
        })
        await workspace.start(pairing: pairing(), archive: archive, consented: true)
        XCTAssertTrue(workspace.captureActive); XCTAssertEqual(recorder.startCount, 1)
        NotificationCenter.default.post(name: AVAudioSession.mediaServicesWereResetNotification, object: nil)
        for _ in 0..<1000 { if !workspace.recording { break }; await Task.yield() }
        XCTAssertFalse(workspace.captureActive)
        XCTAssertEqual(workspace.local?.durationMS, 2000, "Use real saved frames rather than the fixture's stale recorder clock")
        XCTAssertEqual(archive.records.first?.durationMS, 2000)
        XCTAssertEqual(recorder.stopCount, 1)
        XCTAssertTrue(workspace.error?.contains("重置") == true)
        XCTAssertTrue(FileManager.default.fileExists(atPath: try XCTUnwrap(recorder.file).path))
    }
    func testOldRecorderCompletionAndTimerCannotStopReplacement() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let archive = SpeakerLocalArchive(root: root)
        var recorders: [SpeakerRecorderFixture] = []
        let workspace = SpeakerRecordingWorkspace(permission: { true }, isApplicationActive: { true }, recorderFactory: { file, finished in
            let recorder = SpeakerRecorderFixture(); recorder.file = file; recorder.finished = finished
            recorders.append(recorder); return recorder
        })
        await workspace.start(pairing: pairing(), archive: archive, consented: true)
        workspace.finish(archive: archive); workspace.local = nil
        await workspace.start(pairing: pairing(), archive: archive, consented: true)
        recorders[1].currentTime = 3
        recorders[0].finished?(false)
        XCTAssertTrue(workspace.recording); XCTAssertEqual(recorders[1].stopCount, 0)
        try await Task.sleep(for: .milliseconds(550))
        XCTAssertEqual(workspace.seconds, 3)
        workspace.finish(archive: archive)
        XCTAssertFalse(workspace.captureActive)
        XCTAssertEqual(archive.records.count, 2)
    }
    func testJournalFailureNeverStartsMicrophoneAndFinalSaveFailureRetainsAudioForRetry() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let archive = SpeakerLocalArchive(root: root), recorder = SpeakerRecorderFixture()
        var blockJournal = true
        let workspace = SpeakerRecordingWorkspace(permission: { true }, isApplicationActive: { true }, recorderFactory: { file, finished in
            recorder.file = file; recorder.finished = finished
            recorder.prepareAction = {
                if blockJournal { try FileManager.default.createDirectory(at: file.deletingPathExtension().appendingPathExtension("group.json"), withIntermediateDirectories: true) }
            }
            return recorder
        })
        await workspace.start(pairing: pairing(), archive: archive, consented: true)
        XCTAssertEqual(recorder.startCount, 0); XCTAssertEqual(recorder.stopCount, 1)
        XCTAssertFalse(workspace.captureActive)
        blockJournal = false
        await workspace.start(pairing: pairing(), archive: archive, consented: true)
        let local = try XCTUnwrap(workspace.local), file = archive.file(local.id)
        let original = try Data(contentsOf: file)
        let sidecar = root.appendingPathComponent(local.id + ".group.json")
        try FileManager.default.removeItem(at: sidecar)
        try FileManager.default.createDirectory(at: sidecar, withIntermediateDirectories: true)
        workspace.finish(archive: archive)
        XCTAssertTrue(workspace.archiveSavePending); XCTAssertFalse(workspace.captureActive)
        XCTAssertEqual(workspace.local?.durationMS, 2000); XCTAssertEqual(try Data(contentsOf: file), original)
        try FileManager.default.removeItem(at: sidecar)
        workspace.retryArchiveSave(archive: archive)
        XCTAssertFalse(workspace.archiveSavePending)
        XCTAssertEqual(archive.records.first(where: { $0.id == local.id })?.durationMS, 2000)
        XCTAssertEqual(try Data(contentsOf: file), original)
    }
    func testSegmentPlaybackDeadlineCannotStopReplacementAndRejectsInvalidInterval() async throws {
        let local = LocalSpeakerRecording(id: UUID().uuidString, owner: RecordingOwner(pairing()), recordedAt: Date(), durationMS: 2000, participantsConsentedAt: Date())
        var players: [SpeakerPlayerFixture] = []
        let workspace = SpeakerRecordingWorkspace(local: local, playerFactory: { _ in
            let player = SpeakerPlayerFixture(); players.append(player); return player
        })
        let archive = SpeakerLocalArchive(root: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let segment = SpeakerSegment(segment_id: "short", start_ms: 0, end_ms: 10, text: "fixture", speaker_id: nil, speaker_name: nil, attribution: "unidentified", overlap: false)
        workspace.play(archive: archive, segment: segment)
        workspace.play(archive: archive)
        try await Task.sleep(for: .milliseconds(30))
        XCTAssertEqual(players[0].stopCount, 1); XCTAssertEqual(players[1].stopCount, 0)
        let invalid = SpeakerSegment(segment_id: "bad", start_ms: 20, end_ms: 10, text: "fixture", speaker_id: nil, speaker_name: nil, attribution: "unidentified", overlap: false)
        workspace.play(archive: archive, segment: invalid)
        XCTAssertNotNil(workspace.error); XCTAssertEqual(players[1].stopCount, 1)
        workspace.stopPlayback()
    }
    func testGroupRecordingBlocksChangingAccountAndOtherRecorders() async {
        let model = AppModel(pairing: pairing(), recordPermission: { XCTFail("Already recording in group mode"); return false })
        model.isSpeakerRecording = true
        XCTAssertTrue(model.connectionChangeBlocked)
        XCTAssertFalse(model.applyConnection(pairing("other"), persist: false))
        await model.startRecording(); XCTAssertNil(model.draft)
    }
    func testMultipartCarriesDedicatedConsentPolicyAndCountWithoutNamesOrProviderSecrets() async throws {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [SpeakerAPIProtocol.self]
        let api = try APIClient(baseURL: pairing().baseURL, fingerprint: pairing().fingerprint, token: "fixture-actor-token", session: URLSession(configuration: config))
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
        defer { try? FileManager.default.removeItem(at: file) }
        try Data("synthetic-audio-only".utf8).write(to: file)
        let local = LocalSpeakerRecording(id: UUID().uuidString, owner: RecordingOwner(pairing()), recordedAt: Date(), durationMS: 10000,
            speakerCount: 3, participantsConsentedAt: Date())
        let reply = try await api.uploadSpeakerRecording(local, file: file, subject: "subject", consent: "speaker-consent", policy: "speaker-policy")
        XCTAssertEqual(reply.id, "fixture-group")
        let body = String(decoding: SpeakerAPIProtocol.body, as: UTF8.self)
        XCTAssertTrue(body.contains("speaker-consent")); XCTAssertTrue(body.contains("speaker-policy"))
        XCTAssertTrue(body.contains("name=\"speaker_count\"\r\n\r\n3"))
        XCTAssertTrue(body.contains("name=\"participant_consents_confirmed\"\r\n\r\ntrue"))
        XCTAssertTrue(body.contains("synthetic-audio-only"))
        XCTAssertFalse(body.contains("speaker_name")); XCTAssertFalse(body.contains("fixture-actor-token"))
    }
}


@MainActor
final class NaturalSpeakerDisplayTests: XCTestCase {
    func testUnintroducedSpeakerKeepsStableNumberAndUsableText() throws {
        let data = Data(#"{"segment_id":"s","start_ms":100,"end_ms":4000,"text":"那天我们去散步。","speaker_id":"speaker_1","speaker_name":null,"attribution":"unidentified","overlap":false}"#.utf8)
        let segment = try JSONDecoder().decode(SpeakerSegment.self, from: data)
        XCTAssertEqual(segment.label, "说话人 2")
        XCTAssertEqual(segment.text, "那天我们去散步。")
    }
    func testTextOnlyFallbackDoesNotPretendExactTimingOrIdentity() throws {
        let data = Data(#"{"segment_id":"s","start_ms":0,"end_ms":5000,"text":"可用的原话","speaker_id":null,"speaker_name":null,"attribution":"unidentified","overlap":false,"timing_estimated":true}"#.utf8)
        let segment = try JSONDecoder().decode(SpeakerSegment.self, from: data)
        XCTAssertTrue(segment.timing_estimated == true)
        XCTAssertEqual(segment.label, "发言（说话人暂未分清）")
    }
}

import XCTest
import Foundation
import AVFoundation
@testable import RememberMe

private final class RecordingDeleteProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var status = 503
    nonisolated(unsafe) static var body = Data()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let deleting = request.httpMethod == "DELETE"
        let status = deleting ? Self.status : 503
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: deleting ? Self.body : Data())
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
private final class StubSpeech: LocalSpeechTranscriber {
    var result: Result<String, Error> = .success("我喜欢散步。")
    func transcribe(_ file: URL) async throws -> String { try result.get() }
}

@MainActor
final class LocalRecordingTests: XCTestCase {
    func testArchivedAudioCannotStealTheAudioSessionFromGroupRecording() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = try meteredRecording(store, amplitudes: [0.2, 0.2])
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        model.isSpeakerRecording = true
        let category = AVAudioSession.sharedInstance().category
        model.playLocalRecording(record.id)
        XCTAssertFalse(model.isPlaying)
        XCTAssertNil(model.playbackID)
        XCTAssertEqual(AVAudioSession.sharedInstance().category, category)
        XCTAssertTrue(FileManager.default.fileExists(atPath: record.draft.fileURL.path))
    }
    func testPlaybackMeterUsesRealAudioAndClearsOnPauseStopAndLateTimer() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = try meteredRecording(store, amplitudes: Array(repeating: 0.25, count: 6))
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        defer { model.stopPlayback() }
        XCTAssertNil(model.playbackAudioLevel)
        model.playLocalRecording(record.id)
        XCTAssertTrue(model.isPlaying, model.errorMessage ?? "Playback did not start")
        for _ in 0..<80 {
            if (model.playbackAudioLevel ?? 0) > 0 { break }
            try await Task.sleep(for: .milliseconds(25))
        }
        XCTAssertGreaterThan(try XCTUnwrap(model.playbackAudioLevel), 0)
        model.pausePlayback()
        XCTAssertNil(model.playbackAudioLevel)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertNil(model.playbackAudioLevel)
        model.toggleCurrentPlayback()
        for _ in 0..<40 {
            if (model.playbackAudioLevel ?? 0) > 0 { break }
            try await Task.sleep(for: .milliseconds(25))
        }
        XCTAssertGreaterThan(try XCTUnwrap(model.playbackAudioLevel), 0)
        model.stopPlayback()
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertNil(model.playbackAudioLevel)
        XCTAssertNil(model.playbackID)
    }
    func testPlaybackMeterFallsBackToZeroDuringActualSilenceAndNilAtEnd() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = try meteredRecording(store, amplitudes: [0.25, 0.25, 0, 0])
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        defer { model.stopPlayback() }
        model.playLocalRecording(record.id)
        var sawAudio = false, sawSilence = false
        for _ in 0..<140 {
            if let level = model.playbackAudioLevel {
                if level > 0.05 { sawAudio = true }
                else if sawAudio && model.isPlaying { sawSilence = true }
            }
            if !model.isPlaying { break }
            try await Task.sleep(for: .milliseconds(25))
        }
        XCTAssertTrue(sawAudio)
        XCTAssertTrue(sawSilence)
        XCTAssertFalse(model.isPlaying)
        XCTAssertNil(model.playbackAudioLevel)
    }
    func testPlaybackPowerRejectsInvalidValuesAndClampsMeasuredRange() {
        XCTAssertEqual(AppModel.normalizedPlaybackPower(.nan), 0)
        XCTAssertEqual(AppModel.normalizedPlaybackPower(.infinity), 0)
        XCTAssertEqual(AppModel.normalizedPlaybackPower(-160), 0)
        XCTAssertEqual(AppModel.normalizedPlaybackPower(-60), 0)
        XCTAssertEqual(AppModel.normalizedPlaybackPower(-30), 0.5, accuracy: 0.001)
        XCTAssertEqual(AppModel.normalizedPlaybackPower(12), 1)
    }
    private func meteredRecording(_ store: LocalRecordingStore, amplitudes: [Double]) throws -> LocalRecording {
        let id = UUID().uuidString
        let draft = RecordingDraft(id: id, fileURL: store.root.appendingPathComponent(id + ".wav"), recordedAt: Date(),
                                   durationMS: amplitudes.count * 500, questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        let record = LocalRecording(draft: draft, owner: nil)
        try store.save(record)
        var samples = [Int16]()
        for amplitude in amplitudes {
            for index in 0..<8000 {
                samples.append(Int16(sin(Double(index) * 2 * .pi * 440 / 16000) * amplitude * 32767).littleEndian)
            }
        }
        try samples.withUnsafeBytes { try DomesticMicrophoneBuffer.wave(Data($0)).write(to: draft.fileURL) }
        return record
    }
    func testReadingPromptRestoresOnlyForSampleOwnerAndDoesNotLeakIntoOtherSamples() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        try FileManager.default.createDirectory(at: store.root, withIntermediateDirectories: true)
        let sample = store.root.appendingPathComponent("reading-fixture.m4a")
        try Data().write(to: sample)
        let owner = pairing()
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: owner)
        model.retainVoiceSample(sample, owner: RecordingOwner(owner), transcript: AppModel.voiceReadingPrompt,
                                readingPrompt: AppModel.voiceReadingPrompt)
        let restored = AppModel(recordingStore: store, defaults: defaults, pairing: owner)
        XCTAssertEqual(restored.voiceSampleReadingPrompt, AppModel.voiceReadingPrompt)
        XCTAssertEqual(restored.voiceSampleTranscript, AppModel.voiceReadingPrompt)
        let other = AppModel(recordingStore: store, defaults: defaults, pairing: pairing("other"))
        XCTAssertNil(other.voiceSampleURL); XCTAssertNil(other.voiceSampleReadingPrompt)
        // An interrupted or free-speech sample must not inherit a previous prompt.
        model.retainVoiceSample(sample, owner: RecordingOwner(owner), transcript: "")
        let interrupted = AppModel(recordingStore: store, defaults: defaults, pairing: owner)
        XCTAssertNil(interrupted.voiceSampleReadingPrompt); XCTAssertEqual(interrupted.voiceSampleTranscript, "")
    }
    func testEditedVoiceSampleTranscriptRestoresWithSameOwnerAfterRelaunch() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let owner = pairing()
        try FileManager.default.createDirectory(at: store.root, withIntermediateDirectories: true)
        let sample = store.root.appendingPathComponent("voice-fixture.m4a")
        try Data().write(to: sample)
        defaults.set(sample.path, forKey: "pending-voice-sample")
        defaults.set(try JSONEncoder().encode(RecordingOwner(owner)), forKey: "pending-voice-owner")
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: owner)
        model.voiceSampleTranscript = "今天我留下自己的声音。"
        model.saveVoiceSampleTranscript(model.voiceSampleTranscript)
        let restored = AppModel(recordingStore: store, defaults: defaults, pairing: owner)
        XCTAssertEqual(restored.voiceSampleURL, sample)
        XCTAssertEqual(restored.voiceSampleTranscript, "今天我留下自己的声音。")
        let other = AppModel(recordingStore: store, defaults: defaults, pairing: pairing("another-subject"))
        XCTAssertNil(other.voiceSampleURL)
        XCTAssertEqual(other.voiceSampleTranscript, "")
    }
    func testDirectStartRequestsPermissionOnceAndDenialCreatesNoRecording() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        var calls = 0
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil,
                             recordPermission: { calls += 1; return false })
        await model.startRecording()
        XCTAssertEqual(calls, 1); XCTAssertNil(model.draft); XCTAssertFalse(model.isRecording)
        XCTAssertFalse(model.isStartingRecording); XCTAssertTrue(model.localRecordings.isEmpty)
        XCTAssertTrue(model.errorMessage?.contains("麦克风权限已拒绝") == true)
    }
    func testRepeatedTapDuringPermissionPromptCannotCreateSecondRecorder() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        var permission: CheckedContinuation<Bool, Never>?
        var calls = 0
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil,
            recordPermission: { calls += 1; return await withCheckedContinuation { permission = $0 } })
        let pending = Task { await model.startRecording() }
        while permission == nil { await Task.yield() }
        XCTAssertTrue(model.connectionChangeBlocked); XCTAssertFalse(model.prepareNewRecording())
        await model.startRecording(); XCTAssertEqual(calls, 1)
        permission?.resume(returning: false); await pending.value
        XCTAssertNil(model.draft); XCTAssertFalse(model.isStartingRecording)
    }
    func testOfflineAutoTranscriptionStopsForReviewAndPreservesMachineOriginal() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = recording(store.root); try store.save(record)
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults, pairing: nil)
        XCTAssertTrue(model.selectLocalRecording(record.id))
        let policy = await model.transcribeFinishedRecordingAutomatically(); XCTAssertNil(policy)
        XCTAssertTrue(model.isTranscriptReviewReady); XCTAssertEqual(model.transcriptDraft, "我喜欢散步。")
        model.transcriptDraft = "我喜欢晚饭后散步。"; model.saveTranscriptDraft()
        await model.submitTranscript()
        let saved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(saved.machineTranscript, "我喜欢散步。")
        XCTAssertEqual(saved.reviewedTranscript, "我喜欢晚饭后散步。")
        XCTAssertNil(saved.episodeID); XCTAssertFalse(model.isTranscriptReviewReady)
    }
    func testAutoTranscriptionCanBeDisabledButExplicitLocalRetryStillWorks() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = recording(store.root); try store.save(record)
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults, pairing: nil)
        XCTAssertTrue(model.selectLocalRecording(record.id)); model.automaticTranscriptionEnabled = false
        _ = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertNil(model.localRecordings.first(where: { $0.id == record.id })?.machineTranscript); XCTAssertEqual(model.draft?.id, record.id)
        _ = await model.transcribeFinishedRecordingAutomatically(force: true)
        XCTAssertTrue(model.isTranscriptReviewReady)
    }
    func testOfflineTranscriptionFailureRetainsOriginalForRetry() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = recording(store.root); try store.save(record)
        let speech = StubSpeech(); speech.result = .failure(LocalSpeechError.unavailable)
        let model = AppModel(recordingStore: store, localSpeech: speech, defaults: defaults, pairing: nil)
        XCTAssertTrue(model.selectLocalRecording(record.id))
        _ = await model.transcribeFinishedRecordingAutomatically()
        XCTAssertFalse(model.isTranscriptReviewReady); XCTAssertEqual(model.draft?.id, record.id)
        XCTAssertEqual(try store.load().recordings.count, 1); XCTAssertNotNil(model.errorMessage)
    }
    func testDeleteLocalRecordingErasesOnlyChosenOriginalAndClearsPendingDraft() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let chosen = recording(store.root), kept = recording(store.root)
        try store.save(chosen); try store.save(kept)
        try Data([1, 2]).write(to: chosen.draft.fileURL)
        try Data([3, 4]).write(to: kept.draft.fileURL)
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        XCTAssertTrue(model.selectLocalRecording(chosen.id))
        let deleted = await model.deleteRecording(localID: chosen.id, owner: nil); XCTAssertTrue(deleted)
        XCTAssertNil(model.draft); XCTAssertNil(defaults.data(forKey: "pending-recording"))
        XCTAssertFalse(FileManager.default.fileExists(atPath: chosen.draft.fileURL.path))
        XCTAssertEqual(try Data(contentsOf: kept.draft.fileURL), Data([3, 4]))
        let restored = AppModel(recordingStore: store, defaults: defaults, pairing: nil)
        XCTAssertEqual(restored.localRecordings.map(\.id), [kept.id])
    }

    func testDeletionRejectsOtherOwnerBusyStateAndUnrelatedAudioFilename() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let a = pairing("subject-a"), b = pairing("subject-b")
        let chosen = recording(store.root, owner: RecordingOwner(a))
        try store.save(chosen); try Data([1, 2]).write(to: chosen.draft.fileURL)
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: b)
        let otherResult = await model.deleteRecording(localID: chosen.id, owner: RecordingOwner(b)); XCTAssertFalse(otherResult)
        let own = AppModel(recordingStore: store, defaults: defaults, pairing: a)
        own.isBusy = true
        let busyResult = await own.deleteRecording(localID: chosen.id, owner: RecordingOwner(a)); XCTAssertFalse(busyResult)
        own.isBusy = false
        let staleOwnerResult = await own.deleteRecording(localID: chosen.id, owner: RecordingOwner(b)); XCTAssertFalse(staleOwnerResult)
        XCTAssertTrue(FileManager.default.fileExists(atPath: chosen.draft.fileURL.path))
        let bad = LocalRecording(draft: RecordingDraft(id: UUID().uuidString, fileURL: chosen.draft.fileURL,
            recordedAt: Date(), durationMS: 12000, questionID: nil, calibrationID: nil, consentConfirmedAt: Date()))
        XCTAssertThrowsError(try store.remove(bad))
        XCTAssertTrue(FileManager.default.fileExists(atPath: chosen.draft.fileURL.path))
    }

    func testCloudDeletionFailureKeepsLocalOriginalAndCanRetryCleanupReceipt() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let owner = pairing()
        var chosen = recording(store.root, owner: RecordingOwner(owner)); chosen.episodeID = "ep-delete"
        try store.save(chosen); try Data([1, 2]).write(to: chosen.draft.fileURL)
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [RecordingDeleteProtocol.self]
        let api = try APIClient(baseURL: owner.baseURL, fingerprint: owner.fingerprint, session: URLSession(configuration: config))
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: owner, apiClientFactory: { _ in api })
        RecordingDeleteProtocol.status = 503; RecordingDeleteProtocol.body = Data()
        let unavailable = await model.deleteRecording(localID: chosen.id, owner: RecordingOwner(owner))
        XCTAssertFalse(unavailable); XCTAssertEqual(model.localRecordings.count, 1)
        XCTAssertEqual(try Data(contentsOf: chosen.draft.fileURL), Data([1, 2]))
        RecordingDeleteProtocol.status = 200
        RecordingDeleteProtocol.body = Data(#"{"deleted":true,"cleanup_pending":true}"#.utf8)
        let cleanupPending = await model.deleteRecording(localID: chosen.id, owner: RecordingOwner(owner))
        XCTAssertFalse(cleanupPending); XCTAssertEqual(try store.load().recordings.count, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: chosen.draft.fileURL.path))
        RecordingDeleteProtocol.body = Data(#"{"deleted":true,"cleanup_pending":false}"#.utf8)
        let complete = await model.deleteRecording(localID: chosen.id, owner: RecordingOwner(owner))
        XCTAssertTrue(complete); XCTAssertTrue(model.localRecordings.isEmpty)
        XCTAssertTrue(try store.load().recordings.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: chosen.draft.fileURL.path))
    }

    private func setup() throws -> (LocalRecordingStore, UserDefaults, String) {
        let name = "remember-local-tests-" + UUID().uuidString
        let store = LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(name))
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        return (store, defaults, name)
    }
    private func clean(_ store: LocalRecordingStore, _ defaults: UserDefaults, _ suite: String) {
        try? FileManager.default.removeItem(at: store.root)
        defaults.removePersistentDomain(forName: suite)
    }
    private func recording(_ root: URL, date: Date = Date(), owner: RecordingOwner? = nil) -> LocalRecording {
        let id = UUID().uuidString
        return LocalRecording(draft: RecordingDraft(id: id, fileURL: root.appendingPathComponent(id + ".m4a"),
            recordedAt: date, durationMS: 12000, questionID: "question-fixture", calibrationID: "calibration-fixture",
            consentConfirmedAt: date), owner: owner)
    }
    private func pairing(_ subject: String = "subject-fixture", actor: String = "actor-fixture",
                         server: String = "https://local.invalid") -> Pairing {
        Pairing(baseURL: server, fingerprint: String(repeating: "a", count: 64), token: "test-only",
                actorID: actor, subjectID: subject, consentID: "consent-fixture")
    }
    func testRetainedVoiceSampleRestoresOnlyForItsRecordedOwner() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        try FileManager.default.createDirectory(at: store.root, withIntermediateDirectories: true)
        let a = pairing("subject-a"), b = pairing("subject-b")
        let sampleA = store.root.appendingPathComponent("synthetic-a.m4a")
        let sampleB = store.root.appendingPathComponent("synthetic-b.m4a")
        try Data([0,1,2]).write(to:sampleA); try Data([3,4,5]).write(to:sampleB)
        let modelA = AppModel(recordingStore:store, defaults:defaults, pairing:a)
        modelA.retainVoiceSample(sampleA, owner:RecordingOwner(a), transcript:"")
        XCTAssertEqual(AppModel(recordingStore:store, defaults:defaults, pairing:a).voiceSampleURL,sampleA)
        let modelB = AppModel(recordingStore:store, defaults:defaults, pairing:b)
        XCTAssertNil(modelB.voiceSampleURL)
        modelB.retainVoiceSample(sampleB, owner:RecordingOwner(b), transcript:"")
        XCTAssertNil(AppModel(recordingStore:store, defaults:defaults, pairing:a).voiceSampleURL)
        XCTAssertEqual(AppModel(recordingStore:store, defaults:defaults, pairing:b).voiceSampleURL,sampleB)
    }
    func testBackgroundCancelsPendingVoicePermissionAndCannotAffectNewScope() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        var permission: CheckedContinuation<Bool, Never>?
        let model = AppModel(recordingStore:store, defaults:defaults, pairing:pairing("subject-a"),
            recordPermission:{ await withCheckedContinuation { permission = $0 } })
        let pending = Task { await model.startVoiceSample() }
        while permission == nil { await Task.yield() }
        XCTAssertTrue(model.connectionChangeBlocked)
        model.stopAuxiliaryForBackground()
        XCTAssertTrue(model.applyConnection(pairing("subject-b"),persist:false))
        permission?.resume(returning:false); await pending.value
        XCTAssertEqual(model.pairing?.subjectID,"subject-b"); XCTAssertFalse(model.isVoiceRecording)
        XCTAssertFalse(model.errorMessage?.contains("麦克风权限已拒绝") == true)
    }

    func testMultipleRecordingsAndReviewedTextSurviveReload() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        var first = recording(store.root, date: Date(timeIntervalSince1970: 1))
        first.machineTranscript = "我喜欢山步。"; first.reviewedTranscript = "我喜欢散步。"
        first.reviewedAt = Date(); first.episodeID = "episode-fixture"; first.status = "ready"
        let second = recording(store.root, date: Date(timeIntervalSince1970: 2))
        try store.save(first); try store.save(second)
        let loaded = try store.load().recordings
        XCTAssertEqual(loaded.map(\.id), [second.id, first.id])
        XCTAssertEqual(loaded[1].machineTranscript, "我喜欢山步。")
        XCTAssertEqual(loaded[1].reviewedTranscript, "我喜欢散步。")
        XCTAssertEqual(loaded[1].episodeID, "episode-fixture")
        XCTAssertEqual(loaded[1].draft.calibrationID, first.draft.calibrationID)
    }

    func testDamagedMetadataDoesNotHideOtherRecordingsOrDeleteAudio() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let first = recording(store.root); try store.save(first)
        try Data([1, 2]).write(to: first.draft.fileURL)
        try Data("invalid".utf8).write(to: store.root.appendingPathComponent("damaged.recording.json"))
        let loaded = try store.load()
        XCTAssertEqual(loaded.recordings.map(\.id), [first.id])
        XCTAssertEqual(loaded.unreadableCount, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: first.draft.fileURL.path))
    }

    func testContainerRelocationPreservesIdentityAndConsent() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let original = recording(URL(fileURLWithPath: "/old-container/Recordings"))
        try store.save(original)
        let moved = store.root.appendingPathComponent(original.draft.fileURL.lastPathComponent)
        try Data([1]).write(to: moved)
        let resolved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(resolved.draft.fileURL, moved)
        XCTAssertEqual(resolved.id, original.id)
        XCTAssertEqual(resolved.draft.questionID, original.draft.questionID)
        XCTAssertEqual(resolved.draft.consentConfirmedAt, original.draft.consentConfirmedAt)
    }

    func testMissingAudioKeepsTheRecordVisibleForRecovery() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = recording(store.root); try store.save(record)
        XCTAssertEqual(try store.load().recordings.first?.id, record.id)
    }

    func testSubjectActorAndServiceIsolation() {
        let owner = pairing()
        let bound = recording(URL(fileURLWithPath: "/fixture"), owner: RecordingOwner(owner))
        XCTAssertTrue(bound.isVisible(to: owner))
        XCTAssertFalse(bound.isVisible(to: nil))
        XCTAssertFalse(bound.isVisible(to: pairing("other-subject")))
        XCTAssertFalse(bound.isVisible(to: pairing(actor: "other-actor")))
        XCTAssertFalse(bound.isVisible(to: pairing(server: "https://other.invalid")))
        XCTAssertTrue(recording(URL(fileURLWithPath: "/fixture")).isVisible(to: nil))
    }

    func testLegacyPendingDraftIsImportedWithoutLosingEpisodeOrLinks() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let old = recording(store.root)
        defaults.set(try JSONEncoder().encode(old.draft), forKey: "pending-recording")
        defaults.set("episode-fixture", forKey: "pending-episode")
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults, pairing: pairing())
        XCTAssertEqual(model.localRecordings.first?.id, old.id)
        XCTAssertEqual(model.localRecordings.first?.episodeID, "episode-fixture")
        XCTAssertEqual(model.draft?.calibrationID, "calibration-fixture")
    }

    func testSwitchingAndStartingNewKeepsEachEpisodeAndOriginal() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        var first = recording(store.root); first.episodeID = "episode-one"; first.status = "reviewing"
        let second = recording(store.root)
        try store.save(first); try store.save(second)
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults, pairing: nil)
        XCTAssertTrue(model.selectLocalRecording(first.id))
        XCTAssertEqual(model.episodeID, "episode-one")
        XCTAssertTrue(model.prepareNewRecording())
        XCTAssertNil(model.draft)
        XCTAssertTrue(model.selectLocalRecording(second.id))
        XCTAssertNil(model.episodeID)
        XCTAssertTrue(model.selectLocalRecording(first.id))
        XCTAssertEqual(model.episodeID, "episode-one")
        XCTAssertEqual(try store.load().recordings.count, 2)
    }

    func testBusyProcessingCannotSwitchOrReplaceDraft() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let first = recording(store.root); let second = recording(store.root)
        try store.save(first); try store.save(second)
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults, pairing: nil)
        XCTAssertTrue(model.selectLocalRecording(first.id))
        model.isBusy = true
        XCTAssertFalse(model.prepareNewRecording())
        XCTAssertFalse(model.selectLocalRecording(second.id))
        XCTAssertEqual(model.draft?.id, first.id)
        model.isBusy = false
        model.isPollingEpisode = true
        XCTAssertFalse(model.prepareNewRecording())
        XCTAssertFalse(model.selectLocalRecording(second.id))
        XCTAssertEqual(model.draft?.id, first.id)
    }

    func testRestoredActiveRecordingCannotExposeAnotherSubjectsAudio() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let old = recording(store.root, owner: RecordingOwner(pairing()))
        try store.save(old)
        defaults.set(try JSONEncoder().encode(old.draft), forKey: "pending-recording")
        defaults.set("old-episode", forKey: "pending-episode")
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults,
                             pairing: pairing("another-subject"))
        XCTAssertNil(model.draft)
        XCTAssertNil(model.episodeID)
        XCTAssertTrue(model.visibleLocalRecordings.isEmpty)
        XCTAssertEqual(try store.load().recordings.first?.id, old.id)
    }

    func testLocalReviewPreservesMachineTextAndDoesNotCreateEpisode() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = recording(store.root); try store.save(record)
        let speech = StubSpeech()
        let model = AppModel(recordingStore: store, localSpeech: speech, defaults: defaults, pairing: nil)
        await model.transcribeLocalRecording(record.id)
        model.saveLocalReviewDraft(record.id, text: "我不喜欢散步。")
        XCTAssertNil(model.localRecordings.first?.reviewedAt)
        XCTAssertTrue(model.saveLocalReview(record.id, text: "我不喜欢散步。"))
        XCTAssertEqual(model.localRecordings.first?.machineTranscript, "我喜欢散步。")
        XCTAssertEqual(model.localRecordings.first?.reviewedTranscript, "我不喜欢散步。")
        XCTAssertNil(model.localRecordings.first?.episodeID)
        XCTAssertTrue(model.memories.isEmpty)
    }

    func testUnavailableOrEmptyLocalSpeechKeepsOriginalAndCanRetry() async throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let record = recording(store.root); try store.save(record)
        try Data([1, 2, 3]).write(to: record.draft.fileURL)
        let speech = StubSpeech(); speech.result = .failure(LocalSpeechError.unavailable)
        let model = AppModel(recordingStore: store, localSpeech: speech, defaults: defaults, pairing: nil)
        await model.transcribeLocalRecording(record.id)
        XCTAssertFalse(model.isLocalTranscribing)
        XCTAssertNotNil(model.errorMessage)
        XCTAssertEqual(model.localRecordings.first?.id, record.id)
        XCTAssertEqual(try Data(contentsOf: record.draft.fileURL), Data([1, 2, 3]))
        speech.result = .success(" ")
        await model.transcribeLocalRecording(record.id)
        XCTAssertNil(model.localRecordings.first?.machineTranscript)
        speech.result = .success("我喜欢散步。")
        await model.transcribeLocalRecording(record.id)
        XCTAssertEqual(model.localRecordings.first?.machineTranscript, "我喜欢散步。")
        XCTAssertNil(model.errorMessage)
    }

    private func episode(_ id: String, status: String) -> EpisodeRecord {
        EpisodeRecord(episode_id: id, status: status, source: "IOS_MIC", recorded_at: "2026-10-13T00:00:00Z",
                      duration_ms: 12000, transcript: nil, stt_backend: nil, stt_model_version: nil,
                      model_version: nil, error_code: nil)
    }

    func testCloudCompletionRefreshesLocalArchiveWithoutChangingOriginalOrOtherOwners() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let current = pairing()
        var own = recording(store.root, owner: RecordingOwner(current))
        own.episodeID = "episode-one"; own.status = "extracting"; own.reviewDraft = "本人核对文字"
        var other = recording(store.root, owner: RecordingOwner(pairing("other-subject")))
        other.episodeID = "episode-one"; other.status = "extracting"
        try store.save(own); try store.save(other)
        try Data([1, 2, 3]).write(to: own.draft.fileURL)
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults, pairing: current)
        XCTAssertTrue(model.selectLocalRecording(own.id))
        model.reconcileRecordingStatuses([episode("episode-one", status: "ready")], pairing: current)
        let stored = try store.load().recordings
        XCTAssertEqual(stored.first { $0.id == own.id }?.status, "ready")
        XCTAssertEqual(stored.first { $0.id == own.id }?.reviewDraft, "本人核对文字")
        XCTAssertEqual(stored.first { $0.id == other.id }?.status, "extracting")
        XCTAssertEqual(model.processingStatus, "ready")
        XCTAssertEqual(try Data(contentsOf: own.draft.fileURL), Data([1, 2, 3]))
        model.reconcileRecordingStatuses([episode("episode-one", status: "failed")], pairing: pairing("other-subject"))
        XCTAssertEqual(model.processingStatus, "ready")
    }

    func testCompletedRecordingDoesNotRemainAnActiveAgentTask() throws {
        let (store, defaults, suite) = try setup(); defer { clean(store, defaults, suite) }
        let model = AppModel(recordingStore: store, localSpeech: StubSpeech(), defaults: defaults, pairing: pairing())
        model.processingStatus = "ready"
        model.episodes = [episode("episode-one", status: "ready")]
        XCTAssertEqual(model.recordingActivitySummary, "1 段录音 · 已整理")
        model.episodes = [episode("episode-one", status: "reviewing")]
        XCTAssertEqual(model.recordingActivitySummary, "有录音待核对文字")
        model.episodes = [episode("episode-one", status: "failed")]
        XCTAssertEqual(model.recordingActivitySummary, "有录音未完成，可重试")
        model.episodes = [episode("episode-one", status: "transcribing")]
        XCTAssertEqual(model.recordingActivitySummary, "正在转写或整理录音")
    }
}

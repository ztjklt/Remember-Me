import XCTest
@testable import RememberMe

@MainActor
private final class StubSpeech: LocalSpeechTranscriber {
    var result: Result<String, Error> = .success("我喜欢散步。")
    func transcribe(_ file: URL) async throws -> String { try result.get() }
}

@MainActor
final class LocalRecordingTests: XCTestCase {
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
}

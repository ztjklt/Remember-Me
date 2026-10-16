import AVFoundation
import XCTest
@testable import RememberMe

@MainActor
private final class SpeechSessionFixture: LocalSpeechRecognitionSession {
    var cancellations = 0
    func cancel() { cancellations += 1 }
}

@MainActor
private final class SpeechDriverFixture: LocalSpeechRecognitionDriver {
    var supportsOnDeviceRecognition = true
    var permissions: [@MainActor @Sendable (Bool) -> Void] = []
    var callbacks: [@MainActor @Sendable (Result<String, Error>) -> Void] = []
    var sessions: [SpeechSessionFixture] = []
    var immediateResult: Result<String, Error>?
    func requestAuthorization(_ completion: @escaping @MainActor @Sendable (Bool) -> Void) { permissions.append(completion) }
    func start(_ file: URL, completion: @escaping @MainActor @Sendable (Result<String, Error>) -> Void) throws -> any LocalSpeechRecognitionSession {
        callbacks.append(completion)
        let session = SpeechSessionFixture(); sessions.append(session)
        if let immediateResult { completion(immediateResult) }
        return session
    }
}

@MainActor
private final class RecordingActivityFixture: RecordingLiveActivityHandle {
    let id: String
    var updates: [(RecordingActivityAttributes.ContentState, Date)] = []
    var ended = false
    var holdEnd = false
    var endContinuation: CheckedContinuation<Void, Never>?
    init(_ id: String) { self.id = id }
    func update(_ state: RecordingActivityAttributes.ContentState, staleDate: Date) async { updates.append((state, staleDate)) }
    func end() async {
        if holdEnd { await withCheckedContinuation { endContinuation = $0 } }
        ended = true
    }
}

@MainActor
private final class RecordingActivityBackendFixture: RecordingLiveActivityBackend {
    var available = true
    var created: [RecordingActivityFixture] = []
    var requests: [(String, RecordingActivityAttributes.ContentState, Date)] = []
    var activities: [any RecordingLiveActivityHandle] { created.filter { !$0.ended } }
    func request(id: String, state: RecordingActivityAttributes.ContentState, staleDate: Date) throws -> any RecordingLiveActivityHandle {
        requests.append((id, state, staleDate))
        let activity = RecordingActivityFixture(id); created.append(activity); return activity
    }
}

@MainActor
final class RecordingLifecycleTests: XCTestCase {
    private let file = URL(fileURLWithPath: "/isolated/recording.m4a")
    private func waitUntil(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        for _ in 0..<1000 {
            if condition() { return }
            await Task.yield()
        }
        XCTFail("Expected asynchronous state was not reached", file: file, line: line)
    }

    func testSpeechReservesOperationWhilePermissionIsPending() async throws {
        let driver = SpeechDriverFixture()
        let transcriber = OnDeviceSpeechTranscriber(driver: driver)
        let first = Task { try await transcriber.transcribe(file) }
        await waitUntil { driver.permissions.count == 1 }
        do { _ = try await transcriber.transcribe(file); XCTFail("A second operation must not replace the first continuation") }
        catch LocalSpeechError.busy { }
        XCTAssertEqual(driver.permissions.count, 1)
        driver.permissions[0](true); driver.callbacks[0](.success("  本人的原话。  "))
        let text = try await first.value
        XCTAssertEqual(text, "本人的原话。")
        XCTAssertEqual(driver.sessions[0].cancellations, 1)
    }

    func testCancellationDuringPermissionReturnsAndLateAuthorizationCannotStartSpeech() async {
        let driver = SpeechDriverFixture()
        let speech = OnDeviceSpeechTranscriber(driver: driver)
        let operation = Task { try await speech.transcribe(file) }
        await waitUntil { driver.permissions.count == 1 }
        operation.cancel()
        do { _ = try await operation.value; XCTFail("Expected cancellation") } catch { XCTAssertTrue(error is CancellationError) }
        driver.permissions[0](true)
        XCTAssertTrue(driver.sessions.isEmpty)
    }

    func testLateSpeechCallbacksCannotCompleteNextRecording() async throws {
        let driver = SpeechDriverFixture()
        let transcriber = OnDeviceSpeechTranscriber(driver: driver)
        let first = Task { try await transcriber.transcribe(file) }
        await waitUntil { driver.permissions.count == 1 }
        driver.permissions[0](true); driver.callbacks[0](.success("第一段"))
        _ = try await first.value
        let second = Task { try await transcriber.transcribe(file) }
        await waitUntil { driver.permissions.count == 2 }
        driver.permissions[1](true)
        driver.callbacks[0](.failure(LocalSpeechError.timedOut))
        driver.callbacks[0](.success("旧结果"))
        XCTAssertEqual(driver.sessions[1].cancellations, 0)
        driver.callbacks[1](.success("第二段"))
        let text = try await second.value
        XCTAssertEqual(text, "第二段")
    }

    func testSpeechSynchronousFinalResultStillReleasesSessionAndDenialCanRetry() async throws {
        let driver = SpeechDriverFixture()
        let transcriber = OnDeviceSpeechTranscriber(driver: driver)
        let denied = Task { try await transcriber.transcribe(file) }
        await waitUntil { driver.permissions.count == 1 }
        driver.permissions[0](false)
        do { _ = try await denied.value; XCTFail("Expected denial") } catch LocalSpeechError.denied { }
        driver.immediateResult = .success("同步结果")
        let retry = Task { try await transcriber.transcribe(file) }
        await waitUntil { driver.permissions.count == 2 }
        driver.permissions[1](true)
        let text = try await retry.value
        XCTAssertEqual(text, "同步结果")
        XCTAssertEqual(driver.sessions[0].cancellations, 1)
    }

    func testSpeechDeadlineCancelsRecognizerAndLateFinalIsIgnored() async {
        let driver = SpeechDriverFixture()
        let speech = OnDeviceSpeechTranscriber(driver: driver, timeout: .milliseconds(10))
        let operation = Task { try await speech.transcribe(file) }
        await waitUntil { driver.permissions.count == 1 }
        driver.permissions[0](true)
        do { _ = try await operation.value; XCTFail("Expected deadline") } catch LocalSpeechError.timedOut { } catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(driver.sessions[0].cancellations, 1)
        driver.callbacks[0](.success("过期结果"))
    }

    func testPausedLiveActivityExpiresAndSourceChangeUpdatesImmediately() async throws {
        let backend = RecordingActivityBackendFixture()
        let date = Date(timeIntervalSince1970: 1234)
        let activity = RecordingActivityController(backend: backend, now: { date })
        activity.start(id: "first", source: "手机麦克风")
        await waitUntil { backend.created.count == 1 }
        activity.update(paused: true, seconds: 12, source: "手机麦克风")
        await waitUntil { backend.created[0].updates.count == 1 }
        XCTAssertEqual(backend.created[0].updates[0].0.phase, "paused")
        XCTAssertEqual(backend.created[0].updates[0].1, date.addingTimeInterval(90))
        activity.update(paused: true, seconds: 12, source: "耳机麦克风")
        await waitUntil { backend.created[0].updates.count == 2 }
        XCTAssertEqual(backend.created[0].updates[1].0.source, "耳机麦克风")
        activity.finish()
        await waitUntil { backend.created[0].ended }
    }

    func testLiveActivityReplacementWaitsForPreviousEndAndUsesLatestPause() async throws {
        let backend = RecordingActivityBackendFixture()
        let controller = RecordingActivityController(backend: backend)
        controller.start(id: "first", source: "手机麦克风")
        await waitUntil { backend.created.count == 1 }
        let previous = backend.created[0]; previous.holdEnd = true
        controller.start(id: "second", source: "手机麦克风")
        controller.update(paused: true, seconds: 7, source: "耳机麦克风")
        await waitUntil { previous.endContinuation != nil }
        XCTAssertEqual(backend.requests.count, 1)
        previous.endContinuation?.resume(); previous.endContinuation = nil
        await waitUntil { backend.requests.count == 2 }
        XCTAssertTrue(previous.ended)
        XCTAssertEqual(backend.requests[1].0, "second")
        XCTAssertEqual(backend.requests[1].1.phase, "paused")
        XCTAssertEqual(backend.requests[1].1.elapsedSeconds, 7)
        controller.finish()
        await waitUntil { backend.created[1].ended }
    }

    func testLiveActivityFinishInvalidatesPendingRequestAndQueuedUpdate() async throws {
        let backend = RecordingActivityBackendFixture()
        let controller = RecordingActivityController(backend: backend)
        controller.start(id: "never-created", source: "手机麦克风")
        controller.finish()
        controller.start(id: "current", source: "手机麦克风")
        await waitUntil { backend.created.count == 1 }
        XCTAssertEqual(backend.requests[0].0, "current")
        controller.update(paused: true, seconds: 4, source: "手机麦克风")
        controller.finish()
        await waitUntil { backend.created[0].ended }
        XCTAssertTrue(backend.created[0].updates.isEmpty)
    }

    func testAudioDelegateRejectsQueuedOldRecorderAndConsumesOneTerminalCallback() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1]
        let old = try AVAudioRecorder(url: root.appendingPathComponent("old.m4a"), settings: settings)
        let current = try AVAudioRecorder(url: root.appendingPathComponent("current.m4a"), settings: settings)
        let events = RecordingAudioEvents()
        events.recorder = old
        var results: [Bool] = []
        events.finished = { results.append($0) }
        events.audioRecorderDidFinishRecording(old, successfully: false)
        events.recorder = current
        await Task.yield()
        XCTAssertTrue(results.isEmpty)
        events.audioRecorderEncodeErrorDidOccur(current, error: nil)
        await waitUntil { !results.isEmpty }
        events.audioRecorderDidFinishRecording(current, successfully: true)
        await Task.yield()
        XCTAssertEqual(results, [false])
        XCTAssertNil(events.recorder)
    }

    func testAtomicCheckpointContentSurvivesReplacementAndKeepsFinalTranscript() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalRecordingStore(root: root), id = UUID().uuidString
        let draft = RecordingDraft(id: id, fileURL: root.appendingPathComponent(id + ".m4a"), recordedAt: Date(), durationMS: 2000,
                                   questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        var record = LocalRecording(draft: draft, owner: nil, status: "recording")
        let sidecar = root.appendingPathComponent(id + ".recording.json")
        try store.save(record)
        XCTAssertTrue(FileManager.default.fileExists(atPath: sidecar.path))
        XCTAssertEqual(try store.load().recordings.first?.status, "recording")
        record.status = "saved"; record.machineTranscript = "本人原话"
        try store.save(record)
        let loaded = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(loaded.id, id); XCTAssertEqual(loaded.status, "saved")
        XCTAssertEqual(loaded.machineTranscript, "本人原话")
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), [id + ".recording.json"])
    }

    func testSidecarDataProtectionClassesOnPhysicalDevice() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("iOS Simulator does not expose Data Protection file attributes; physical-device verification is required.")
        #else
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = LocalRecordingStore(root: root), id = UUID().uuidString
        let draft = RecordingDraft(id: id, fileURL: root.appendingPathComponent(id + ".m4a"), recordedAt: Date(), durationMS: 2000,
                                   questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        var record = LocalRecording(draft: draft, owner: nil, status: "recording")
        let sidecar = root.appendingPathComponent(id + ".recording.json")
        try store.save(record)
        XCTAssertEqual(try FileManager.default.attributesOfItem(atPath: sidecar.path)[.protectionKey] as? FileProtectionType, .completeUntilFirstUserAuthentication)
        record.status = "saved"; record.machineTranscript = "本人原话"
        try store.save(record)
        XCTAssertEqual(try FileManager.default.attributesOfItem(atPath: sidecar.path)[.protectionKey] as? FileProtectionType, .complete)
        #endif
    }
}

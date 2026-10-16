import Foundation
import XCTest
@testable import RememberMe

private struct CaptureRequest: Sendable {
    let method: String
    let path: String
    let body: Data
    func multipartValue(_ name: String) -> String? {
        let text = String(decoding: body, as: UTF8.self)
        guard let marker = text.range(of: "name=\"\(name)\"\r\n\r\n"),
              let end = text.range(of: "\r\n", range: marker.upperBound..<text.endIndex) else { return nil }
        return String(text[marker.upperBound..<end.lowerBound])
    }
}

private final class CaptureRequestLog: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [CaptureRequest] = []
    func append(_ request: URLRequest) {
        let value = CaptureRequest(method: request.httpMethod ?? "GET", path: request.url?.path ?? "", body: Self.body(request))
        lock.lock(); defer { lock.unlock() }; values.append(value)
    }
    var requests: [CaptureRequest] { lock.lock(); defer { lock.unlock() }; return values }
    var patchCount: Int { requests.filter { $0.method == "PATCH" }.count }
    var episodeUploadCount: Int { requests.filter { $0.method == "POST" && $0.path == "/api/v1/episodes" }.count }
    private static func body(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var result = Data(), bytes = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&bytes, maxLength: bytes.count)
            if count <= 0 { break }
            result.append(contentsOf: bytes.prefix(count))
        }
        return result
    }
}

private final class CaptureReadGate: @unchecked Sendable {
    private let lock = NSLock()
    private var path: String?
    private var pending: CaptureRequestProtocol?
    func hold(_ path: String) { lock.lock(); defer { lock.unlock() }; self.path = path; pending = nil }
    func capture(_ request: CaptureRequestProtocol) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard path == request.request.url?.path else { return false }
        pending = request; return true
    }
    var hasPending: Bool { lock.lock(); defer { lock.unlock() }; return pending != nil }
    func release(_ data: Data, status: Int = 200) {
        lock.lock(); let request = pending; pending = nil; path = nil; lock.unlock()
        request?.finish(status: status, data: data)
    }
}

private final class CaptureRequestProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var response: ((URLRequest) throws -> (Int, Data))?
    nonisolated(unsafe) static var log = CaptureRequestLog()
    static let gate = CaptureReadGate()
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.log.append(request)
        if Self.gate.capture(self) { return }
        do {
            let (status, data) = try Self.response?(request) ?? (503, Data())
            finish(status: status, data: data)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    func finish(status: Int, data: Data) {
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }
}

@MainActor
final class AutomaticCaptureTests: XCTestCase {
    private let reviewJSON = #"{"state":"reviewing","transcript":"自动校对后的文字。","machine_transcript":"机器最初的文字。","stt_model_version":"fixture-stt"}"#

    private func pairing(_ subject: String = "subject", actor: String = "actor", server: String = "https://fixture.invalid") -> Pairing {
        Pairing(baseURL: server, fingerprint: String(repeating: "a", count: 64), token: "fixture-token",
                actorID: actor, subjectID: subject, consentID: "recording")
    }
    private func fixture() throws -> (LocalRecordingStore, UserDefaults, String) {
        let name = "automatic-capture-" + UUID().uuidString
        CaptureRequestProtocol.log = CaptureRequestLog()
        CaptureRequestProtocol.gate.release(Data(), status: 503)
        let store = LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(name))
        return (store, try XCTUnwrap(UserDefaults(suiteName: name)), name)
    }
    private func cleanup(_ store: LocalRecordingStore, _ defaults: UserDefaults, _ name: String) {
        CaptureRequestProtocol.gate.release(Data(), status: 503)
        CaptureRequestProtocol.response = nil
        defaults.removePersistentDomain(forName: name)
        try? FileManager.default.removeItem(at: store.root)
    }
    private func recording(_ store: LocalRecordingStore, owner: Pairing, episode: String? = "capture", automatic: Bool? = true) throws -> LocalRecording {
        let id = UUID().uuidString
        let draft = RecordingDraft(id: id, fileURL: store.root.appendingPathComponent(id + ".m4a"),
            recordedAt: Date(), durationMS: 12000, questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        var record = LocalRecording(draft: draft, owner: RecordingOwner(owner))
        record.episodeID = episode; record.status = episode == nil ? "saved" : "reviewing"
        record.automaticProcessing = automatic
        try store.save(record)
        // Sentinel bytes prove the tests never invoke an audio recorder or rewrite the original.
        try Data([1, 5, 9, 13]).write(to: draft.fileURL)
        return record
    }
    private func model(_ store: LocalRecordingStore, _ defaults: UserDefaults, pairing: Pairing) throws -> AppModel {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [CaptureRequestProtocol.self]
        let api = try APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token,
                                session: URLSession(configuration: config))
        return AppModel(recordingStore: store, defaults: defaults, pairing: pairing,
                        apiClientFactory: { _ in api }, recordPermission: { false }, applicationIsActive: { true })
    }
    nonisolated private func response(_ request: URLRequest, modern: Bool = true, grants: String? = nil) -> (Int, Data) {
        let path = request.url?.path ?? ""
        let text: String
        if path == "/api/v1/workbench/capabilities" {
            text = modern
                ? #"{"stt":"fixture","stt_processing":"local","stt_configured":true,"ai_available":true,"automatic_capture_version":1,"automatic_profile_analysis":true}"#
                : #"{"stt":"fixture","stt_processing":"local","stt_configured":true,"ai_available":true}"#
        } else if path == "/api/v1/consents" {
            text = grants ?? #"[{"consent_id":"recording","scope":"RECORDING","status":"granted"},{"consent_id":"old-cloud","scope":"CLOUD_TWIN","status":"revoked"},{"consent_id":"current-cloud","scope":"CLOUD_TWIN","status":"granted"}]"#
        } else if path.hasSuffix("/transcript-review") {
            text = request.httpMethod == "PATCH" ? "{}" : #"{"state":"reviewing","transcript":"自动校对后的文字。","machine_transcript":"机器最初的文字。","stt_model_version":"fixture-stt"}"#
        } else if path.hasSuffix("/person-model") {
            text = #"{"version":2,"domains":[]}"#
        } else if path.hasSuffix("/episodes") {
            text = #"{"items":[{"episode_id":"capture","status":"transcribing","source":"IOS_MIC","recorded_at":"2026-10-16T00:00:00Z"}]}"#
        } else if path == "/api/v1/episodes/capture" {
            text = #"{"status":"extracting"}"#
        } else if ["/memories", "/questions", "/calibrations"].contains(where: path.hasSuffix) {
            text = #"{"items":[]}"#
        } else { return (404, Data(#"{"error":{"message":"optional fixture service"}}"#.utf8)) }
        return (200, Data(text.utf8))
    }
    private func waitForRead(file: StaticString = #filePath, line: UInt = #line) async {
        for _ in 0..<100 {
            if CaptureRequestProtocol.gate.hasPending { return }
            try? await Task.sleep(for: .milliseconds(10))
        }
        XCTFail("The transcript refresh did not reach the held read", file: file, line: line)
    }
    private func waitForQueue(_ model: AppModel, file: StaticString = #filePath, line: UInt = #line) async {
        for _ in 0..<200 {
            if !model.isSyncingDeviceRecordings { return }
            try? await Task.sleep(for: .milliseconds(10))
        }
        XCTFail("The bounded recording queue did not finish", file: file, line: line)
    }

    func testOneSaveSendsEditedTextSupplementAndCurrentAnalysisConsent() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(), original = Data([1, 5, 9, 13])
        var record = try recording(store, owner: owner)
        record.machineTranscript = "机器最初的文字。"; record.reviewDraft = "自动校对后的文字。"; try store.save(record)
        let model = try model(store, defaults, pairing: owner)
        model.cloudConsentID = "old-cloud"
        CaptureRequestProtocol.response = { [self] request in response(request) }
        model.saveCaptureDraft(record.id, text: "本人修改后的完整文字。", supplement: "补充发生在春天。")

        await model.submitCaptureDraft(record.id)

        let writes = CaptureRequestProtocol.log.requests.filter { $0.method == "PATCH" && $0.path.hasSuffix("/transcript-review") }
        XCTAssertEqual(writes.count, 1)
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: XCTUnwrap(writes.first).body) as? [String: String])
        XCTAssertEqual(body["transcript"], "本人修改后的完整文字。")
        XCTAssertEqual(body["supplement"], "补充发生在春天。")
        XCTAssertEqual(body["cloud_analysis_consent_id"], "current-cloud")
        XCTAssertFalse(CaptureRequestProtocol.log.requests.contains { $0.method == "POST" && $0.path == "/api/v1/consents" })
        let saved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(saved.machineTranscript, "机器最初的文字。")
        XCTAssertEqual(saved.reviewedTranscript, "本人修改后的完整文字。")
        XCTAssertEqual(saved.supplementDraft, "补充发生在春天。")
        XCTAssertEqual(model.lastSavedCaptureID, record.id)
        XCTAssertEqual(try Data(contentsOf: record.draft.fileURL), original)
    }

    func testOlderBackendSaveOmitsAnalysisFieldAndRetainsSupportedSupplement() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(); var record = try recording(store, owner: owner)
        record.machineTranscript = "机器稿。"; record.reviewDraft = "待核对文字。"; try store.save(record)
        let model = try model(store, defaults, pairing: owner)
        model.cloudConsentID = "old-cloud"
        CaptureRequestProtocol.response = { [self] request in response(request, modern: false) }
        model.saveCaptureDraft(record.id, text: "核对完成的文字。", supplement: "等待兼容服务的补充。")

        await model.submitCaptureDraft(record.id)

        let writes = CaptureRequestProtocol.log.requests.filter { $0.method == "PATCH" && $0.path.hasSuffix("/transcript-review") }
        XCTAssertEqual(writes.count, 1)
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: XCTUnwrap(writes.first).body) as? [String: String])
        XCTAssertEqual(body, ["transcript": "核对完成的文字。", "supplement": "等待兼容服务的补充。"])
        XCTAssertEqual(try store.load().recordings.first?.supplementDraft, "等待兼容服务的补充。")
    }

    func testCaptureDraftRecoversAfterRelaunchOnlyWithinItsOwnerScope() throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(); var record = try recording(store, owner: owner)
        record.machineTranscript = "原始机器稿。"; try store.save(record)
        let first = try model(store, defaults, pairing: owner)
        first.saveCaptureDraft(record.id, text: "还没点保存的本人改稿。", supplement: "尚未提交的补充。")
        let restored = try model(store, defaults, pairing: owner)
        XCTAssertEqual(restored.latestCaptureDraft?.id, record.id)
        XCTAssertEqual(restored.latestCaptureDraft?.reviewDraft, "还没点保存的本人改稿。")
        XCTAssertEqual(restored.latestCaptureDraft?.supplementDraft, "尚未提交的补充。")
        XCTAssertEqual(restored.latestCaptureDraft?.machineTranscript, "原始机器稿。")
        for other in [pairing("other"), pairing(actor: "other"), pairing(server: "https://other.invalid")] {
            let isolated = try model(store, defaults, pairing: other)
            XCTAssertNil(isolated.latestCaptureDraft)
            isolated.saveCaptureDraft(record.id, text: "越界改稿", supplement: "越界补充")
        }
        XCTAssertEqual(try store.load().recordings.first?.reviewDraft, "还没点保存的本人改稿。")
        XCTAssertTrue(CaptureRequestProtocol.log.requests.isEmpty)
    }

    func testRevokedAnalysisConsentIsNotRestoredBySavingADraft() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(); var record = try recording(store, owner: owner)
        record.machineTranscript = "原始文字。"; try store.save(record)
        let model = try model(store, defaults, pairing: owner)
        model.cloudConsentID = "old-cloud"
        CaptureRequestProtocol.response = { [self] request in
            response(request, grants: #"[{"consent_id":"recording","scope":"RECORDING","status":"granted"},{"consent_id":"old-cloud","scope":"CLOUD_TWIN","status":"revoked"},{"consent_id":"wrong-purpose","scope":"MODEL_TRAINING","status":"granted"}]"#)
        }
        model.saveCaptureDraft(record.id, text: "只保存核对文字。", supplement: "")
        await model.submitCaptureDraft(record.id)
        let write = try XCTUnwrap(CaptureRequestProtocol.log.requests.first { $0.method == "PATCH" })
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: write.body) as? [String: String])
        XCTAssertEqual(body["transcript"], "只保存核对文字。")
        XCTAssertNil(body["cloud_analysis_consent_id"])
        XCTAssertFalse(CaptureRequestProtocol.log.requests.contains { $0.method == "POST" && $0.path == "/api/v1/consents" })
    }

    func testFailedSaveKeepsUnreviewedDraftAndRetrySendsTheSameContent() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(); var record = try recording(store, owner: owner)
        record.machineTranscript = "不可改写的机器原稿。"; try store.save(record)
        let model = try model(store, defaults, pairing: owner)
        CaptureRequestProtocol.response = { [self] request in
            if request.httpMethod == "PATCH", CaptureRequestProtocol.log.patchCount == 1 {
                return (503, Data(#"{"error":{"message":"fixture unavailable"}}"#.utf8))
            }
            return response(request)
        }
        model.saveCaptureDraft(record.id, text: "重试也应保持的核对文字。", supplement: "补充不会丢失。")
        await model.submitCaptureDraft(record.id)
        let failed = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(failed.status, "reviewing")
        XCTAssertNil(failed.reviewedAt); XCTAssertNil(failed.reviewedTranscript)
        XCTAssertEqual(failed.reviewDraft, "重试也应保持的核对文字。")
        XCTAssertEqual(failed.supplementDraft, "补充不会丢失。")
        XCTAssertNil(model.lastSavedCaptureID); XCTAssertNil(model.savingCaptureID)
        XCTAssertEqual(try Data(contentsOf: record.draft.fileURL), Data([1, 5, 9, 13]))

        await model.submitCaptureDraft(record.id)

        let writes = CaptureRequestProtocol.log.requests.filter { $0.method == "PATCH" }
        XCTAssertEqual(writes.count, 2)
        let bodies = try writes.map { try JSONSerialization.jsonObject(with: $0.body) as? [String: String] }
        XCTAssertEqual(try XCTUnwrap(bodies.first), try XCTUnwrap(bodies.last))
        let saved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(saved.status, "extracting")
        XCTAssertNotNil(saved.reviewedAt)
        XCTAssertEqual(saved.reviewedTranscript, "重试也应保持的核对文字。")
        XCTAssertEqual(saved.machineTranscript, "不可改写的机器原稿。")
        XCTAssertEqual(model.lastSavedCaptureID, record.id)
    }

    func testFreshDraftSeparatesMachineOriginalAutomaticCorrectionAndHumanEdits() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(), record = try recording(store, owner: pairing())
        let model = try model(store, defaults, pairing: owner)
        CaptureRequestProtocol.response = { [self] request in
            if request.url?.path.hasSuffix("/transcript-review") == true {
                return (200, Data(#"{"state":"reviewing","transcript":"我在上海工作。","machine_transcript":"我在上还工作。","stt_model_version":"fixture-stt","automatic_correction":{"status":"completed","draft":"我在上海工作。","model_version":"fixture-correction","edits":[{"before":"上还","after":"上海","category":"homophone","action":"auto","reason":"上下文中的地名","start":2,"end":4}]}}"#.utf8))
            }
            return response(request)
        }
        await model.refreshCaptureDrafts()
        let draft = try XCTUnwrap(model.latestCaptureDraft)
        XCTAssertEqual(draft.machineTranscript, "我在上还工作。")
        XCTAssertEqual(draft.reviewDraft, "我在上海工作。")
        XCTAssertEqual(draft.automaticCorrection?.status, "completed")
        XCTAssertEqual(draft.automaticCorrection?.changes.first?.before, "上还")
        XCTAssertEqual(draft.automaticCorrection?.changes.first?.after, "上海")
        model.saveCaptureDraft(record.id, text: "我曾经在上海工作。", supplement: "当时住在浦东。")
        let saved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(saved.machineTranscript, "我在上还工作。")
        XCTAssertEqual(saved.automaticCorrection?.draft, "我在上海工作。")
        XCTAssertEqual(saved.reviewDraft, "我曾经在上海工作。")
        XCTAssertEqual(saved.supplementDraft, "当时住在浦东。")
        XCTAssertNil(saved.reviewedAt)
    }

    func testLateTranscriptReadPreservesDraftEditedWhileRefreshWasInFlight() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(); var record = try recording(store, owner: owner)
        record.machineTranscript = "已有机器稿。"; try store.save(record)
        let model = try model(store, defaults, pairing: owner)
        CaptureRequestProtocol.response = { [self] request in response(request) }
        CaptureRequestProtocol.gate.hold("/api/v1/episodes/capture/transcript-review")
        let refresh = Task { await model.refreshCaptureDrafts() }
        await waitForRead()
        model.saveCaptureDraft(record.id, text: "刷新期间刚输入的改稿。", supplement: "刚输入的补充。")
        CaptureRequestProtocol.gate.release(Data(reviewJSON.utf8))
        await refresh.value
        let saved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(saved.reviewDraft, "刷新期间刚输入的改稿。")
        XCTAssertEqual(saved.supplementDraft, "刚输入的补充。")
        XCTAssertEqual(saved.machineTranscript, "已有机器稿。")
    }

    func testLateTranscriptReadCannotUpdateOldOwnerAfterSpaceChanges() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(); let record = try recording(store, owner: owner)
        let other = try recording(store, owner: pairing("other"), episode: "other-capture")
        let model = try model(store, defaults, pairing: owner)
        CaptureRequestProtocol.response = { [self] request in response(request) }
        CaptureRequestProtocol.gate.hold("/api/v1/episodes/capture/transcript-review")
        let refresh = Task { await model.refreshCaptureDrafts() }
        await waitForRead()
        model.pairing = pairing("other")
        CaptureRequestProtocol.gate.release(Data(reviewJSON.utf8))
        await refresh.value
        let rows = try store.load().recordings
        XCTAssertNil(rows.first { $0.id == record.id }?.machineTranscript)
        XCTAssertNil(rows.first { $0.id == record.id }?.reviewDraft)
        XCTAssertNil(rows.first { $0.id == other.id }?.reviewDraft)
        XCTAssertFalse(model.visibleLocalRecordings.contains { $0.id == record.id })
    }

    func testLegacyUnflaggedPhoneRecordingsAreNeverAutomaticallyUploaded() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(), legacy = try recording(store, owner: pairing(), episode: nil, automatic: nil)
        let model = try model(store, defaults, pairing: owner)
        CaptureRequestProtocol.response = { _ in XCTFail("Legacy phone recordings must remain local until explicitly submitted"); return (500, Data()) }
        model.processDeviceRecordingQueue()
        for _ in 0..<20 { await Task.yield() }
        XCTAssertFalse(model.isSyncingDeviceRecordings)
        XCTAssertTrue(CaptureRequestProtocol.log.requests.isEmpty)
        let saved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(saved.id, legacy.id); XCTAssertNil(saved.episodeID); XCTAssertNil(saved.automaticProcessing)
        XCTAssertEqual(try Data(contentsOf: legacy.draft.fileURL), Data([1, 5, 9, 13]))
    }

    func testNewPhoneQueuePersistsFailureAndReusesIdempotencyKeyAfterRelaunch() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(), record = try recording(store, owner: pairing(), episode: nil)
        let first = try model(store, defaults, pairing: owner)
        CaptureRequestProtocol.response = { [self] request in
            if request.httpMethod == "POST", request.url?.path == "/api/v1/episodes" {
                if CaptureRequestProtocol.log.episodeUploadCount == 1 {
                    // The server may have accepted the bytes while its response was lost.
                    // Replaying the persisted key must resolve to the same Episode.
                    return (503, Data(#"{"error":{"message":"fixture lost upload response"}}"#.utf8))
                }
                return (200, Data(#"{"episode_id":"capture"}"#.utf8))
            }
            return response(request)
        }
        first.processDeviceRecordingQueue()
        XCTAssertTrue(first.isSyncingDeviceRecordings)
        await waitForQueue(first)
        let failed = try XCTUnwrap(store.load().recordings.first)
        XCTAssertNil(failed.episodeID)
        XCTAssertEqual(failed.automaticAttempts, 1)
        XCTAssertNotNil(failed.automaticRetryAt)
        XCTAssertNotNil(failed.automaticError)
        XCTAssertEqual(failed.automaticProcessing, true)

        let restored = try model(store, defaults, pairing: owner)
        XCTAssertEqual(restored.visibleLocalRecordings.first?.automaticAttempts, 1)
        restored.processDeviceRecordingQueue()
        XCTAssertFalse(restored.isSyncingDeviceRecordings, "A relaunch must honor the persisted retry delay")
        XCTAssertEqual(CaptureRequestProtocol.log.episodeUploadCount, 1)
        restored.retryAutomaticRecording(record.id)
        XCTAssertTrue(restored.isSyncingDeviceRecordings)
        await waitForQueue(restored)

        let uploads = CaptureRequestProtocol.log.requests.filter { $0.method == "POST" && $0.path == "/api/v1/episodes" }
        XCTAssertEqual(uploads.count, 2)
        XCTAssertEqual(uploads.map { $0.multipartValue("idempotency_key") }, [record.id, record.id])
        XCTAssertEqual(uploads.map { $0.multipartValue("source") }, ["IOS_MIC", "IOS_MIC"])
        XCTAssertEqual(uploads.map { $0.multipartValue("subject_id") }, [owner.subjectID, owner.subjectID])
        XCTAssertEqual(uploads.map { $0.multipartValue("recording_consent_id") }, ["recording", "recording"])
        XCTAssertFalse(CaptureRequestProtocol.log.requests.contains { $0.method == "POST" && $0.path == "/api/v1/consents" })
        let saved = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(saved.episodeID, "capture")
        XCTAssertEqual(saved.automaticAttempts, 0)
        XCTAssertNil(saved.automaticRetryAt); XCTAssertNil(saved.automaticError)
        XCTAssertEqual(saved.draft.id, record.id)
        XCTAssertEqual(try Data(contentsOf: record.draft.fileURL), Data([1, 5, 9, 13]))
    }

    func testRealtimePreflightDefersPhoneUploadAndLateOldOwnerResponseCannotBind() async throws {
        let (store, defaults, name) = try fixture(); defer { cleanup(store, defaults, name) }
        let owner = pairing(), record = try recording(store, owner: pairing(), episode: nil)
        let otherOwner = pairing("other", actor: "other-actor")
        let other = try recording(store, owner: otherOwner, episode: nil)
        let model = try model(store, defaults, pairing: owner)
        CaptureRequestProtocol.response = { [self] request in
            if request.httpMethod == "POST", request.url?.path == "/api/v1/episodes" {
                return (200, Data(#"{"episode_id":"late-old-capture"}"#.utf8))
            }
            return response(request)
        }
        CaptureRequestProtocol.gate.hold("/api/v1/episodes")
        model.processDeviceRecordingQueue()
        await waitForRead()
        XCTAssertTrue(model.isSyncingDeviceRecordings)
        XCTAssertFalse(model.recordingStartBlocked, "Queued transfer must yield to foreground capture")
        XCTAssertTrue(model.prepareRealtimeCapture())
        XCTAssertFalse(model.isSyncingDeviceRecordings)
        XCTAssertNil(model.localRecordings.first { $0.id == record.id }?.episodeID)

        // Use the existing native-audio state without opening the microphone.
        model.isSpeakerRecording = true
        model.pairing = otherOwner
        model.processDeviceRecordingQueue()
        XCTAssertFalse(model.isSyncingDeviceRecordings, "Realtime audio must prevent a replacement-owner upload")
        CaptureRequestProtocol.gate.release(Data(#"{"episode_id":"late-old-capture"}"#.utf8))
        for _ in 0..<30 { await Task.yield() }
        let rows = try store.load().recordings
        XCTAssertNil(rows.first { $0.id == record.id }?.episodeID)
        XCTAssertNil(rows.first { $0.id == other.id }?.episodeID)
        XCTAssertFalse(model.visibleLocalRecordings.contains { $0.id == record.id })
        XCTAssertEqual(CaptureRequestProtocol.log.episodeUploadCount, 1)
        let upload = try XCTUnwrap(CaptureRequestProtocol.log.requests.first { $0.method == "POST" && $0.path == "/api/v1/episodes" })
        XCTAssertEqual(upload.multipartValue("idempotency_key"), record.id)
        XCTAssertEqual(upload.multipartValue("subject_id"), owner.subjectID)
        XCTAssertFalse(CaptureRequestProtocol.log.requests.contains { $0.method == "POST" && $0.path == "/api/v1/consents" })
        XCTAssertEqual(try Data(contentsOf: record.draft.fileURL), Data([1, 5, 9, 13]))
        model.isSpeakerRecording = false
    }
}

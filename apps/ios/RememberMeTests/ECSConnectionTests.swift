import XCTest
@testable import RememberMe

private final class ECSRequestProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var response: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, data) = try Self.response!(request)
            let reply = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                        headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: reply, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}

@MainActor
final class ECSConnectionTests: XCTestCase {
    private func client() throws -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ECSRequestProtocol.self]
        return try APIClient(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                             token: "fixture-token", session: URLSession(configuration: config))
    }
    nonisolated private func requestBody(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var data = Data()
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let count = stream.read(buffer, maxLength: 4096)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }
    func testLoginAndSpaceDecodingUseSharedBackend() async throws {
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/accounts/login")
            XCTAssertEqual(request.httpMethod, "POST")
            return (200, Data(#"{"actor_token":"fixture-token","actor_id":"actor","display_name":"本人"}"#.utf8))
        }
        let api = try client()
        let login = try await api.login(username: "fixture", password: "fixture-password")
        XCTAssertEqual(login.actor_id, "actor")
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/workbench/spaces")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer fixture-token")
            return (200, Data(#"{"actor_id":"actor","display_name":"本人","items":[{"subject_id":"subject","display_name":"本人","role":"owner"},{"subject_id":"shared","display_name":"亲友","role":"reader"}]}"#.utf8))
        }
        let spaces = try await api.spaces()
        XCTAssertEqual(spaces.items.map(\.role), ["owner", "reader"])
    }
    func testQueryConsentPolicyIsSentWithAudio() async throws {
        ECSRequestProtocol.response = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/subjects/subject/twin/transcribe-query")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Cloud-ASR-Policy"), "policy-fixture")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "audio/mp4")
            return (200, Data(#"{"text":"我的问题","stt_model_version":"fixture-asr"}"#.utf8))
        }
        let result = try await client().transcribeQuery(subjectID: "subject", audio: Data([1, 2]), cloudASRPolicy: "policy-fixture")
        XCTAssertEqual(result.text, "我的问题")
    }
    func testUploadPreservesIdentityIdempotencyAndConsentPolicy() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
        try Data([1, 2, 3]).write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        let draft = RecordingDraft(id: "stable-upload", fileURL: file, recordedAt: Date(), durationMS: 10000,
                                   questionID: "question", calibrationID: "calibration", consentConfirmedAt: Date())
        ECSRequestProtocol.response = { [self] request in
            let body = String(decoding: requestBody(request), as: UTF8.self)
            XCTAssertTrue(body.contains("IOS_MIC"))
            XCTAssertTrue(body.contains("stable-upload"))
            XCTAssertTrue(body.contains("policy-fixture"))
            XCTAssertTrue(body.contains("calibration"))
            XCTAssertTrue(body.contains("question"))
            XCTAssertTrue(body.contains("recording-consent"))
            return (201, Data(#"{"episode_id":"episode-fixture"}"#.utf8))
        }
        let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64),
                              token: "fixture-token", actorID: "actor", subjectID: "subject", consentID: "recording-consent")
        let uploaded = try await client().upload(draft, pairing: pairing, cloudASRPolicy: "policy-fixture")
        XCTAssertEqual(uploaded, "episode-fixture")
    }
    func testStructuredServerFailureIsReadable() async throws {
        ECSRequestProtocol.response = { _ in
            (409, Data(#"{"error":{"code":"SOURCE_CHANGED","message":"资料已变化，请重新提问。"}}"#.utf8))
        }
        do { _ = try await client().spaces(); XCTFail("Expected rejection") }
        catch { XCTAssertTrue(error.localizedDescription.contains("资料已变化")) }
    }
    func testOldPairingDecodesWithoutCloudFields() throws {
        let old = Data(#"{"baseURL":"https://mac.invalid","fingerprint":"aaaa","token":"fixture","actorID":"actor","subjectID":"subject","consentID":"consent"}"#.utf8)
        let pairing = try JSONDecoder().decode(Pairing.self, from: old)
        XCTAssertFalse(pairing.isCloud)
    }
    func testChangingServiceArchivesPendingEpisodeInOriginalScope() throws {
        let name = "ecs-isolation-" + UUID().uuidString
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        let store = LocalRecordingStore(root: FileManager.default.temporaryDirectory.appendingPathComponent(name))
        defer {
            try? FileManager.default.removeItem(at: store.root)
            defaults.removePersistentDomain(forName: name)
        }
        let mac = Pairing(baseURL: "https://mac.invalid", fingerprint: String(repeating: "a", count: 64),
                          token: "fixture", actorID: "old-actor", subjectID: "old-subject", consentID: "consent")
        let draft = RecordingDraft(id: UUID().uuidString, fileURL: store.root.appendingPathComponent("old.m4a"),
                                   recordedAt: Date(), durationMS: 10000, questionID: nil, calibrationID: nil, consentConfirmedAt: Date())
        let model = AppModel(recordingStore: store, defaults: defaults, pairing: mac)
        model.draft = draft; model.episodeID = "mac-episode"
        let cloud = Pairing(baseURL: ECSConfiguration.baseURL, fingerprint: ECSConfiguration.fingerprint,
                            token: "cloud-fixture", actorID: "new-actor", subjectID: "new-subject", consentID: "", connectionKind: "ecs")
        XCTAssertTrue(model.applyConnection(cloud, persist: false))
        XCTAssertNil(model.draft); XCTAssertNil(model.episodeID)
        XCTAssertTrue(model.visibleLocalRecordings.isEmpty)
        let retained = try XCTUnwrap(store.load().recordings.first)
        XCTAssertEqual(retained.owner, RecordingOwner(mac))
        XCTAssertEqual(retained.episodeID, "mac-episode")
        XCTAssertTrue(model.applyConnection(mac, persist: false))
        XCTAssertEqual(model.visibleLocalRecordings.first?.id, draft.id)
    }
}

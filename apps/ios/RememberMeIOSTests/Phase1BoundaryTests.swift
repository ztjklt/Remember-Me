import Foundation
import XCTest
@testable import RememberMeIOS

final class Phase1BoundaryTests: XCTestCase {
    private final class StubProtocol: URLProtocol {
        static var observedRequest: URLRequest?
        static var responseCode = 200
        static var responseBody = Data()
        static var handler: ((URLRequest) -> (Int, Data))?

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            Self.observedRequest = request
            let (code, body) = Self.handler?(request) ?? (Self.responseCode, Self.responseBody)
            let response = HTTPURLResponse(
                url: request.url!, statusCode: code,
                httpVersion: nil, headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func stubbedAPI() -> EpisodeAPI {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubProtocol.self]
        return EpisodeAPI(session: URLSession(configuration: configuration))
    }

    func testFailedEpisodeRetryUsesCurrentActorTokenAndExistingEpisode() async throws {
        StubProtocol.handler = nil
        StubProtocol.responseCode = 200
        StubProtocol.responseBody = Data(#"{"episode_id":"ep_existing","status":"extracting"}"#.utf8)
        let settings = ServerSettings(
            baseURL: "https://example.test", token: "current-account-token",
            subjectID: "subject-1", recordingConsentID: "consent-1",
            cloudTwinConsentID: "", handoverConsentID: "", voiceConsentID: ""
        )
        let status = try await stubbedAPI().retryProcessing(episodeID: "ep_existing", settings: settings)
        XCTAssertEqual(status.episodeId, "ep_existing")
        XCTAssertEqual(status.status, "extracting")
        XCTAssertEqual(StubProtocol.observedRequest?.httpMethod, "POST")
        XCTAssertEqual(StubProtocol.observedRequest?.url?.path, "/api/v1/episodes/ep_existing/retry")
        XCTAssertEqual(StubProtocol.observedRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer current-account-token")
    }

    func testTranscriptUnavailableIsNotShownAsAnEmptyTranscript() async throws {
        StubProtocol.handler = nil
        StubProtocol.responseCode = 409
        StubProtocol.responseBody = Data(#"{"error_code":"EPISODE_NOT_READY","error_message":"Transcript is not available yet"}"#.utf8)
        let settings = ServerSettings(
            baseURL: "https://example.test", token: "current-account-token",
            subjectID: "subject-1", recordingConsentID: "consent-1",
            cloudTwinConsentID: "", handoverConsentID: "", voiceConsentID: ""
        )
        do {
            _ = try await stubbedAPI().transcript(episodeID: "ep_waiting", settings: settings)
            XCTFail("An unprocessed Episode must not appear as empty text")
        } catch EpisodeAPIError.http(let code, _) {
            XCTAssertEqual(code, 409)
        }
        XCTAssertEqual(StubProtocol.observedRequest?.url?.path, "/api/v1/episodes/ep_waiting/transcript")
    }

    @MainActor
    func testUploadReleasesComposerWhileEarlierEpisodeProcesses() async throws {
        let subject = "subject-\(UUID().uuidString)"
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("episode-\(UUID().uuidString).m4a")
        try Data([0, 1, 2, 3]).write(to: file)
        defer {
            try? FileManager.default.removeItem(at: file)
            UserDefaults.standard.removeObject(forKey: "lastEpisodeID:\(subject)")
            UserDefaults.standard.removeObject(forKey: "pendingCapturePath:\(subject)")
            UserDefaults.standard.removeObject(forKey: "pendingCaptureDate:\(subject)")
            StubProtocol.handler = nil
        }
        StubProtocol.handler = { request in
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/v1/episodes"):
                return (201, Data(#"{"episode_id":"ep_slow","upload_status":"uploaded"}"#.utf8))
            case ("GET", "/api/v1/episodes"):
                return (200, Data("[]".utf8))
            case ("GET", "/api/v1/episodes/ep_slow"):
                Thread.sleep(forTimeInterval: 1)
                return (200, Data(#"{"episode_id":"ep_slow","status":"failed"}"#.utf8))
            default:
                return (404, Data(#"{"error_message":"unexpected request"}"#.utf8))
            }
        }
        let flow = EpisodeFlow(api: stubbedAPI())
        flow.settings = ServerSettings(
            baseURL: "https://example.test", token: "current-account-token",
            subjectID: subject, recordingConsentID: "consent-1",
            cloudTwinConsentID: "", handoverConsentID: "", voiceConsentID: ""
        )
        let started = Date()
        await flow.uploadAndProcess(fileURL: file, recordedAt: Date())
        XCTAssertLessThan(Date().timeIntervalSince(started), 0.9)
        XCTAssertFalse(flow.isBusy)
        XCTAssertNil(flow.pendingCaptureURL)
        try await Task.sleep(nanoseconds: 1_200_000_000)
    }

    func testMultipartPreservesConsentEpisodeMetadataAndAudio() throws {
        let audio = Data([0, 1, 2, 255])
        let body = MultipartCapture.body(
            audio: audio, fileName: "recording.m4a", subjectID: "subject-1",
            recordingConsentID: "consent-1", recordedAt: Date(timeIntervalSince1970: 0),
            idempotencyKey: "same-recording", boundary: "test-boundary"
        )
        let text = String(decoding: body, as: UTF8.self)
        XCTAssertTrue(text.contains("name=\"subject_id\"\r\n\r\nsubject-1"))
        XCTAssertTrue(text.contains("name=\"recording_consent_id\"\r\n\r\nconsent-1"))
        XCTAssertTrue(text.contains("name=\"idempotency_key\"\r\n\r\nsame-recording"))
        XCTAssertTrue(text.contains("name=\"source\"\r\n\r\nIMPORT"))
        XCTAssertTrue(text.contains("Content-Type: audio/mp4"))
        XCTAssertNotNil(body.range(of: audio))
        XCTAssertFalse(text.contains("Actor 令牌"))
    }

    func testSettingsRejectCredentialBearingAndNonHTTPURLs() {
        let base = ServerSettings(baseURL: "http://127.0.0.1:8000", token: "secret", subjectID: "s", recordingConsentID: "c", cloudTwinConsentID: "", handoverConsentID: "", voiceConsentID: "")
        XCTAssertTrue(base.isReady)
        for bad in ["ftp://example.test", "https://user:secret@example.test", "https://example.test?key=secret", "http://127.0.0.1:8000/other"] {
            var settings = base
            settings.baseURL = bad
            XCTAssertNil(settings.validatedURL, bad)
        }
    }

    func testImportedWavKeepsItsAudioType() {
        let body = MultipartCapture.body(
            audio: Data([1, 2]), fileName: "device.wav", subjectID: "s",
            recordingConsentID: "c", recordedAt: Date(timeIntervalSince1970: 0),
            idempotencyKey: "device-import", boundary: "test-boundary"
        )
        XCTAssertTrue(String(decoding: body, as: UTF8.self).contains("Content-Type: audio/wav"))
    }
}

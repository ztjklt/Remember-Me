import Foundation
import XCTest
@testable import RememberMeIOS

final class Phase1BoundaryTests: XCTestCase {
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

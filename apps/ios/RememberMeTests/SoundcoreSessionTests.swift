import XCTest
@testable import RememberMe

@MainActor
final class SoundcoreSessionTests: XCTestCase {
    func testOfficialSDKValidatesEphemeralQAReceiptWithoutScanningOrRecording() async throws {
        guard SoundcoreWorkAdapter.available else { throw XCTSkip("Local vendor SDK is not installed") }
        let receiptURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("soundcore-qa-session.json")
        guard FileManager.default.fileExists(atPath: receiptURL.path) else { throw XCTSkip("Requires an ignored, short-lived QA receipt from the running backend") }
        defer { try? FileManager.default.removeItem(at: receiptURL) }
        let receipt = try JSONDecoder().decode(RecordingDeviceSession.self, from: Data(contentsOf: receiptURL))
        let authenticated = expectation(description: "Official SDK license authentication")
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let adapter = SoundcoreWorkAdapter(root: root) { event in
            if case .authenticated(let valid) = event {
                XCTAssertTrue(valid, "Official SDK refused the ephemeral QA session")
                authenticated.fulfill()
            }
        }
        try adapter.initialize(receipt)
        await fulfillment(of: [authenticated], timeout: 30)
        adapter.close()
    }
}

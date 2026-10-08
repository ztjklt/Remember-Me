import Foundation
import CryptoKit
import Security

struct Pairing: Codable, Equatable {
    let baseURL: String
    let fingerprint: String
    let token: String
    let actorID: String
    let subjectID: String
    let consentID: String
}

struct PairingReply: Decodable {
    let actor_token: String
    let actor_id: String
    let subject_id: String
    let recording_consent_id: String
}

struct EpisodeCreated: Decodable { let episode_id: String }
struct Processing: Decodable {
    let status: String
    let error_code: String?
    let error_message: String?
}
struct TranscriptReview: Decodable {
    let state: String
    let transcript: String?
    let stt_model_version: String?
}
struct EvidenceRecord: Decodable, Identifiable {
    let evidence_id: String
    let excerpt: String?
    let source_type: String
    let source_ref: String
    let span_start: Int?
    let span_end: Int?
    var id: String { evidence_id }
}
struct MemoryRecord: Decodable, Identifiable {
    let memory_item_id: String
    let episode_id: String
    let content: String
    let memory_type: String
    let domain: String?
    let source_type: String
    let confidence: Double
    let model_version: String
    let recorded_at: String
    let transcript: String?
    let stt_model_version: String?
    let evidence: [EvidenceRecord]
    var id: String { memory_item_id }
}
struct MemoryListReply: Decodable { let items: [MemoryRecord] }
struct EpisodeRecord: Decodable, Identifiable {
    let episode_id: String
    let status: String
    let source: String
    let recorded_at: String
    let duration_ms: Int?
    let transcript: String?
    let stt_backend: String?
    let stt_model_version: String?
    let model_version: String?
    let error_code: String?
    var id: String { episode_id }
}
struct EpisodeListReply: Decodable { let items: [EpisodeRecord] }
struct TraitRecord: Decodable, Identifiable {
    let trait_id: String
    let statement: String
    let context: String?
    let confidence: Double
    let evidence_ids: [String]
    let counter_evidence_ids: [String]
    let status: String
    let model_version: String
    let source_type: String?
    let valid_from: String?
    let valid_to: String?
    let memory_item_ids: [String]?
    var id: String { trait_id }
}
struct DomainRecord: Decodable, Identifiable {
    let domain: String
    let traits: [TraitRecord]
    var id: String { domain }
}
struct PersonModelReply: Decodable {
    let version: Int
    let domains: [DomainRecord]
    let graph_facts: [GraphFactRecord]?
}
struct GraphFactRecord: Decodable, Identifiable {
    let fact_id: String
    let kind: String
    let content: String
    let evidence_ids: [String]
    let valid_from: String?
    var id: String { fact_id }
}
struct FacetRecord: Decodable {
    let category: String
    let label: String
    let quote: String
    let evidence_ids: [String]
}
struct AudioObservation: Decodable {
    let status: String
    let rms_dbfs: Double?
    let silence_fraction: Double?
    let clipped_fraction: Double?
    let analyzed_seconds: Double?
    let reason: String?
}
struct MemoryMetadata: Decodable {
    let facets: [FacetRecord]?
    let audio_observation: AudioObservation?
}
struct ProcessedMemory: Decodable {
    let content: String
    let evidence_ids: [String]
    let metadata: MemoryMetadata?
}
struct EpisodeResultReply: Decodable { let memory_items: [ProcessedMemory] }
struct QuestionRecord: Decodable, Identifiable {
    let question_id: String
    let text: String
    let target_domain: String
    let reason: String
    var id: String { question_id }
}
struct QuestionListReply: Decodable { let items: [QuestionRecord] }

struct ConsentRecord: Decodable, Identifiable {
    let consent_id: String
    let scope: String
    let status: String
    var id: String { consent_id }
}
struct TwinEvidenceRecord: Decodable, Identifiable {
    let evidence_id: String
    let excerpt: String?
    let episode_id: String
    let source_type: String
    var id: String { evidence_id }
}
struct TwinAnswerRecord: Decodable, Identifiable {
    let answer_id: String
    let question: String
    let answer: String
    let response_type: String
    let evidence: [TwinEvidenceRecord]
    let model_version: String
    let person_model_version: Int
    let stale: Bool
    var id: String { answer_id }
}
struct QueryTranscript: Decodable { let text: String; let stt_model_version: String }
struct VoiceProfileRecord: Decodable {
    let ready: Bool
    let profile_id: String?
    let model_version: String?
    let voice_consent_id: String?
}
struct SpeechRecord: Decodable { let status: String; let asset_id: String; let model_version: String }
struct MemorySearchRecord: Decodable, Identifiable {
    let memory_item_id: String
    let statement: String
    let domain: String?
    let evidence: [TwinEvidenceRecord]
    var id: String { memory_item_id }
}
struct MemorySearchReply: Decodable { let items: [MemorySearchRecord] }
struct CalibrationDimensionRecord: Decodable, Identifiable {
    let dimension: String
    let alignment: String
    let note: String
    let human_excerpt: String?
    var id: String { dimension }
}
struct CalibrationRecord: Decodable, Identifiable {
    let calibration_id: String
    let twin_answer_id: String
    let question: String
    let locked_answer: String?
    let status: String
    let human_episode_id: String?
    let summary: String?
    let dimensions: [CalibrationDimensionRecord]
    let suggested_question: String?
    let comparison_model_version: String?
    var id: String { calibration_id }
}
struct CalibrationListReply: Decodable { let items: [CalibrationRecord] }

enum APIError: LocalizedError {
    case invalidURL, invalidCertificate, server(Int, String), invalidResponse
    var errorDescription: String? {
        switch self {
        case .invalidURL: "本机服务地址无效，请检查 HTTPS 地址。"
        case .invalidCertificate: "服务器证书与配对时提供的指纹不一致。"
        case let .server(code, message): "本机服务返回 \(code)：\(message)"
        case .invalidResponse: "本机服务返回了无法识别的数据。"
        }
    }
}

final class CertificatePin: NSObject, URLSessionDelegate {
    private let expected: String
    init(_ fingerprint: String) { expected = fingerprint.lowercased().filter { $0.isHexDigit } }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust,
              let certificate = (SecTrustCopyCertificateChain(trust) as? [SecCertificate])?.first else {
            completionHandler(.cancelAuthenticationChallenge, nil); return
        }
        let digest = SHA256.hash(data: SecCertificateCopyData(certificate) as Data)
        let actual = digest.map { String(format: "%02x", $0) }.joined()
        if actual == expected {
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }
}

final class APIClient: @unchecked Sendable {
    let baseURL: URL
    private let session: URLSession
    private let token: String?

    init(baseURL: String, fingerprint: String, token: String? = nil, session: URLSession? = nil) throws {
        guard let url = URL(string: baseURL), url.scheme == "https", url.host != nil,
              fingerprint.filter({ $0.isHexDigit }).count == 64 else { throw APIError.invalidURL }
        self.baseURL = url
        self.token = token
        self.session = session ?? URLSession(configuration: .default, delegate: CertificatePin(fingerprint), delegateQueue: nil)
    }

    private func request(_ path: String, method: String = "GET", body: Data? = nil,
                         contentType: String? = nil) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.timeoutInterval = 300
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let contentType { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let raw = String(data: data, encoding: .utf8) ?? "未知错误"
            throw APIError.server(http.statusCode, raw.prefix(300).description)
        }
        return data
    }

    func claim(code: String) async throws -> PairingReply {
        let body = try JSONSerialization.data(withJSONObject: ["code": code])
        return try JSONDecoder().decode(PairingReply.self, from: await request(
            "/api/v1/local-pairing/claim", method: "POST", body: body,
            contentType: "application/json"))
    }

    func memories(_ id: String) async throws -> [MemoryRecord] {
        try JSONDecoder().decode(MemoryListReply.self, from: await request("/api/v1/subjects/\(id)/memories")).items
    }
    func episodes(_ id: String) async throws -> [EpisodeRecord] {
        try JSONDecoder().decode(EpisodeListReply.self, from: await request("/api/v1/subjects/\(id)/episodes")).items
    }
    func model(_ id: String) async throws -> PersonModelReply {
        try JSONDecoder().decode(PersonModelReply.self, from: await request("/api/v1/subjects/\(id)/person-model"))
    }
    func questions(_ id: String) async throws -> [QuestionRecord] {
        try JSONDecoder().decode(QuestionListReply.self, from: await request("/api/v1/subjects/\(id)/questions")).items
    }
    func status(_ episodeID: String) async throws -> Processing {
        try JSONDecoder().decode(Processing.self, from: await request("/api/v1/episodes/\(episodeID)"))
    }
    func result(_ episodeID: String) async throws -> [ProcessedMemory] {
        try JSONDecoder().decode(EpisodeResultReply.self, from: await request("/api/v1/episodes/\(episodeID)/result")).memory_items
    }
    func transcriptReview(_ episodeID: String) async throws -> TranscriptReview {
        try JSONDecoder().decode(TranscriptReview.self, from: await request(
            "/api/v1/episodes/\(episodeID)/transcript-review"))
    }
    func confirmTranscript(_ episodeID: String, transcript: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["transcript": transcript])
        _ = try await request("/api/v1/episodes/\(episodeID)/transcript-review",
                              method: "PATCH", body: body, contentType: "application/json")
    }
    func retry(_ episodeID: String) async throws {
        _ = try await request("/api/v1/episodes/\(episodeID)/retry", method: "POST")
    }
    func audio(_ episodeID: String) async throws -> Data {
        try await request("/api/v1/episodes/\(episodeID)/audio")
    }
    func correct(subjectID: String, memoryID: String, content: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["content": content])
        _ = try await request("/api/v1/subjects/\(subjectID)/memories/\(memoryID)",
                              method: "PATCH", body: body, contentType: "application/json")
    }
    func delete(subjectID: String, memoryID: String) async throws {
        _ = try await request("/api/v1/subjects/\(subjectID)/memories/\(memoryID)", method: "DELETE")
    }

    func consents(subjectID: String) async throws -> [ConsentRecord] {
        try JSONDecoder().decode([ConsentRecord].self, from: await request(
            "/api/v1/consents?subject_id=\(subjectID)"))
    }
    func searchMemories(subjectID: String, query: String) async throws -> [MemorySearchRecord] {
        let escaped = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        return try JSONDecoder().decode(MemorySearchReply.self, from: await request(
            "/api/v1/subjects/\(subjectID)/memory-search?q=\(escaped)")).items
    }
    func grantConsent(subjectID: String, scope: String) async throws -> ConsentRecord {
        let body = try JSONSerialization.data(withJSONObject: ["subject_id": subjectID, "scope": scope,
                                                               "evidence_ref": "ios-explicit-confirmation"])
        return try JSONDecoder().decode(ConsentRecord.self, from: await request(
            "/api/v1/consents", method: "POST", body: body, contentType: "application/json"))
    }
    func revokeConsent(_ id: String) async throws {
        _ = try await request("/api/v1/consents/\(id)/revoke", method: "POST")
    }
    func askTwin(subjectID: String, question: String, cloudConsentID: String) async throws -> TwinAnswerRecord {
        let body = try JSONSerialization.data(withJSONObject: ["question": question, "cloud_consent_id": cloudConsentID])
        return try JSONDecoder().decode(TwinAnswerRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/answers", method: "POST", body: body,
            contentType: "application/json"))
    }
    func twinAnswer(subjectID: String, answerID: String) async throws -> TwinAnswerRecord {
        try JSONDecoder().decode(TwinAnswerRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/answers/\(answerID)"))
    }
    func transcribeQuery(subjectID: String, audio: Data) async throws -> QueryTranscript {
        try JSONDecoder().decode(QueryTranscript.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/transcribe-query", method: "POST",
            body: audio, contentType: "audio/mp4"))
    }
    func voiceProfile(subjectID: String) async throws -> VoiceProfileRecord {
        try JSONDecoder().decode(VoiceProfileRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/voice/profile"))
    }
    func enrollVoice(subjectID: String, consentID: String, transcript: String, audio: Data) async throws -> VoiceProfileRecord {
        let boundary = "RememberMe-\(UUID().uuidString)"
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        field("voice_consent_id", consentID)
        field("transcript", transcript)
        field("own_voice_confirmed", "true")
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"sample\"; filename=\"sample.m4a\"\r\nContent-Type: audio/mp4\r\n\r\n".utf8))
        body.append(audio)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return try JSONDecoder().decode(VoiceProfileRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/voice/profile", method: "POST", body: body,
            contentType: "multipart/form-data; boundary=\(boundary)"))
    }
    func createSpeech(subjectID: String, answerID: String) async throws -> SpeechRecord {
        try JSONDecoder().decode(SpeechRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/answers/\(answerID)/speech", method: "POST"))
    }
    func speechAudio(subjectID: String, assetID: String) async throws -> Data {
        try await request("/api/v1/subjects/\(subjectID)/voice/assets/\(assetID)/audio")
    }
    func calibrations(subjectID: String) async throws -> [CalibrationRecord] {
        try JSONDecoder().decode(CalibrationListReply.self, from: await request(
            "/api/v1/subjects/\(subjectID)/calibrations")).items
    }
    func startCalibration(subjectID: String, answerID: String,
                          cloudConsentID: String) async throws -> CalibrationRecord {
        let body = try JSONSerialization.data(withJSONObject: ["twin_answer_id": answerID,
                                                               "cloud_consent_id": cloudConsentID])
        return try JSONDecoder().decode(CalibrationRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/calibrations", method: "POST", body: body,
            contentType: "application/json"))
    }
    func completeCalibration(subjectID: String, calibrationID: String,
                             cloudConsentID: String) async throws -> CalibrationRecord {
        let body = try JSONSerialization.data(withJSONObject: ["cloud_consent_id": cloudConsentID])
        return try JSONDecoder().decode(CalibrationRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/calibrations/\(calibrationID)/complete",
            method: "POST", body: body, contentType: "application/json"))
    }

    func upload(_ draft: RecordingDraft, pairing: Pairing) async throws -> String {
        let audio = try Data(contentsOf: draft.fileURL)
        let boundary = "RememberMe-\(UUID().uuidString)"
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        field("subject_id", pairing.subjectID)
        field("source", "IOS_MIC")
        field("recorded_at", ISO8601DateFormatter().string(from: draft.recordedAt))
        field("audio_ref", draft.id + ".m4a")
        field("idempotency_key", draft.id)
        field("recording_consent_id", pairing.consentID)
        field("duration_ms", String(draft.durationMS))
        var metadata: [String: String] = ["consent_confirmed_at": ISO8601DateFormatter().string(from: draft.consentConfirmedAt)]
        if let questionID = draft.questionID { metadata["question_id"] = questionID }
        if let calibrationID = draft.calibrationID { metadata["calibration_id"] = calibrationID }
        let metadataData = try JSONSerialization.data(withJSONObject: metadata)
        field("metadata", String(data: metadataData, encoding: .utf8) ?? "{}")
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"recording.m4a\"\r\nContent-Type: audio/mp4\r\n\r\n".utf8))
        body.append(audio)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let data = try await request("/api/v1/episodes", method: "POST", body: body,
                                     contentType: "multipart/form-data; boundary=\(boundary)")
        return try JSONDecoder().decode(EpisodeCreated.self, from: data).episode_id
    }
}

enum PairingStore {
    private static let account = "local-pairing"
    static func save(_ pairing: Pairing) throws {
        let data = try JSONEncoder().encode(pairing)
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                    kSecAttrService as String: "me.remember.personal",
                                    kSecAttrAccount as String: account]
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw APIError.invalidResponse }
    }
    static func load() -> Pairing? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                    kSecAttrService as String: "me.remember.personal",
                                    kSecAttrAccount as String: account,
                                    kSecReturnData as String: true,
                                    kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(Pairing.self, from: data)
    }
}

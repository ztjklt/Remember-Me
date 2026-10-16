import Foundation
import CryptoKit
import Security

struct Pairing: Codable {
    let baseURL: String
    let fingerprint: String
    let token: String
    let actorID: String
    let subjectID: String
    let consentID: String
    var connectionKind: String? = nil
    var displayName: String? = nil
    var spaceName: String? = nil
    var isCloud: Bool { connectionKind == "ecs" || connectionKind == "cloudbase" }
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
    var machine_transcript: String? = nil
    var automatic_correction: TranscriptCorrection? = nil
    var supplement: String? = nil
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
    let capture_source: String?
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
    var speaker_report: SpeakerReport? = nil
    var capture_origin: String? = nil
    var cumulative_analysis: CaptureAnalysisStatus? = nil
    var waiting_for_review: Bool? = nil
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
    var id: String { trait_id }
}
struct DomainRecord: Decodable, Identifiable {
    let domain: String
    let traits: [TraitRecord]
    var id: String { domain }
}
struct GraphFactRecord: Decodable, Identifiable {
    let fact_id: String
    let subject_id: String
    let kind: String
    let content: String
    let evidence_ids: [String]
    let model_version: String
    let valid_from: String?
    let valid_to: String?
    var id: String { fact_id }
}
struct PersonModelReply: Decodable {
    let version: Int
    let domains: [DomainRecord]
    let graph_facts: [GraphFactRecord]
    init(version: Int, domains: [DomainRecord], graphFacts: [GraphFactRecord] = []) {
        self.version = version; self.domains = domains; graph_facts = graphFacts
    }
    private enum CodingKeys: String, CodingKey { case version, domains, graph_facts }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        version = try values.decode(Int.self, forKey: .version)
        domains = try values.decode([DomainRecord].self, forKey: .domains)
        graph_facts = try values.decodeIfPresent([GraphFactRecord].self, forKey: .graph_facts) ?? []
    }
}
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
    let has_audio: Bool?
    var id: String { evidence_id }
}
struct TwinExpressionRecord: Decodable {
    let status: String
    let text: String
    let model_version: String
    let prompt_version: String
}
struct ChatMemoryReply: Decodable {
    let episode_id: String
    let memory_item_id: String
    let source: String
    let status: String
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
    let expression: TwinExpressionRecord?
    let conversation_id: String?
    let parent_answer_id: String?
    let context_turn_count: Int?
    let context_truncated: Bool?
    let recalled_turn_count: Int?
    let history_summary_status: String?
    let recalled_answer_ids: [String]?
    let remembered_episode_id: String?
    var checkedExpression: String? {
        guard !stale, response_type == "SIMULATION", let expression,
              expression.status == "available", expression.text.count <= 500,
              !expression.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return expression.text
    }
    var displayText: String { checkedExpression ?? answer }
    var id: String { answer_id }
}
struct HistoricalChatTurn: Decodable, Identifiable {
    let answer_id: String
    let question: String
    let answer: String?
    let assistant_stale: Bool
    let created_at: String
    var deletion_pending: Bool? = nil
    var id: String { answer_id }
}
struct TwinAnswerHistory: Decodable {
    let items: [HistoricalChatTurn]
    let next_cursor: String?
}
struct HistoricalChatSummary: Decodable, Identifiable {
    let summary: String
    let source_answer_ids: [String]
    let created_at: String
    var id: String { source_answer_ids.joined(separator: ",") }
}
struct ChatHistoryMemory: Decodable {
    let enabled: Bool
    let available_turn_count: Int
    let items: [HistoricalChatTurn]
    let summaries: [HistoricalChatSummary]
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
        case .invalidURL: "服务地址无效，请检查 HTTPS 地址。"
        case .invalidCertificate: "服务器证书与配对时提供的指纹不一致。"
        case let .server(code, message): "服务返回 \(code)：\(message)"
        case .invalidResponse: "服务返回了无法识别的数据。"
        }
    }
}

final class CertificatePin: NSObject, URLSessionDelegate, URLSessionTaskDelegate {
    private let expected: String
    init(_ fingerprint: String) { expected = fingerprint.lowercased().filter { $0.isHexDigit } }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }

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
            // Trust the pinned certificate as an anchor, while still validating
            // its hostname, validity period, and SSL policy.
            SecTrustSetAnchorCertificates(trust, [certificate] as CFArray)
            SecTrustSetAnchorCertificatesOnly(trust, true)
            guard SecTrustEvaluateWithError(trust, nil) else {
                completionHandler(.cancelAuthenticationChallenge, nil); return
            }
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }
}

final class SystemCertificateTrust: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
    // Server-trust challenges use URLSession's default certificate-chain and
    // hostname validation. No custom trust anchor is installed for CloudBase.
}

final class APIClient: @unchecked Sendable {
    let baseURL: URL
    private let session: URLSession
    private let token: String?

    init(baseURL: String, fingerprint: String, token: String? = nil, session: URLSession? = nil) throws {
        let systemTrust = baseURL == ECSConfiguration.baseURL && fingerprint.isEmpty
        guard let url = URL(string: baseURL), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil,
              systemTrust || fingerprint.filter({ $0.isHexDigit }).count == 64 else { throw APIError.invalidURL }
        self.baseURL = url
        self.token = token
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        let delegate: any URLSessionDelegate = systemTrust ? SystemCertificateTrust() : CertificatePin(fingerprint)
        self.session = session ?? URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
    }

    func request(_ path: String, method: String = "GET", body: Data? = nil,
                         contentType: String? = nil, timeout: TimeInterval = 300, headers: [String: String] = [:]) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.timeoutInterval = timeout
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let contentType { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let decoded = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let error = decoded?["error"] as? [String: Any]
            let message = error?["message"] as? String ?? decoded?["error_message"] as? String ?? decoded?["detail"] as? String ?? "请求未完成，请稍后重试。"
            throw APIError.server(http.statusCode, String(message.prefix(300)))
        }
        return data
    }

    func serviceInfo() async throws -> CloudServiceInfo {
        try JSONDecoder().decode(CloudServiceInfo.self, from: await request("/api/v1/service-info", timeout: 15))
    }
    /// Same trust/auth boundary as JSON requests; never a vendor URL or token.
    func voiceAudioBytes(_ path: String) async throws -> URLSession.AsyncBytes {
        guard let url = URL(string: path, relativeTo: baseURL) else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard http.statusCode == 200 else { throw APIError.server(http.statusCode, "本人声音暂时无法播放。") }
        guard http.value(forHTTPHeaderField: "Content-Type")?.hasPrefix("audio/pcm") == true,
              http.value(forHTTPHeaderField: "X-Audio-Sample-Rate") == "24000",
              http.value(forHTTPHeaderField: "X-Audio-Channels") == "1" else { throw APIError.invalidResponse }
        return bytes
    }
    func login(username: String, password: String) async throws -> CloudLoginReply {
        let body = try JSONSerialization.data(withJSONObject: ["username": username, "password": password])
        return try JSONDecoder().decode(CloudLoginReply.self, from: await request(
            "/api/v1/accounts/login", method: "POST", body: body, contentType: "application/json", timeout: 30))
    }
    func logout() async throws { _ = try await request("/api/v1/accounts/logout", method: "POST", timeout: 15) }
    func spaces() async throws -> CloudSpacesReply {
        try JSONDecoder().decode(CloudSpacesReply.self, from: await request("/api/v1/workbench/spaces", timeout: 15))
    }
    func capabilities() async throws -> BackendCapabilities {
        try JSONDecoder().decode(BackendCapabilities.self, from: await request("/api/v1/workbench/capabilities", timeout: 15))
    }

    func claim(code: String) async throws -> PairingReply {
        let body = try JSONSerialization.data(withJSONObject: ["code": code])
        return try JSONDecoder().decode(PairingReply.self, from: await request(
            "/api/v1/local-pairing/claim", method: "POST", body: body,
            contentType: "application/json", timeout: 15))
    }

    func memories(_ id: String) async throws -> [MemoryRecord] {
        try JSONDecoder().decode(MemoryListReply.self, from: await request("/api/v1/subjects/\(id)/memories", timeout: 30)).items
    }
    func episodes(_ id: String) async throws -> [EpisodeRecord] {
        try JSONDecoder().decode(EpisodeListReply.self, from: await request("/api/v1/subjects/\(id)/episodes", timeout: 30)).items
    }
    func model(_ id: String) async throws -> PersonModelReply {
        try JSONDecoder().decode(PersonModelReply.self, from: await request("/api/v1/subjects/\(id)/person-model", timeout: 30))
    }
    func questions(_ id: String) async throws -> [QuestionRecord] {
        try JSONDecoder().decode(QuestionListReply.self, from: await request("/api/v1/subjects/\(id)/questions", timeout: 30)).items
    }
    func status(_ episodeID: String) async throws -> Processing {
        try JSONDecoder().decode(Processing.self, from: await request("/api/v1/episodes/\(episodeID)", timeout: 15))
    }
    func transcriptReview(_ episodeID: String) async throws -> TranscriptReview {
        try JSONDecoder().decode(TranscriptReview.self, from: await request(
            "/api/v1/episodes/\(episodeID)/transcript-review", timeout: 15))
    }
    func confirmTranscript(_ episodeID: String, transcript: String, supplement: String = "", cloudAnalysisConsentID: String? = nil) async throws {
        var payload: [String: String] = ["transcript": transcript]
        if !supplement.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { payload["supplement"] = supplement }
        if let cloudAnalysisConsentID { payload["cloud_analysis_consent_id"] = cloudAnalysisConsentID }
        let body = try JSONSerialization.data(withJSONObject: payload)
        _ = try await request("/api/v1/episodes/\(episodeID)/transcript-review",
                              method: "PATCH", body: body, contentType: "application/json")
    }
    func retry(_ episodeID: String) async throws {
        _ = try await request("/api/v1/episodes/\(episodeID)/retry", method: "POST")
    }
    func deleteRecording(_ episodeID: String) async throws {
        struct Receipt: Decodable { let deleted: Bool; let cleanup_pending: Bool }
        let receipt = try JSONDecoder().decode(Receipt.self, from: await request(
            "/api/v1/episodes/\(episodeID)", method: "DELETE", timeout: 30))
        guard receipt.deleted && !receipt.cleanup_pending else {
            throw APIError.server(503, "录音访问已关闭，原音清理暂未完成，请再试一次。")
        }
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
            "/api/v1/consents?subject_id=\(subjectID)", timeout: 30))
    }
    func searchMemories(subjectID: String, query: String) async throws -> [MemorySearchRecord] {
        var parts = URLComponents()
        parts.path = "/api/v1/subjects/\(subjectID)/memory-search"
        parts.queryItems = [URLQueryItem(name: "q", value: query)]
        // Query parameters use form decoding on the server: a literal '+'
        // must be escaped even though URLComponents permits it in a query.
        parts.percentEncodedQuery = parts.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        return try JSONDecoder().decode(MemorySearchReply.self, from: await request(parts.string!)).items
    }
    func grantConsent(subjectID: String, scope: String, evidenceRef: String = "ios-explicit-confirmation") async throws -> ConsentRecord {
        let body = try JSONSerialization.data(withJSONObject: ["subject_id": subjectID, "scope": scope,
                                                               "evidence_ref": evidenceRef])
        return try JSONDecoder().decode(ConsentRecord.self, from: await request(
            "/api/v1/consents", method: "POST", body: body, contentType: "application/json"))
    }
    func revokeConsent(_ id: String) async throws {
        _ = try await request("/api/v1/consents/\(id)/revoke", method: "POST")
    }
    func askTwin(subjectID: String, question: String, cloudConsentID: String,
                 conversationMode: Bool = false, previousAnswerID: String? = nil, requestID: String? = nil) async throws -> TwinAnswerRecord {
        var fields: [String: Any] = ["question": question, "cloud_consent_id": cloudConsentID]
        if conversationMode {
            fields["conversation_mode"] = true
            if let previousAnswerID { fields["previous_answer_id"] = previousAnswerID }
            if let requestID { fields["request_id"] = requestID }
        }
        let body = try JSONSerialization.data(withJSONObject: fields)
        return try JSONDecoder().decode(TwinAnswerRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/answers", method: "POST", body: body,
            contentType: "application/json"))
    }
    func rememberChatMessage(subjectID: String, answerID: String, cloudConsentID: String,
                             recordingConsentID: String) async throws -> ChatMemoryReply {
        let body = try JSONSerialization.data(withJSONObject: ["cloud_consent_id": cloudConsentID,
            "recording_consent_id": recordingConsentID, "confirmed": true])
        return try JSONDecoder().decode(ChatMemoryReply.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/answers/\(answerID)/remember", method: "POST",
            body: body, contentType: "application/json", timeout: 30))
    }
    func chatHistoryMemory(subjectID: String, cloudConsentID: String, query: String = "", answerIDs: [String] = []) async throws -> ChatHistoryMemory {
        var components = URLComponents()
        components.path = "/api/v1/subjects/\(subjectID)/twin/chat-memory"
        components.queryItems = [URLQueryItem(name: "cloud_consent_id", value: cloudConsentID), URLQueryItem(name: "q", value: query)]
        if !answerIDs.isEmpty { components.queryItems?.append(URLQueryItem(name: "answer_ids", value: answerIDs.joined(separator: ","))) }
        components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        guard let path = components.string else { throw APIError.invalidURL }
        return try JSONDecoder().decode(ChatHistoryMemory.self, from: await request(path, timeout: 45))
    }
    func twinAnswerHistory(subjectID: String, cloudConsentID: String, cursor: String? = nil) async throws -> TwinAnswerHistory {
        var components = URLComponents()
        components.path = "/api/v1/subjects/\(subjectID)/twin/answer-history"
        components.queryItems = [URLQueryItem(name: "cloud_consent_id", value: cloudConsentID)]
        if let cursor { components.queryItems?.append(URLQueryItem(name: "cursor", value: cursor)) }
        components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        guard let path = components.string else { throw APIError.invalidURL }
        return try JSONDecoder().decode(TwinAnswerHistory.self, from: await request(path, timeout: 25))
    }
    func deleteTwinAnswer(subjectID: String, answerID: String) async throws -> Bool {
        struct Receipt: Decodable { let deleted: Bool; let cleanup_pending: Bool }
        let receipt = try JSONDecoder().decode(Receipt.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/answers/\(answerID)", method: "DELETE", timeout: 25))
        guard receipt.deleted else { throw APIError.invalidResponse }
        return !receipt.cleanup_pending
    }
    func setChatHistoryMemory(subjectID: String, enabled: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["enabled": enabled])
        _ = try await request("/api/v1/subjects/\(subjectID)/twin/chat-memory", method: "PUT", body: body, contentType: "application/json", timeout: 20)
    }
    func clearChatHistoryMemory(subjectID: String) async throws {
        _ = try await request("/api/v1/subjects/\(subjectID)/twin/chat-memory", method: "DELETE", timeout: 20)
    }
    func twinAnswer(subjectID: String, answerID: String) async throws -> TwinAnswerRecord {
        let answer = try JSONDecoder().decode(TwinAnswerRecord.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/answers/\(answerID)", timeout: 15))
        guard answer.id == answerID else { throw APIError.invalidResponse }
        return answer
    }
    func transcribeQuery(subjectID: String, audio: Data, cloudASRPolicy: String? = nil) async throws -> QueryTranscript {
        try JSONDecoder().decode(QueryTranscript.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/transcribe-query", method: "POST",
            body: audio, contentType: "audio/mp4", headers: cloudASRPolicy.map { ["X-Cloud-ASR-Policy": $0] } ?? [:]))
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
            "/api/v1/subjects/\(subjectID)/calibrations", timeout: 30)).items
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

    func upload(_ draft: RecordingDraft, pairing: Pairing, cloudASRPolicy: String? = nil, speakerConsent: String? = nil, transcriptCorrectionPolicy: String? = nil) async throws -> String {
        let audio = try Data(contentsOf: draft.fileURL)
        let boundary = "RememberMe-\(UUID().uuidString)"
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        field("subject_id", pairing.subjectID)
        field("source", draft.captureSource ?? "IOS_MIC")
        field("recorded_at", ISO8601DateFormatter().string(from: draft.recordedAt))
        field("audio_ref", draft.fileURL.lastPathComponent)
        field("idempotency_key", draft.id)
        field("recording_consent_id", pairing.consentID)
        field("duration_ms", String(draft.durationMS))
        var metadata: [String: String] = draft.captureMetadata ?? [:]
        metadata["consent_confirmed_at"] = ISO8601DateFormatter().string(from: draft.consentConfirmedAt)
        if let cloudASRPolicy { metadata["cloud_asr_policy"] = cloudASRPolicy }
        if let speakerConsent { metadata["voiceprint_consent_id"] = speakerConsent }
        if let transcriptCorrectionPolicy { metadata["transcript_correction_policy"] = transcriptCorrectionPolicy }
        if let questionID = draft.questionID { metadata["question_id"] = questionID }
        if let calibrationID = draft.calibrationID { metadata["calibration_id"] = calibrationID }
        let metadataData = try JSONSerialization.data(withJSONObject: metadata)
        field("metadata", String(data: metadataData, encoding: .utf8) ?? "{}")
        let ext = draft.fileURL.pathExtension.lowercased()
        let mime = ["wav": "audio/wav", "caf": "audio/x-caf", "aac": "audio/aac", "mp3": "audio/mpeg"][ext] ?? "audio/mp4"
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"recording.\(ext)\"\r\nContent-Type: \(mime)\r\n\r\n".utf8))
        body.append(audio)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let data = try await request("/api/v1/episodes", method: "POST", body: body,
                                     contentType: "multipart/form-data; boundary=\(boundary)")
        return try JSONDecoder().decode(EpisodeCreated.self, from: data).episode_id
    }
}

enum PairingStore {
    private static let account = "local-pairing"
    static func save(_ pairing: Pairing, account: String = "local-pairing") throws {
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
    static func clear(account: String = "local-pairing") {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword,
                       kSecAttrService as String: "me.remember.personal",
                       kSecAttrAccount as String: account] as CFDictionary)
    }
    static func load(account: String = "local-pairing") -> Pairing? {
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

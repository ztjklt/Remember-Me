import Foundation

struct EpisodeCreated: Decodable {
    let episodeId: String
    let uploadStatus: String
}

struct EpisodeStatus: Decodable {
    let episodeId: String
    let status: String
    let progress: Double?
    let errorCode: String?
    let errorMessage: String?
}

struct MemoryItem: Decodable, Identifiable {
    let memoryType: String
    let content: String
    let sourceType: String
    let evidenceIds: [String]
    let confidence: Double
    let modelVersion: String
    let promptVersion: String
    let schemaVersion: String

    var id: String { "\(memoryType):\(evidenceIds.joined(separator: ",")):\(content)" }
}

struct EpisodeResult: Decodable {
    let episodeId: String
    let status: String
    let memoryItems: [MemoryItem]
    let modelVersion: String
}

struct RecordingConsent: Decodable {
    let consentId: String
    let status: String
}

private struct ConsentAuthorization: Decodable {
    let authorized: Bool
    let scope: String
}

struct EvidenceView: Decodable, Identifiable {
    let evidenceId: String
    let sourceType: String
    let sourceRef: String
    let excerpt: String?
    let confidence: Double?

    var id: String { evidenceId }
}

struct SubjectMemory: Decodable, Identifiable {
    let memoryItemId: String
    let episodeId: String
    let recordedAt: String
    let memoryType: String
    let domain: String
    let content: String
    let sourceType: String
    let confidence: Double
    let evidence: [EvidenceView]
    let modelVersion: String
    let correction: String?

    var id: String { memoryItemId }
}

struct SubjectMemories: Decodable {
    let subjectId: String
    let items: [SubjectMemory]
    let domainCounts: [String: Int]
}

struct TwinAnswer: Decodable {
    let subjectId: String
    let question: String
    let answer: String
    let responseType: String
    let confidence: Double
    let evidence: [EvidenceView]
    let modelVersion: String?
}

struct CalibrationGaps: Codable {
    var decision = false
    var reasoning = false
    var valuePriority = false
    var emotionalReaction = false
    var expression = false
}

struct CalibrationRecord: Decodable, Identifiable {
    let calibrationId: String
    let subjectId: String
    let question: String
    let lockedAnswer: String
    let responseType: String
    let confidence: Double
    let modelVersion: String?
    let evidenceIds: [String]
    let humanAnswer: String?
    let gaps: CalibrationGaps?

    var id: String { calibrationId }
}

struct LegacyGrantRecord: Decodable, Identifiable {
    let grantId: String
    let subjectId: String
    let recipientActorId: String
    let allowedDomains: [String]
    let status: String
    let snapshotCount: Int

    var id: String { grantId }
}

struct RecipientMemoryList: Decodable {
    let subjectId: String
    let mode: String
    let items: [SubjectMemory]
}

struct PersonModelFact: Decodable, Identifiable {
    let memoryItemId: String
    let episodeId: String
    let content: String
    let sourceType: String
    let evidenceIds: [String]
    let confidence: Double
    let modelVersion: String

    var id: String { memoryItemId }
}

struct PersonModelPreview: Decodable {
    let subjectId: String
    let revision: Int
    let modelVersion: String
    let sourceMemoryIds: [String]
    let domains: [String: [PersonModelFact]]
}

enum EpisodeAPIError: LocalizedError {
    case invalidServerURL
    case missingCredentials
    case oversizedAudio
    case invalidResponse
    case http(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidServerURL: return "Backend 地址必须是有效的 http(s) 根地址。"
        case .missingCredentials: return "请先填写 Actor 令牌和 Subject ID。"
        case .oversizedAudio: return "录音超过 Backend 的 25 MiB 上传限制。"
        case .invalidResponse: return "Backend 返回了无法识别的数据。"
        case .http(let status, let message): return "Backend \(status)：\(message)"
        }
    }
}

enum MultipartCapture {
    // Contract v0.1.2 has no IOS_MIC source. An iOS recording is uploaded as a
    // local file through IMPORT until a versioned source-enum proposal is approved.
    static func body(
        audio: Data,
        fileName: String,
        subjectID: String,
        recordingConsentID: String,
        recordedAt: Date,
        idempotencyKey: String,
        boundary: String
    ) -> Data {
        var result = Data()
        let date = ISO8601DateFormatter().string(from: recordedAt)
        let fields = [
            ("subject_id", subjectID),
            ("source", "IMPORT"),
            ("recorded_at", date),
            ("audio_ref", fileName),
            ("idempotency_key", idempotencyKey),
            ("recording_consent_id", recordingConsentID)
        ]
        for (name, value) in fields {
            result.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        let safeName = fileName.replacingOccurrences(of: "\"", with: "_")
            .replacingOccurrences(of: "\r", with: "_")
            .replacingOccurrences(of: "\n", with: "_")
        let contentType = fileName.lowercased().hasSuffix(".wav") ? "audio/wav" : "audio/mp4"
        result.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(safeName)\"\r\nContent-Type: \(contentType)\r\n\r\n".utf8))
        result.append(audio)
        result.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return result
    }
}

struct EpisodeAPI {
    let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func grantRecordingConsent(settings: ServerSettings) async throws -> RecordingConsent {
        try await grantConsent(scope: "RECORDING", settings: settings)
    }

    func grantCloudTwinConsent(settings: ServerSettings) async throws -> RecordingConsent {
        try await grantConsent(scope: "CLOUD_TWIN", settings: settings)
    }

    func grantHandoverConsent(settings: ServerSettings) async throws -> RecordingConsent {
        try await grantConsent(scope: "DIGITAL_HANDOVER", settings: settings)
    }

    func grantVoiceConsent(settings: ServerSettings) async throws -> RecordingConsent {
        try await grantConsent(scope: "VOICE", settings: settings)
    }

    func authorizeVoice(settings: ServerSettings) async throws {
        guard !settings.voiceConsentID.isEmpty else { throw EpisodeAPIError.missingCredentials }
        var request = try authorizedRequest(
            path: "api/v1/consents/authorize", method: "POST", settings: settings
        )
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "subject_id": settings.subjectID,
            "scope": "VOICE",
            "consent_id": settings.voiceConsentID
        ])
        let result = try await decode(ConsentAuthorization.self, request: request)
        guard result.authorized, result.scope == "VOICE" else { throw EpisodeAPIError.invalidResponse }
    }

    private func grantConsent(scope: String, settings: ServerSettings) async throws -> RecordingConsent {
        guard !settings.subjectID.isEmpty, !settings.token.isEmpty else {
            throw EpisodeAPIError.missingCredentials
        }
        var request = try authorizedRequest(path: "api/v1/consents", method: "POST", settings: settings)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "subject_id": settings.subjectID,
            "scope": scope,
            "evidence_ref": "iOS in-app explicit \(scope) consent"
        ])
        return try await decode(RecordingConsent.self, request: request)
    }

    func memories(settings: ServerSettings) async throws -> SubjectMemories {
        guard !settings.subjectID.isEmpty else { throw EpisodeAPIError.missingCredentials }
        let id = settings.subjectID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? settings.subjectID
        let request = try authorizedRequest(path: "api/v1/subjects/\(id)/memories", method: "GET", settings: settings)
        return try await decode(SubjectMemories.self, request: request)
    }

    func personModel(settings: ServerSettings) async throws -> PersonModelPreview {
        guard !settings.subjectID.isEmpty else { throw EpisodeAPIError.missingCredentials }
        let id = settings.subjectID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? settings.subjectID
        let request = try authorizedRequest(
            path: "api/v1/subjects/\(id)/person-model", method: "GET", settings: settings
        )
        return try await decode(PersonModelPreview.self, request: request)
    }

    func twin(question: String, settings: ServerSettings) async throws -> TwinAnswer {
        guard !settings.subjectID.isEmpty, !settings.cloudTwinConsentID.isEmpty else {
            throw EpisodeAPIError.missingCredentials
        }
        let id = settings.subjectID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? settings.subjectID
        var request = try authorizedRequest(path: "api/v1/subjects/\(id)/twin/query", method: "POST", settings: settings)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "question": question,
            "cloud_twin_consent_id": settings.cloudTwinConsentID
        ])
        return try await decode(TwinAnswer.self, request: request)
    }

    func correctMemory(id: String, proposedContent: String, settings: ServerSettings) async throws {
        var request = try authorizedRequest(
            path: memoryPath(id: id, settings: settings) + "/correction",
            method: "PUT", settings: settings
        )
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["proposed_content": proposedContent])
        _ = try await decode(CorrectionReceipt.self, request: request)
    }

    func removeCorrection(id: String, settings: ServerSettings) async throws {
        let request = try authorizedRequest(
            path: memoryPath(id: id, settings: settings) + "/correction",
            method: "DELETE", settings: settings
        )
        try await requireNoContent(request)
    }

    func deleteMemory(id: String, settings: ServerSettings) async throws {
        let request = try authorizedRequest(
            path: memoryPath(id: id, settings: settings), method: "DELETE", settings: settings
        )
        try await requireNoContent(request)
    }

    func startCalibration(question: String, settings: ServerSettings) async throws -> CalibrationRecord {
        guard !settings.cloudTwinConsentID.isEmpty else { throw EpisodeAPIError.missingCredentials }
        var request = try authorizedRequest(
            path: calibrationPath(settings: settings), method: "POST", settings: settings
        )
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "question": question,
            "cloud_twin_consent_id": settings.cloudTwinConsentID
        ])
        return try await decode(CalibrationRecord.self, request: request)
    }

    func submitCalibration(
        id: String, humanAnswer: String, gaps: CalibrationGaps,
        settings: ServerSettings
    ) async throws -> CalibrationRecord {
        let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        var request = try authorizedRequest(
            path: calibrationPath(settings: settings) + "/\(encoded)/answer",
            method: "POST", settings: settings
        )
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        request.httpBody = try encoder.encode(CalibrationSubmission(humanAnswer: humanAnswer, gaps: gaps))
        return try await decode(CalibrationRecord.self, request: request)
    }

    func calibrations(settings: ServerSettings) async throws -> [CalibrationRecord] {
        let request = try authorizedRequest(
            path: calibrationPath(settings: settings), method: "GET", settings: settings
        )
        return try await decode([CalibrationRecord].self, request: request)
    }

    func createLegacyGrant(
        recipientActorID: String, domains: [String], settings: ServerSettings
    ) async throws -> LegacyGrantRecord {
        guard !settings.handoverConsentID.isEmpty else { throw EpisodeAPIError.missingCredentials }
        var request = try authorizedRequest(
            path: handoverPath(settings: settings), method: "POST", settings: settings
        )
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "recipient_actor_id": recipientActorID,
            "handover_consent_id": settings.handoverConsentID,
            "allowed_domains": domains
        ])
        return try await decode(LegacyGrantRecord.self, request: request)
    }

    func handoverGrants(settings: ServerSettings) async throws -> [LegacyGrantRecord] {
        let request = try authorizedRequest(
            path: handoverPath(settings: settings), method: "GET", settings: settings
        )
        return try await decode([LegacyGrantRecord].self, request: request)
    }

    func activateLegacyPreview(id: String, settings: ServerSettings) async throws -> LegacyGrantRecord {
        let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        var request = try authorizedRequest(
            path: handoverPath(settings: settings) + "/\(encoded)/activate-preview",
            method: "POST", settings: settings
        )
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["confirmation": "ACTIVATE_PREVIEW"])
        return try await decode(LegacyGrantRecord.self, request: request)
    }

    func revokeLegacyGrant(id: String, settings: ServerSettings) async throws -> LegacyGrantRecord {
        let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        let request = try authorizedRequest(
            path: handoverPath(settings: settings) + "/\(encoded)/revoke",
            method: "POST", settings: settings
        )
        return try await decode(LegacyGrantRecord.self, request: request)
    }

    func legacyRecipientMemories(settings: ServerSettings) async throws -> RecipientMemoryList {
        let subject = settings.subjectID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? settings.subjectID
        let request = try authorizedRequest(
            path: "api/v1/subjects/\(subject)/legacy-preview/memories",
            method: "GET", settings: settings
        )
        return try await decode(RecipientMemoryList.self, request: request)
    }

    private func handoverPath(settings: ServerSettings) -> String {
        let subject = settings.subjectID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? settings.subjectID
        return "api/v1/subjects/\(subject)/handover/grants"
    }

    private func calibrationPath(settings: ServerSettings) -> String {
        let subject = settings.subjectID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? settings.subjectID
        return "api/v1/subjects/\(subject)/calibrations"
    }

    private func memoryPath(id: String, settings: ServerSettings) -> String {
        let subject = settings.subjectID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? settings.subjectID
        let memory = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        return "api/v1/subjects/\(subject)/memories/\(memory)"
    }

    private func requireNoContent(_ request: URLRequest) async throws {
        let (_, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw EpisodeAPIError.invalidResponse }
        guard response.statusCode == 204 else {
            throw EpisodeAPIError.http(response.statusCode, "记忆操作失败")
        }
    }

    func upload(
        fileURL: URL,
        recordedAt: Date,
        idempotencyKey: String,
        settings: ServerSettings
    ) async throws -> EpisodeCreated {
        guard settings.isReady else { throw EpisodeAPIError.missingCredentials }
        let data = try Data(contentsOf: fileURL)
        guard data.count <= 25 * 1024 * 1024 else { throw EpisodeAPIError.oversizedAudio }
        let boundary = "RememberMe-\(UUID().uuidString)"
        var request = try authorizedRequest(path: "api/v1/episodes", method: "POST", settings: settings)
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = MultipartCapture.body(
            audio: data,
            fileName: fileURL.lastPathComponent,
            subjectID: settings.subjectID,
            recordingConsentID: settings.recordingConsentID,
            recordedAt: recordedAt,
            idempotencyKey: idempotencyKey,
            boundary: boundary
        )
        return try await decode(EpisodeCreated.self, request: request)
    }

    func status(episodeID: String, settings: ServerSettings) async throws -> EpisodeStatus {
        let request = try authorizedRequest(
            path: "api/v1/episodes/\(episodeID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? episodeID)",
            method: "GET", settings: settings
        )
        return try await decode(EpisodeStatus.self, request: request)
    }

    func result(episodeID: String, settings: ServerSettings) async throws -> EpisodeResult {
        let encoded = episodeID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? episodeID
        let request = try authorizedRequest(path: "api/v1/episodes/\(encoded)/result", method: "GET", settings: settings)
        return try await decode(EpisodeResult.self, request: request)
    }

    private func authorizedRequest(path: String, method: String, settings: ServerSettings) throws -> URLRequest {
        guard let base = settings.validatedURL else { throw EpisodeAPIError.invalidServerURL }
        guard !settings.token.isEmpty else { throw EpisodeAPIError.missingCredentials }
        var request = URLRequest(url: base.appending(path: path))
        request.httpMethod = method
        request.timeoutInterval = 30
        request.setValue("Bearer \(settings.token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    private func decode<T: Decodable>(_ type: T.Type, request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw EpisodeAPIError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else {
            let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let message = object?["error_message"] as? String
                ?? object?["detail"] as? String
                ?? object?["error_code"] as? String
                ?? "请求失败"
            throw EpisodeAPIError.http(response.statusCode, message)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do { return try decoder.decode(type, from: data) }
        catch { throw EpisodeAPIError.invalidResponse }
    }
}

private struct CorrectionReceipt: Decodable {
    let memoryItemId: String
}

private struct CalibrationSubmission: Encodable {
    let humanAnswer: String
    let gaps: CalibrationGaps
}

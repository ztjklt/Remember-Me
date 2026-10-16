import Foundation

struct RealtimeVoiceProfile: Decodable {
    let ready: Bool
    let profile_id: String?
    let status: String
    let model_version: String?
    let voice_consent_id: String?
}
struct RealtimeVoiceReview: Decodable {
    let profile_id: String?
    let status: String
    let reviewed_at: String?
    let previewed_at: String?
}
struct RealtimeVoiceCapabilities: Decodable {
    var transport: String? = nil
    var personal_voice_available: Bool? = nil
    let available: Bool
    var default_voice_available: Bool? = nil
    let policy: String
    let notice: String
    var profile: RealtimeVoiceProfile
    var dialogue_capture_available: Bool? = nil
    var natural_voice_preparation: Bool? = nil
    var voiceprint_available: Bool? = nil
    var owner_voice_registered: Bool? = nil
}
struct VoiceCallTicket: Decodable {
    var capture_enabled: Bool? = nil
    var voice_mode: String? = nil
    let call_id: String
    let room: String
    let participant_identity: String
    var transport: String? = nil
    var app_id: String? = nil
    var bot_identity: String? = nil
    var livekit_url: String? = nil
    let token: String
    let expires_at: String
}
struct VoiceCallEvent: Decodable {
    let type: String
    let turn_id: String?
    let text: String?
    let state: String?
    let answer: TwinAnswerRecord?
    let message: String?
    var speaker_names: [String]? = nil
}

extension APIClient {
    func realtimeVoiceReview(subjectID: String, transport: String? = nil,
                             profileID: String? = nil, accepted: Bool? = nil) async throws -> RealtimeVoiceReview {
        let route = transport == "volcengine" ? "volcengine/" : ""
        var payload: Data?
        if let profileID, let accepted {
            payload = try JSONSerialization.data(withJSONObject: ["profile_id":profileID, "accepted":accepted])
        }
        return try JSONDecoder().decode(RealtimeVoiceReview.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/\(route)profile/review", method: payload == nil ? "GET" : "POST",
            body: payload, contentType: "application/json", timeout: 15))
    }
    func retryRealtimeVoice(subjectID: String, profileID: String, transport: String? = nil) async throws {
        let route = transport == "volcengine" ? "volcengine/" : ""
        let body = try JSONSerialization.data(withJSONObject: ["profile_id":profileID])
        struct Receipt: Decodable { let retired_profile_id: String; let status: String }
        let receipt = try JSONDecoder().decode(Receipt.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/\(route)profile/retry", method: "POST", body: body,
            contentType: "application/json", timeout: 15))
        guard receipt.retired_profile_id == profileID, receipt.status == "retired" else { throw APIError.invalidResponse }
    }
    func realtimeVoicePreview(subjectID: String, transport: String? = nil) async throws -> Data {
        let route = transport == "volcengine" ? "volcengine/" : ""
        return try await request("/api/v1/subjects/\(subjectID)/twin/voice/\(route)profile/preview", timeout: 60)
    }
    func realtimeCapabilities(subjectID: String) async throws -> RealtimeVoiceCapabilities {
        try JSONDecoder().decode(RealtimeVoiceCapabilities.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/capabilities?transport=volcengine&features=2", timeout: 15))
    }
    func realtimeProfile(subjectID: String, transport: String? = nil) async throws -> RealtimeVoiceProfile {
        let route = transport == "volcengine" ? "volcengine/" : ""
        return try JSONDecoder().decode(RealtimeVoiceProfile.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/\(route)profile", timeout: 45))
    }
    func enrollRealtimeVoice(subjectID: String, consentID: String, transcript: String,
                             policy: String, audio: Data, transport: String? = nil) async throws -> RealtimeVoiceProfile {
        let route = transport == "volcengine" ? "volcengine/" : ""
        let boundary = UUID().uuidString
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        field("voice_consent_id", consentID); field("transcript", transcript)
        field("own_voice_confirmed", "true"); field("accepted_policy", policy)
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"sample\"; filename=\"sample.m4a\"\r\nContent-Type: audio/mp4\r\n\r\n".utf8))
        body.append(audio); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return try JSONDecoder().decode(RealtimeVoiceProfile.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/\(route)profile", method: "POST", body: body,
            contentType: "multipart/form-data; boundary=\(boundary)", timeout: 60))
    }
    func startVoiceCall(subjectID: String, cloudConsent: String, voiceConsent: String, policy: String, voiceMode: String = "personal", recordingConsent: String? = nil, speakerConsent: String? = nil, enrollOwnerVoice: Bool = false, transport: String? = nil) async throws -> VoiceCallTicket {
        var payload: [String: Any] = ["cloud_consent_id": cloudConsent, "voice_consent_id": voiceConsent, "policy": policy, "voice_mode": voiceMode]
        if let recordingConsent { payload["recording_consent_id"] = recordingConsent }
        if let speakerConsent { payload["speaker_consent_id"] = speakerConsent }
        if enrollOwnerVoice { payload["enroll_owner_voice"] = true }
        let body = try JSONSerialization.data(withJSONObject: payload)
        let route = transport == "volcengine" ? "volcengine/" : ""
        return try JSONDecoder().decode(VoiceCallTicket.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/\(route)calls", method: "POST", body: body,
            contentType: "application/json", timeout: 20))
    }
    func endVoiceCall(subjectID: String, callID: String, transport: String? = nil) async throws {
        let route = transport == "volcengine" ? "volcengine/" : ""
        _ = try await request("/api/v1/subjects/\(subjectID)/twin/voice/\(route)calls/\(callID)", method: "DELETE", timeout: 15)
    }
}

struct DomesticVoiceStatus: Decodable {
    let call_id: String
    let turn_id: String?
    let question: String
    let answer: TwinAnswerRecord?
    let failed: Bool
    var speaker_names: [String]? = nil
    var speaker_message: String? = nil
    var retired_turn_id: String? = nil
}
extension APIClient {
    func activateDomesticVoice(subjectID: String, callID: String) async throws {
        _ = try await request("/api/v1/subjects/\(subjectID)/twin/voice/volcengine/calls/\(callID)/activate",
            method: "POST", timeout: 12)
    }
    func domesticVoiceHeartbeat(subjectID: String, callID: String) async throws -> DomesticVoiceStatus {
        try JSONDecoder().decode(DomesticVoiceStatus.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/volcengine/calls/\(callID)/status", timeout: 5))
    }
    func domesticVoiceLease(subjectID: String, callID: String) async throws {
        struct Reply: Decodable { let call_id: String }
        let reply = try JSONDecoder().decode(Reply.self, from: await request(
            "/api/v1/subjects/\(subjectID)/twin/voice/volcengine/calls/\(callID)/lease", method: "POST", timeout: 3))
        guard reply.call_id == callID else { throw APIError.invalidResponse }
    }
    func domesticVoiceAudio(subjectID: String, callID: String, turnID: String, answerID: String) async throws -> URLSession.AsyncBytes {
        try await voiceAudioBytes("/api/v1/subjects/\(subjectID)/twin/voice/volcengine/calls/\(callID)/speech/\(turnID)/\(answerID)")
    }
    func uploadDomesticVoice(subjectID: String, callID: String, segmentID: String, sample: Bool, audio: Data) async throws {
        guard audio.count <= 960044 else { throw APIError.invalidResponse }
        let boundary = UUID().uuidString
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"sample\"; filename=\"utterance.wav\"\r\nContent-Type: audio/wav\r\n\r\n".utf8)
        body.append(audio); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        _ = try await request("/api/v1/subjects/\(subjectID)/twin/voice/volcengine/calls/\(callID)/\(sample ? "samples" : "utterances")/\(segmentID)",
            method: "POST", body: body, contentType: "multipart/form-data; boundary=\(boundary)", timeout: 12)
    }
    func interruptDomesticVoice(subjectID: String, callID: String, turnID: String) async throws {
        _ = try await request("/api/v1/subjects/\(subjectID)/twin/voice/volcengine/calls/\(callID)/interrupt",
            method: "POST", body: JSONSerialization.data(withJSONObject: ["turn_id": turnID]),
            contentType: "application/json", timeout: 5)
    }
}

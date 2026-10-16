import Foundation
import Combine

// Shared workbench APIs, approved in agent-loop-v5-proposal.md.
// This is a projection of server records; it never builds a second memory store.
struct ReviewScope: Hashable {
    let server: String
    let fingerprint: String
    let actor: String
    let subject: String
    private let token: String
    init(_ pairing: Pairing) {
        server = pairing.baseURL; fingerprint = pairing.fingerprint
        actor = pairing.actorID; subject = pairing.subjectID; token = pairing.token
    }
}

struct ReviewEvidence: Decodable, Identifiable {
    let evidence_id: String
    let episode_id: String
    let excerpt: String
    let source_type: String
    let temporal_context: String?
    var id: String { evidence_id }
    var isOwnWords: Bool { ["SUBJECT", "CALIBRATION"].contains(source_type) }
}

struct ReviewCandidate: Decodable, Identifiable {
    let candidate_id: String
    let domain: String
    let kind: String
    let statement: String
    let context: String?
    let evidence_ids: [String]
    let counter_evidence_ids: [String]
    let status: String
    let stored_status: String
    let model_version: String
    let prompt_version: String
    let source_version: String
    var id: String { candidate_id }
    var canBeRelationTarget: Bool { status == "confirmed" || (status == "stale" && stored_status == "confirmed") }
}

struct ReviewJob: Decodable, Identifiable {
    let job_id: String
    let status: String
    let error: String?
    var id: String { job_id }
    var isRunning: Bool { ["queued", "running"].contains(status) }
}
struct ReviewCandidateList: Decodable {
    let items: [ReviewCandidate]
    let jobs: [ReviewJob]
    let source_version: String
}
struct ReviewJobList: Decodable { let items: [ReviewJob] }

struct ReviewRecord: Decodable, Identifiable {
    let id: String
    let kind: String
    let title: String
    let text: String
    let evidence_ids: [String]
    let facets: [String]
    let time_text: String
    let place_text: String
    let aliases: [String]
    let same_event: Bool
    let recipient_label: String
    let status: String
    let revision: Int
    let model_version: String
    let prompt_version: String
    let evidence: [ReviewEvidence]
    let source_valid: Bool
    let historical: Bool
    var editable: Bool { source_valid && !historical }
}
struct ReviewStyle: Codable { let enabled: Bool; let revision: Int }
struct ReviewOverview: Decodable {
    let subject_id: String
    let role: String
    let records: [ReviewRecord]
    let source_evidence: [ReviewEvidence]
    let style: ReviewStyle
    var understandings: [GardenUnderstanding] = []
    var next_question: GardenNextQuestion? = nil
    private enum CodingKeys: String, CodingKey { case subject_id, role, records, source_evidence, style, understandings, next_question }
    init(subject_id: String, role: String, records: [ReviewRecord], source_evidence: [ReviewEvidence], style: ReviewStyle,
         understandings: [GardenUnderstanding] = [], next_question: GardenNextQuestion? = nil) {
        self.subject_id = subject_id; self.role = role; self.records = records; self.source_evidence = source_evidence
        self.style = style; self.understandings = understandings; self.next_question = next_question
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        subject_id = try values.decode(String.self, forKey: .subject_id)
        role = try values.decode(String.self, forKey: .role)
        records = try values.decode([ReviewRecord].self, forKey: .records)
        source_evidence = try values.decode([ReviewEvidence].self, forKey: .source_evidence)
        style = try values.decode(ReviewStyle.self, forKey: .style)
        understandings = try values.decodeIfPresent([GardenUnderstanding].self, forKey: .understandings) ?? []
        next_question = try values.decodeIfPresent(GardenNextQuestion.self, forKey: .next_question)
    }
}
struct ReviewUpdate: Decodable, Identifiable {
    let update_id: String
    let candidate_id: String
    let target_candidate_id: String?
    let action: String
    let reason: String
    let time_text: String
    let status: String
    var id: String { update_id }
}
struct ReviewUpdateList: Decodable { let items: [ReviewUpdate] }

struct ReviewRecordInput: Encodable {
    var kind: String
    var title: String
    var text: String
    var evidence_ids: [String]
    var facets: [String]
    var time_text = ""
    var place_text = ""
    var aliases: [String] = []
    var same_event = false
    var recipient_label = ""
    // nil is omitted when creating; edits must carry the server revision.
    var revision: Int?

    init(kind: String, title: String, text: String, evidenceIDs: [String], facets: [String]) {
        self.kind = kind; self.title = title; self.text = text
        evidence_ids = evidenceIDs; self.facets = facets
    }
    init(_ record: ReviewRecord) {
        kind = record.kind; title = record.title; text = record.text
        evidence_ids = record.evidence_ids; facets = record.facets
        time_text = record.time_text; place_text = record.place_text; aliases = record.aliases
        same_event = record.same_event; recipient_label = record.recipient_label; revision = record.revision
    }
    func validationMessage(sources: [ReviewEvidence]) -> String? {
        if title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || title.count > 120 { return "标题须为 1–120 字。" }
        let words = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if words.isEmpty || words.count > 1500 { return "内容须为 1–1500 字。" }
        if evidence_ids.isEmpty || evidence_ids.count > 64 || Set(evidence_ids).count != evidence_ids.count { return "请选择有效的原文依据。" }
        if facets.isEmpty || Set(facets).count != facets.count || !facets.allSatisfy({ reviewFacets[$0] != nil }) { return "请至少选择一个分类。" }
        let selected = sources.filter { evidence_ids.contains($0.id) }
        if selected.count != evidence_ids.count { return "原文已不可用，请刷新后重新核对。" }
        if ["style", "letter"].contains(kind) {
            if !facets.contains("EXPRESSION") || !selected.allSatisfy(\.isOwnWords) || !selected.contains(where: { $0.excerpt.contains(words) }) {
                return "表达范例和寄语须逐字选取本人原话，并保留表达分类。"
            }
        }
        if same_event && kind != "story" { return "同一事件只能用于故事归组。" }
        for phrase in [time_text, place_text] + aliases where !phrase.isEmpty {
            if !selected.contains(where: { $0.excerpt.contains(phrase) }) { return "时间、地点和别名须来自所选原文。" }
        }
        return nil
    }
}

let reviewFacets = ["EXPERIENCE": "经历与转折", "RELATIONSHIPS": "人物与关系", "IDENTITY": "身份与角色",
                    "PRACTICES": "偏好与做事方法", "VALUES": "价值与选择理由", "FEELINGS": "当时的感受",
                    "WISHES": "愿望与牵挂", "EXPRESSION": "原话与表达"]
let reviewFacetOrder = ["EXPERIENCE", "RELATIONSHIPS", "IDENTITY", "PRACTICES", "VALUES", "FEELINGS", "WISHES", "EXPRESSION"]

extension APIClient {
    func reviewPath(subject: String, suffix: String) throws -> String {
        // IDs are opaque server IDs, never paths or query strings supplied by a view.
        guard !subject.isEmpty, subject.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-" )).contains($0) }) else { throw APIError.invalidURL }
        return "/api/v1/workbench/subjects/\(subject)/\(suffix)"
    }
    func reviewOverview(subject: String) async throws -> ReviewOverview {
        try JSONDecoder().decode(ReviewOverview.self, from: await request(reviewPath(subject: subject, suffix: "narrative"), timeout: 30))
    }
    func reviewCandidates(subject: String) async throws -> ReviewCandidateList {
        try JSONDecoder().decode(ReviewCandidateList.self, from: await request(reviewPath(subject: subject, suffix: "profile-candidates"), timeout: 30))
    }
    func reviewUpdates(subject: String) async throws -> ReviewUpdateList {
        try JSONDecoder().decode(ReviewUpdateList.self, from: await request(reviewPath(subject: subject, suffix: "profile-candidates/updates"), timeout: 30))
    }
    func reviewJobs(subject: String) async throws -> ReviewJobList {
        try JSONDecoder().decode(ReviewJobList.self, from: await request(reviewPath(subject: subject, suffix: "narrative/jobs"), timeout: 30))
    }
    func reviewWrite(subject: String, suffix: String, method: String = "POST", body: Data? = nil) async throws {
        _ = try await request(reviewPath(subject: subject, suffix: suffix), method: method, body: body,
                              contentType: body == nil ? nil : "application/json", timeout: 30)
    }
}

@MainActor
final class PersonReviewModel: ObservableObject {
    @Published private(set) var candidates: [ReviewCandidate] = []
    @Published private(set) var records: [ReviewRecord] = []
    @Published private(set) var sources: [ReviewEvidence] = []
    @Published private(set) var updates: [ReviewUpdate] = []
    @Published private(set) var jobs: [ReviewJob] = []
    @Published private(set) var style = ReviewStyle(enabled: false, revision: 0)
    @Published private(set) var isLoading = false
    @Published private(set) var isMutating = false
    @Published private(set) var isReady = false
    @Published var errorMessage: String?
    @Published private(set) var notice: String?
    var onMutation: ((ReviewScope) -> Void)?
    private var pairing: Pairing?
    private var generation = UUID()
    private var loadID = UUID()
    private let clientFactory: (Pairing) throws -> APIClient
    var scope: ReviewScope? { pairing.map(ReviewScope.init) }
    var hasRunningJobs: Bool { jobs.contains(where: \.isRunning) }
    var canUseStyle: Bool { records.contains { $0.kind == "style" && $0.status == "confirmed" && $0.editable } }

    init(clientFactory: @escaping (Pairing) throws -> APIClient = {
        try APIClient(baseURL: $0.baseURL, fingerprint: $0.fingerprint, token: $0.token)
    }) { self.clientFactory = clientFactory }

    func configure(_ pairing: Pairing?) {
        self.pairing = pairing; generation = UUID(); loadID = UUID()
        clear(); isLoading = false; isMutating = false; errorMessage = nil; notice = nil
    }
    private func clear() {
        candidates = []; records = []; sources = []; updates = []; jobs = []
        style = ReviewStyle(enabled: false, revision: 0); isReady = false
    }
    func reload() async {
        guard let pairing, !isMutating else { return }
        let wasReady = isReady
        let epoch = generation, requestID = UUID(); loadID = requestID
        isLoading = true; isReady = false
        defer { if generation == epoch && loadID == requestID { isLoading = false } }
        do {
            let api = try clientFactory(pairing)
            async let overview = api.reviewOverview(subject: pairing.subjectID)
            async let list = api.reviewCandidates(subject: pairing.subjectID)
            async let changes = api.reviewUpdates(subject: pairing.subjectID)
            async let narrativeJobs = api.reviewJobs(subject: pairing.subjectID)
            let (view, result, relations, work) = try await (overview, list, changes, narrativeJobs)
            guard generation == epoch, loadID == requestID else { return }
            guard view.subject_id == pairing.subjectID, view.role == "owner" else { throw APIError.server(403, "此页面仅供本人核对自己的资料。") }
            sources = view.source_evidence
            // Candidate API includes historical records; never publish private snapshots of revoked sources.
            let visibleIDs = Set(sources.map(\.id))
            candidates = result.items.filter { Set($0.evidence_ids + $0.counter_evidence_ids).isSubset(of: visibleIDs) }
            records = view.records; updates = relations.items
            var seenJobs = Set<String>()
            jobs = (result.jobs + work.items).filter { seenJobs.insert($0.id).inserted }
            style = view.style; isReady = true; errorMessage = nil
        } catch {
            guard generation == epoch, loadID == requestID else { return }
            if Task.isCancelled { isReady = wasReady; return }
            clear()
            if case APIError.server(404, _) = error {
                errorMessage = "当前服务尚未提供人物审核接口。请更新 Backend；已有录音、记忆和 Twin 入口仍可使用。"
            } else { errorMessage = error.localizedDescription }
        }
    }
    private func mutate(suffix: String, method: String = "POST", body: Data? = nil,
                        message: String, invalidatesTwin: Bool = true) async -> Bool {
        guard isReady, !isMutating, let pairing else { return false }
        let epoch = generation, currentScope = ReviewScope(pairing)
        // Discard GETs started before the write, even if they return after it.
        loadID = UUID(); isLoading = false; isMutating = true; errorMessage = nil; notice = nil
        // The server may commit even if the response is lost. Drop cached answers
        // before the write, and discard any answer already in flight.
        if invalidatesTwin { onMutation?(currentScope) }
        var succeeded = false
        do {
            try await clientFactory(pairing).reviewWrite(subject: pairing.subjectID, suffix: suffix, method: method, body: body)
            guard generation == epoch else { return false }
            succeeded = true; notice = message
        } catch {
            guard generation == epoch else { return false }
            errorMessage = error.localizedDescription
            if case APIError.server(409, _) = error, !invalidatesTwin { onMutation?(currentScope) }
        }
        guard generation == epoch else { return false }
        isMutating = false
        let failure = errorMessage
        await reload()
        if generation == epoch, let failure { errorMessage = failure }
        return succeeded
    }
    private func safeID(_ id: String) -> Bool {
        !id.isEmpty && id.unicodeScalars.allSatisfy { CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-")).contains($0) }
    }
    func decideCandidate(_ candidate: ReviewCandidate, confirm: Bool) async -> Bool {
        guard safeID(candidate.id), candidates.contains(where: { $0.id == candidate.id && $0.source_version == candidate.source_version && $0.status == candidate.status }),
              confirm ? candidate.status == "pending" : ["pending", "confirmed"].contains(candidate.status) else { return false }
        return await mutate(suffix: "profile-candidates/\(candidate.id)/\(confirm ? "confirm" : "reject")",
                            message: confirm ? "已确认这项情境化理解。" : "不采用这项理解；原文和录音仍保留。")
    }
    func saveRecord(_ input: ReviewRecordInput, recordID: String? = nil) async -> Bool {
        if let issue = input.validationMessage(sources: sources) { errorMessage = issue; return false }
        if let recordID {
            guard safeID(recordID), records.contains(where: { $0.id == recordID && $0.revision == input.revision && $0.editable }) else {
                errorMessage = "记录已经变化，请刷新后重新编辑。"; return false
            }
        }
        do {
            return await mutate(suffix: "narrative/records" + (recordID.map { "/\($0)" } ?? ""), method: recordID == nil ? "POST" : "PUT",
                                body: try JSONEncoder().encode(input), message: "已保存为待核对内容，请查看依据后确认。", invalidatesTwin: recordID != nil)
        } catch { errorMessage = error.localizedDescription; return false }
    }
    func decideRecord(_ record: ReviewRecord, confirm: Bool) async -> Bool {
        guard safeID(record.id), record.editable,
              records.contains(where: { $0.id == record.id && $0.revision == record.revision }),
              confirm ? record.status == "pending" : ["pending", "confirmed"].contains(record.status) else { return false }
        let body = try? JSONSerialization.data(withJSONObject: ["revision": record.revision])
        return await mutate(suffix: "narrative/records/\(record.id)/\(confirm ? "confirm" : "reject")", body: body,
                            message: confirm ? "已确认整理内容。" : "已停用整理内容；原文和录音仍保留。")
    }
    func setStyle(_ enabled: Bool) async -> Bool {
        guard !enabled || canUseStyle else { errorMessage = "请先确认至少一条本人原话作为表达范例。"; return false }
        let body = try? JSONEncoder().encode(ReviewStyle(enabled: enabled, revision: style.revision))
        return await mutate(suffix: "narrative/style", method: "PUT", body: body, message: enabled ? "Twin 已启用经你确认的表达范例。" : "Twin 已停用表达范例。")
    }
    func requestSuggestions(consentID: String, narrative: Bool) async -> Bool {
        guard !consentID.isEmpty else { return false }
        let body = try? JSONSerialization.data(withJSONObject: ["cloud_consent_id": consentID])
        return await mutate(suffix: narrative ? "narrative/suggest" : "profile-candidates/refresh", body: body,
                            message: "整理任务已提交。完成后仍需你核对，不会自动确认。", invalidatesTwin: false)
    }
    func proposeRelation(candidate: ReviewCandidate, targetID: String, action: String, reason: String, time: String) async -> Bool {
        guard candidate.status == "pending", candidates.contains(where: { $0.id == candidate.id && $0.status == "pending" && $0.source_version == candidate.source_version }),
              ["SUPPORT", "CHANGE", "CONFLICT"].contains(action),
              let target = candidates.first(where: { $0.id == targetID && $0.canBeRelationTarget }),
              target.domain == candidate.domain, target.kind == candidate.kind,
              !reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, reason.count <= 1000,
              time.count <= 200, action != "CHANGE" || !time.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "请选择同类已确认理解并填写原因；变化还须提供时间说明。"; return false
        }
        let body = try? JSONSerialization.data(withJSONObject: ["candidate_id": candidate.id, "target_candidate_id": targetID,
                                                               "action": action, "reason": reason, "time_text": time])
        return await mutate(suffix: "profile-candidates/updates", body: body, message: "已提交关联建议，确认后才会生效。", invalidatesTwin: false)
    }
    func decideUpdate(_ update: ReviewUpdate, confirm: Bool) async -> Bool {
        guard safeID(update.id), update.status == "pending", updates.contains(where: { $0.id == update.id && $0.status == "pending" }) else { return false }
        return await mutate(suffix: "profile-candidates/updates/\(update.id)/\(confirm ? "confirm" : "reject")", message: confirm ? "人物理解更新已确认。" : "已拒绝关联建议。")
    }
}

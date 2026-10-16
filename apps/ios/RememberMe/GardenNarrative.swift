import Foundation

struct GardenUnderstanding: Decodable, Identifiable {
    let candidate_id: String
    let statement: String
    let context: String?
    let status: String
    let evidence_ids: [String]
    let counter_evidence_ids: [String]
    let evidence: [ReviewEvidence]
    let counter_evidence: [ReviewEvidence]
    let model_version: String
    var id: String { candidate_id }
    func isCurrent(sources: [ReviewEvidence], episodes: [EpisodeRecord]) -> Bool {
        let current = Dictionary(sources.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let ready = Set(episodes.filter { $0.status == "ready" }.map(\.id))
        let refs = evidence + counter_evidence
        guard status == "confirmed", !evidence_ids.isEmpty,
              Set(refs.map(\.id)) == Set(evidence_ids + counter_evidence_ids) else { return false }
        return refs.allSatisfy { source in
            current[source.id].map { $0.episode_id == source.episode_id && $0.excerpt == source.excerpt &&
                $0.source_type == source.source_type && ready.contains(source.episode_id) } ?? false
        }
    }
}

struct GardenNextQuestion: Decodable {
    let id: String
    let text: String
    let reason: String
    let evidence_ids: [String]
}

enum GardenPersonView: String, CaseIterable, Identifiable {
    case life = "人生足迹", people = "重要的人", choices = "在意选择", expression = "声音表达"
    var id: String { rawValue }
    var facets: Set<String> {
        switch self {
        case .life: ["EXPERIENCE", "IDENTITY", "FEELINGS"]
        case .people: ["RELATIONSHIPS"]
        case .choices: ["PRACTICES", "VALUES", "WISHES"]
        case .expression: ["EXPRESSION"]
        }
    }
    var kinds: [String] {
        switch self {
        case .life: ["story", "observation", "person"]
        case .people: ["person", "story", "observation"]
        case .choices: ["observation", "story", "person"]
        case .expression: ["letter", "style", "observation", "story", "person"]
        }
    }
}

enum GardenFacet: String, CaseIterable, Identifiable {
    case experience = "EXPERIENCE", relationships = "RELATIONSHIPS", identity = "IDENTITY"
    case practices = "PRACTICES", values = "VALUES", feelings = "FEELINGS", wishes = "WISHES", expression = "EXPRESSION"
    var id: String { rawValue }
    var title: String {
        switch self {
        case .experience: "人生经历"
        case .relationships: "人物关系"
        case .identity: "身份角色"
        case .practices: "偏好习惯"
        case .values: "在意选择"
        case .feelings: "感受状态"
        case .wishes: "愿望牵挂"
        case .expression: "原话寄语"
        }
    }
    var symbol: String {
        switch self {
        case .experience: "leaf"
        case .relationships: "person.2"
        case .identity: "person.crop.circle"
        case .practices: "sun.max"
        case .values: "arrow.triangle.branch"
        case .feelings: "heart"
        case .wishes: "sparkles"
        case .expression: "quote.bubble"
        }
    }
}

/// Narrative text is visible only while every referenced source still agrees with
/// the current owner projection. A matching evidence ID alone is insufficient.
enum GardenNarrativeProjection {
    static func hasCurrentEvidence(_ record: ReviewRecord, overview: ReviewOverview, episodes: [EpisodeRecord]) -> Bool {
        let ready = Set(episodes.filter { $0.status == "ready" }.map(\.id))
        let sources = Dictionary(overview.source_evidence.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        guard record.source_valid, !record.historical, !record.evidence_ids.isEmpty,
              Set(record.evidence_ids).count == record.evidence_ids.count,
              Set(record.evidence.map(\.id)) == Set(record.evidence_ids) else { return false }
        return record.evidence.allSatisfy { source in
            guard let current = sources[source.id] else { return false }
            return ready.contains(source.episode_id) && current.episode_id == source.episode_id &&
                current.excerpt == source.excerpt && current.source_type == source.source_type && !source.excerpt.isEmpty
        }
    }
    static func records(_ overview: ReviewOverview?, episodes: [EpisodeRecord], view: GardenPersonView? = nil,
                        facet: GardenFacet? = nil, query: String = "", pending: Bool = false) -> [ReviewRecord] {
        guard let overview, overview.role == "owner" else { return [] }
        let search = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return overview.records.filter { row in
            let status = pending ? ["pending", "stale"].contains(row.status) : row.status == "confirmed"
            // Stale rows belong to the management queue, never the garden document.
            return status && hasCurrentEvidence(row, overview: overview, episodes: episodes) &&
                (view == nil || !view!.facets.isDisjoint(with: row.facets)) &&
                (facet == nil || row.facets.contains(facet!.rawValue)) &&
                (search.isEmpty || ([row.title, row.text, row.place_text] + row.aliases + row.evidence.map(\.excerpt))
                    .joined(separator: " ").localizedCaseInsensitiveContains(search))
        }.sorted { left, right in
            let kinds = view?.kinds ?? ["story", "person", "observation", "letter", "style"]
            let l = kinds.firstIndex(of: left.kind) ?? kinds.count, r = kinds.firstIndex(of: right.kind) ?? kinds.count
            return l == r ? left.id < right.id : l < r
        }
    }
    static func relatedStories(to row: ReviewRecord, records: [ReviewRecord]) -> [ReviewRecord] {
        let ids = Set(row.evidence_ids)
        return records.filter { $0.kind == "story" && $0.id != row.id && !ids.isDisjoint(with: $0.evidence_ids) }
    }
    static func kindTitle(_ kind: String) -> String {
        ["story": "故事", "person": "人物", "observation": "情境观察", "letter": "给你的话", "style": "表达范例"][kind] ?? "整理内容"
    }
}

enum GardenHomeProjection {
    static func entries(memories: [MemoryRecord], episodes: [EpisodeRecord], overview: ReviewOverview?) -> [GardenEntry] {
        let stories = MemoryGardenProjection.entries(memories: memories, episodes: episodes, overview: overview).filter { $0.id.hasPrefix("record:") }
        let covered = Set(stories.flatMap { $0.memories.map(\.id) })
        let rejected = Set((overview?.records ?? []).filter { $0.kind == "story" && $0.status == "rejected" }.flatMap(\.evidence_ids))
        let ready = episodes.filter { $0.status == "ready" }
        let extras = ready.compactMap { episode -> GardenEntry? in
            let remaining = memories.filter { $0.episode_id == episode.id && !covered.contains($0.id) &&
                GardenMemorySourceProjection.isCurrent($0, sources: overview?.source_evidence, episodes: episodes) &&
                Set($0.evidence.map(\.id)).isDisjoint(with: rejected) }
            guard !remaining.isEmpty else { return nil }
            return GardenEntry(id: "episode:" + episode.id, title: MemoryGardenProjection.recordingDate(episode.recorded_at) + "的讲述",
                text: "尚未归组的记忆，来自同一段讲述。", label: "系统整理 · 尚未归组", date: MemoryGardenProjection.recordingDate(episode.recorded_at),
                sortDate: episode.recorded_at, section: .stories, memories: remaining.sorted { $0.id < $1.id }, evidence: [])
        }
        return (stories + extras).sorted { $0.sortDate == $1.sortDate ? $0.id < $1.id : $0.sortDate > $1.sortDate }
    }
}

enum GardenMemorySourceProjection {
    static func isCurrent(_ memory: MemoryRecord, sources: [ReviewEvidence]?, episodes: [EpisodeRecord]) -> Bool {
        let ready = Set(episodes.filter { $0.status == "ready" }.map(\.id))
        guard ready.contains(memory.episode_id), !memory.evidence.isEmpty,
              memory.evidence.allSatisfy({ !$0.id.isEmpty && $0.excerpt?.isEmpty == false }) else { return false }
        // A legacy service has no independent narrative source projection. Its
        // current memory response remains the explicitly supported fallback.
        guard let sources else { return true }
        let byID = Dictionary(sources.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return memory.evidence.allSatisfy { evidence in
            guard let source = byID[evidence.id] else { return false }
            return source.excerpt == evidence.excerpt && source.source_type == evidence.source_type &&
                source.episode_id == memory.episode_id && ready.contains(source.episode_id)
        }
    }
}

struct GardenHistoryReply: Decodable {
    struct Item: Decodable, Identifiable {
        struct Snapshot: Decodable { let title: String; let text: String; let evidence_ids: [String] }
        let revision: Int
        let action: String
        let created_at: String
        let record: Snapshot
        var id: Int { revision }
    }
    let items: [Item]
    func currentItems(evidenceIDs: Set<String>) -> [Item] {
        items.filter { !$0.record.evidence_ids.isEmpty && Set($0.record.evidence_ids).isSubset(of: evidenceIDs) }
    }
}

extension APIClient {
    func gardenRecordHistory(subject: String, record: String) async throws -> GardenHistoryReply {
        guard !record.isEmpty, record.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-" )).contains($0) }) else { throw APIError.invalidURL }
        return try JSONDecoder().decode(GardenHistoryReply.self, from: await request(
            reviewPath(subject: subject, suffix: "narrative/records/\(record)/history"), timeout: 20))
    }
}

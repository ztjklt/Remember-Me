import Foundation
import SwiftUI
import CryptoKit

enum GardenSection: String, CaseIterable, Identifiable {
    case stories = "故事与记忆", people = "人物与关系", graph = "记忆图谱"
    var id: String { rawValue }
}

struct GardenEntry: Identifiable {
    let id: String
    let title: String
    let text: String
    let label: String
    let date: String
    let sortDate: String
    let section: GardenSection
    let memories: [MemoryRecord]
    let evidence: [ReviewEvidence]
    var displayIDs: Set<String> {
        Set([id] + memories.map { "episode:" + $0.episode_id } +
            memories.filter { $0.memory_type == "EVENT" }.map { "event:" + $0.id })
    }
    func matches(_ query: String) -> Bool {
        let words = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !words.isEmpty else { return true }
        return ([title, text] + memories.map(\.content) + evidence.map(\.excerpt)).joined(separator: "\n")
            .localizedCaseInsensitiveContains(words)
    }
}

private struct GardenStoryDraft {
    var title: String
    var text: String
}

private struct GardenEditing: Identifiable {
    let entry: GardenEntry
    let record: ReviewRecord?
    let pairing: Pairing
    var id: String { entry.id }
}

enum GardenBrowseMode: String, CaseIterable, Identifiable {
    case timeline = "时间线", graph = "图谱"
    var id: String { rawValue }
}

enum GardenArtwork: String, CaseIterable, Identifiable {
    case sprig = "GardenPaperSprig", wreath = "GardenWreath", basket = "GardenBasket"
    case bouquet = "GardenGrandBouquet", vase = "GardenGlassVase", pressed = "GardenPressedFlowers"
    case ribbon = "GardenRibbonPosy", petals = "GardenPetals", linework = "GardenLinework", arch = "GardenFloralArch"
    var id: String { rawValue }
    var title: String {
        switch self {
        case .sprig: "花簇"
        case .wreath: "花环"
        case .basket: "花篮"
        case .bouquet: "一捧花"
        case .vase: "玻璃花瓶"
        case .pressed: "压花"
        case .ribbon: "丝带花束"
        case .petals: "飘落花瓣"
        case .linework: "线描花枝"
        case .arch: "花拱"
        }
    }
    static func forEntry(_ entry: GardenEntry) -> Self {
        if entry.section == .people { return .ribbon }
        let choices = allCases
        let byte = Array(SHA256.hash(data: Data(entry.id.utf8))).first ?? 0
        return choices[Int(byte) % choices.count]
    }
}

struct GardenPetal {
    let x: Double
    let y: Double
    let angle: Double
    let opacity: Double
}

/// Preserve each botanical asset's original blue petals, yellow centers and natural foliage.
struct GardenArtworkImage: View {
    let artwork: GardenArtwork
    var body: some View {
        Image(artwork.rawValue).resizable().scaledToFit()
    }
}

enum GardenPetalMotion {
    static func particles(time: Double) -> [GardenPetal] {
        guard time.isFinite, time >= 0 else { return [] }
        return (0..<7).map { index in
            let seed = Double(index)
            let progress = (time * (0.024 + seed * 0.001) + seed / 7).truncatingRemainder(dividingBy: 1)
            return GardenPetal(x: 0.12 + seed * 0.12 + sin(time * 0.24 + seed) * 0.04,
                               y: progress, angle: sin(time * 0.3 + seed) * 50,
                               opacity: sin(progress * .pi) * 0.38)
        }
    }
}

struct GardenTimelineGroup: Identifiable {
    let id: String
    let date: Date?
    let title: String
    let entries: [GardenEntry]
}

enum GardenTimelineProjection {
    static func groups(_ entries: [GardenEntry], timeZone: TimeZone = .current) -> [GardenTimelineGroup] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.calendar = calendar
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyy.MM.dd"
        let parser = ISO8601DateFormatter()
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        // Group by capture time only. Free-form event descriptions are never parsed into invented dates.
        let dated = entries.map { entry in
            let timestamp = fractional.date(from: entry.sortDate) ?? parser.date(from: entry.sortDate)
            return (entry, timestamp.map { calendar.startOfDay(for: $0) }, timestamp)
        }
        return Dictionary(grouping: dated, by: { $0.1 }).map { day, rows in
            GardenTimelineGroup(id: day.map { formatter.string(from: $0) } ?? "undated", date: day,
                title: day.map { "录入 · " + formatter.string(from: $0) } ?? "录入时间未知",
                entries: rows.sorted { left, right in
                    if left.2 == right.2 { return left.0.id < right.0.id }
                    return (left.2 ?? .distantPast) > (right.2 ?? .distantPast)
                }.map(\.0))
        }.sorted {
            switch ($0.date, $1.date) {
            case let (left?, right?): left > right
            case (_?, nil): true
            default: false
            }
        }
    }

    static func linkedFacts(for entry: GardenEntry, items: [GardenGraphItem]) -> [GardenGraphItem] {
        let evidence = Set(entry.evidence.map(\.id) + entry.memories.flatMap { $0.evidence.map(\.id) })
        return items.filter { !evidence.isDisjoint(with: $0.fact.evidence_ids) }
    }
}

enum MemoryGardenProjection {
    static func recordingDate(_ timestamp: String, timeZone: TimeZone = .current) -> String {
        let fractional = ISO8601DateFormatter(); fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = fractional.date(from: timestamp) ?? ISO8601DateFormatter().date(from: timestamp) else { return "录入日期未知" }
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "zh_CN")
        formatter.timeZone = timeZone; formatter.dateFormat = "yyyy-MM-dd"
        return "录入于 " + formatter.string(from: date)
    }
    static func entries(memories: [MemoryRecord], episodes: [EpisodeRecord], overview: ReviewOverview?) -> [GardenEntry] {
        let ready = Set(episodes.filter { $0.status == "ready" }.map(\.id))
        let active = memories.filter { ready.contains($0.episode_id) && !$0.evidence.isEmpty }
        let validSources = Set((overview?.source_evidence ?? []).filter { ready.contains($0.episode_id) }.map(\.id))
        var entries: [GardenEntry] = [], storyEvidence = Set<String>()
        // A rejected story must not return as a new flower made from its source EVENT.
        let rejectedEvidence = Set((overview?.records ?? []).filter {
            $0.kind == "story" && $0.status == "rejected"
        }.flatMap(\.evidence_ids))
        for record in overview?.records ?? [] {
            let displayable = record.status == "confirmed" || (record.status == "pending" && overview?.role == "owner")
            guard record.kind == "story", displayable, record.source_valid,
                  !record.historical, !record.evidence_ids.isEmpty,
                  Set(record.evidence_ids).isSubset(of: validSources),
                  Set(record.evidence_ids).isSubset(of: Set(record.evidence.map(\.id))),
                  record.evidence.allSatisfy({ ready.contains($0.episode_id) }),
                  overview.map({ GardenNarrativeProjection.hasCurrentEvidence(record, overview: $0, episodes: episodes) }) == true else { continue }
            let sources = record.evidence.filter { record.evidence_ids.contains($0.id) }
            let linked = active.filter { memory in !memory.evidence.isEmpty && Set(memory.evidence.map(\.id)).isSubset(of: Set(record.evidence_ids)) }
            let dates = episodes.filter { sources.map(\.episode_id).contains($0.id) }.map(\.recorded_at)
            entries.append(GardenEntry(id: "record:" + record.id, title: record.title, text: record.text,
                label: record.status == "confirmed" ? "本人核对的故事" : "整理的故事",
                date: record.time_text.isEmpty ? recordingDate(dates.min() ?? "") : record.time_text,
                sortDate: dates.max() ?? "", section: .stories, memories: linked, evidence: sources))
            storyEvidence.formUnion(record.evidence_ids)
        }
        let covered = storyEvidence.union(rejectedEvidence)
        // Extraction already identifies events. Preferences, names and other fragments
        // remain in the memory library; sharing a recording does not make them one event.
        for memory in active where memory.memory_type == "EVENT" &&
            !memory.evidence.contains(where: { covered.contains($0.id) }) {
            let ids = Set(memory.evidence.map(\.id))
            let linked = active.filter { $0.evidence.contains { ids.contains($0.id) } }
                .sorted { $0.id < $1.id }
            entries.append(GardenEntry(id: "event:" + memory.id, title: memory.content, text: memory.content,
                label: "AI 整理的事件", date: recordingDate(memory.recorded_at),
                sortDate: memory.recorded_at, section: .stories, memories: linked, evidence: []))
        }
        return entries.sorted { $0.sortDate == $1.sortDate ? $0.id < $1.id : $0.sortDate > $1.sortDate }
    }
}

struct GardenGraphItem: Identifiable {
    let fact: GraphFactRecord
    let memories: [MemoryRecord]
    var id: String { fact.id }
}

enum GardenGraphProjection {
    static func items(facts: [GraphFactRecord], memories: [MemoryRecord], subjectID: String) -> [GardenGraphItem] {
        let evidenceIDs = Set(memories.flatMap { $0.evidence.map(\.id) })
        return facts.compactMap { fact in
            guard fact.subject_id == subjectID, ["EVENT", "PERSON", "RELATIONSHIP"].contains(fact.kind),
                  !fact.evidence_ids.isEmpty, Set(fact.evidence_ids).isSubset(of: evidenceIDs) else { return nil }
            let sources = memories.filter { !Set($0.evidence.map(\.id)).isDisjoint(with: fact.evidence_ids) }
            return GardenGraphItem(fact: fact, memories: sources)
        }
    }
}

/// Only display IDs are saved. This is neither a permission store nor a second memory library.
struct GardenVisibilityStore {
    let root: URL
    private func file(_ owner: RecordingOwner) throws -> URL {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        let digest = SHA256.hash(data: try encoder.encode(owner)).map { String(format: "%02x", $0) }.joined()
        return root.appendingPathComponent(digest + ".json")
    }
    func load(_ owner: RecordingOwner) throws -> Set<String> {
        let path = try file(owner)
        guard FileManager.default.fileExists(atPath: path.path) else { return [] }
        return Set(try JSONDecoder().decode([String].self, from: Data(contentsOf: path)))
    }
    func save(_ hidden: Set<String>, owner: RecordingOwner) throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        var directory = root, values = URLResourceValues(); values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        try JSONEncoder().encode(hidden.sorted()).write(to: file(owner), options: [.atomic, .completeFileProtection])
    }
}

@MainActor
final class GardenVisibility: ObservableObject {
    @Published private(set) var hidden = Set<String>()
    @Published private(set) var error: String?
    private var previewDrafts: [String: GardenStoryDraft] = [:]
    func previewEntry(_ entry: GardenEntry) -> GardenEntry {
        guard let draft = previewDrafts[entry.id] else { return entry }
        return GardenEntry(id: entry.id, title: draft.title, text: draft.text, label: "整理的故事",
            date: entry.date, sortDate: entry.sortDate, section: entry.section, memories: entry.memories, evidence: entry.evidence)
    }
    func editPreview(_ entry: GardenEntry, title: String, text: String) {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("--uitest-memory-garden") else { return }
        objectWillChange.send(); previewDrafts[entry.id] = GardenStoryDraft(title: title, text: text)
        #endif
    }
    private var owner: RecordingOwner?
    private let store: GardenVisibilityStore
    init(root: URL? = nil) {
        let preview = ProcessInfo.processInfo.arguments.contains("--uitest-memory-garden")
        let defaultRoot = preview ? FileManager.default.temporaryDirectory.appendingPathComponent("garden-ui-" + UUID().uuidString) :
            FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("GardenDisplay")
        store = GardenVisibilityStore(root: root ?? defaultRoot)
    }
    func configure(_ pairing: Pairing?) {
        let next = pairing.map(RecordingOwner.init)
        guard next != owner else { return }
        owner = next; hidden = []; error = nil
        guard let next else { return }
        do { hidden = try store.load(next) }
        catch { self.error = "本机花园的展示选择未能读取。原始记忆仍然保留。" }
    }
    func setHidden(_ id: String, hidden target: Bool, pairing: Pairing) {
        guard owner == RecordingOwner(pairing) else { return }
        var next = hidden
        if target { next.insert(id) } else { next.remove(id) }
        do { try store.save(next, owner: RecordingOwner(pairing)); hidden = next; error = nil }
        catch { self.error = "展示选择未能保存，请重试。记忆没有被删除。" }
    }
}

@MainActor
final class MemoryGardenWorkspace: ObservableObject {
    @Published private(set) var overview: ReviewOverview?
    @Published private(set) var isLoading = false
    @Published private(set) var denied = false
    @Published private(set) var notice: String?
    private var legacyService = false
    private(set) var scope: ReviewScope?
    private(set) var contentRevision: UUID?
    private(set) var memoryIDs: [String] = []
    private var modelVersion = 0
    private var requestID = UUID()
    private let loader: (Pairing) async throws -> ReviewOverview
    init(loader: @escaping (Pairing) async throws -> ReviewOverview = { pairing in
        try await APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token)
            .reviewOverview(subject: pairing.subjectID)
    }) { self.loader = loader }
    func reload(_ pairing: Pairing?, revision: UUID? = nil, memoryIDs: [String] = [], modelVersion: Int = 0) async {
        let current = UUID(); requestID = current; scope = pairing.map(ReviewScope.init)
        contentRevision = revision; self.memoryIDs = memoryIDs.sorted()
        self.modelVersion = modelVersion
        overview = nil; denied = false; notice = nil; legacyService = false; isLoading = pairing != nil
        guard let pairing else { return }
        defer { if requestID == current { isLoading = false } }
        do {
            let reply = try await loader(pairing)
            guard requestID == current, scope == ReviewScope(pairing), !Task.isCancelled else { return }
            guard reply.subject_id == pairing.subjectID, reply.role == "owner" else {
                denied = true; notice = "此花园目前只支持本人的记忆空间。"; return
            }
            overview = reply
        } catch {
            guard requestID == current, scope == ReviewScope(pairing), !Task.isCancelled else { return }
            if case APIError.server(let code, _) = error, [401, 403].contains(code) {
                denied = true; notice = "当前登录或权限不可用，请重新连接本人空间。"
            } else if case APIError.server(404, _) = error {
                legacyService = true; notice = "当前服务可展示已整理的事件，暂不支持故事整理。"
            } else { notice = "故事暂未读取，请稍后刷新。原始记忆仍保留。" }
        }
    }
    func currentOverview(for pairing: Pairing, revision: UUID, memoryIDs: [String], modelVersion: Int) -> ReviewOverview? {
        guard !denied, scope == ReviewScope(pairing), contentRevision == revision,
              self.memoryIDs == memoryIDs.sorted(), self.modelVersion == modelVersion else { return nil }
        return overview
    }
    func canDisplayEntries(for pairing: Pairing, revision: UUID, memoryIDs: [String], modelVersion: Int) -> Bool {
        guard !denied, !isLoading, scope == ReviewScope(pairing), contentRevision == revision,
              self.memoryIDs == memoryIDs.sorted(), self.modelVersion == modelVersion else { return false }
        // Without the owner overview, a rejected story could reappear via its EVENT.
        return overview != nil || legacyService
    }
}

private struct GardenRefreshKey: Hashable {
    let scope: ReviewScope?
    let revision: UUID
    let memoryIDs: [String]
    let modelVersion: Int
    let audioBusy: Bool
}

struct MemoryGardenHome: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    @StateObject private var workspace = MemoryGardenWorkspace()
    @StateObject private var visibility = GardenVisibility()
    @State private var selectedFactID: String?
    @State private var removal: GardenEntry?
    @State private var deletion: GardenEditing?
    @State private var showRemoved = false
    @State private var mode = GardenSurfaceMode.meadow
    @State private var query = ""
    @State private var facet: GardenFacet?
    @State private var searchOpen = false
    @State private var showScenes = false
    @State private var showTwin = false
    @AppStorage("memory-garden-scene") private var sceneChoice = GardenScene.meadow.rawValue
    private var scene: GardenScene { GardenScene(rawValue: sceneChoice) ?? .meadow }
    private var fixture: GardenPreview? { GardenPreview.current }
    private var pairing: Pairing? { fixture?.pairing ?? model.pairing }
    private var key: GardenRefreshKey {
        GardenRefreshKey(scope: pairing.map(ReviewScope.init), revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion,
            audioBusy: model.isUsingRealtimeAudio)
    }
    private var entries: [GardenEntry] {
        if let fixture { return fixture.entries.map(visibility.previewEntry) }
        guard let pairing, workspace.canDisplayEntries(for: pairing, revision: model.memoryContentRevision,
            memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion) else { return [] }
        return GardenHomeProjection.entries(memories: model.memories, episodes: model.episodes,
            overview: workspace.currentOverview(for: pairing, revision: model.memoryContentRevision,
                memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion))
    }
    private var visible: [GardenEntry] {
        entries.filter { entry in
            !isHidden(entry) && entry.matches(query) && (facet == nil || currentOverview?.records.first { entry.id == "record:" + $0.id }?.facets.contains(facet!.rawValue) == true)
        }
    }
    private var currentOverview: ReviewOverview? {
        if let fixture { return fixture.overview }
        guard let pairing else { return nil }
        return workspace.currentOverview(for: pairing, revision: model.memoryContentRevision,
            memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
    }
    private var playableEpisodeIDs: Set<String> { Set(model.episodes.filter { $0.status == "ready" && $0.source != "IOS_TEXT" }.map(\.id)) }
    private func isHidden(_ entry: GardenEntry) -> Bool {
        !entry.displayIDs.isDisjoint(with: visibility.hidden)
    }
    private var removed: [GardenEntry] { entries.filter { isHidden($0) } }
    private var graph: [GardenGraphItem] {
        let shown = visible
        var seen = Set<String>()
        let sources = shown.flatMap(\.memories).filter { seen.insert($0.id).inserted }
        return GardenGraphProjection.items(facts: fixture?.graphFacts ?? model.graphFacts, memories: sources,
                                           subjectID: pairing?.subjectID ?? "")
    }
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: RMSpacing.lg) {
                browseControls
                if workspace.isLoading { ProgressView("正在读取故事…") }
                if let notice = workspace.notice { Text(notice).font(.subheadline).foregroundStyle(Ink.muted) }
                if let error = visibility.error { Text(error).font(.subheadline).foregroundStyle(.red) }
                if let error = model.errorMessage { Text(error).font(.subheadline).foregroundStyle(.red) }
                if mode == .person || mode == .facets {
                    GardenNarrativeBrowser(overview: currentOverview, episodes: fixture?.episodes ?? model.episodes,
                        facetsMode: mode == .facets, query: query, workspace: workspace, fixture: fixture)
                } else if visible.isEmpty {
                    if query.isEmpty && facet == nil { emptyGarden }
                    else {
                        ContentUnavailableView("没有找到匹配的故事", systemImage: "magnifyingglass", description: Text("试试别的词，或清除记忆侧面筛选。"))
                        Button("清除筛选") { query = ""; facet = nil }
                    }
                } else if mode == .meadow {
                    GardenMeadow(entries: visible) { entry in
                        GardenEntryDetail(id: entry.id, workspace: workspace, visibility: visibility, fixture: fixture)
                    }
                } else if mode == .list {
                    ForEach(visible) { entry in entryLink(entry).padding(14).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20)) }
                } else { timeline }
                if searchOpen && !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    GardenRelatedResults(query: query, fixture: fixture)
                }
            }.padding(RMSpacing.page).frame(maxWidth: RMMetrics.maximumReadingWidth)
                .frame(maxWidth: .infinity)
        }
        .background { if mode == .meadow { GardenSceneBackground(scene: scene) } else { RMColors.background.ignoresSafeArea() } }
        .environment(\.rmAnimationsDisabled, animationsDisabled || showRemoved || selectedFactID != nil)
        .navigationTitle("记忆花园").navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) { GardenMiniPlayer(allowedEpisodeIDs: playableEpisodeIDs) }
        .navigationDestination(isPresented: $showTwin) { TwinView() }
        .sheet(isPresented: $showScenes) {
            GardenScenePicker(scene: Binding(get: { scene }, set: { sceneChoice = $0.rawValue }), close: { showScenes = false })
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { GuestSharingView() } label: { Image(systemName: "person.2") }
                    .accessibilityLabel("亲友开放范围").accessibilityIdentifier("garden.guestSharing")
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(model.isUsingRealtimeAudio)
                    .accessibilityLabel("刷新记忆")
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button { showRemoved = true } label: { Image(systemName: "leaf.arrow.triangle.circlepath") }
                    .accessibilityLabel("查看移出的花").accessibilityIdentifier("garden.removed")
            }
        }
        .sheet(isPresented: Binding(get: { selectedFactID != nil }, set: { if !$0 { selectedFactID = nil } })) {
            NavigationStack {
                List {
                    if let item = graph.first(where: { $0.id == selectedFactID }) {
                        Section { Text(item.fact.content).font(RMTypography.title) }
                        Section("原文依据") {
                            ForEach(item.memories) { memory in
                                NavigationLink {
                                    GardenCurrentMemoryDetail(id: memory.id, scope: pairing.map(ReviewScope.init), fixture: fixture)
                                } label: { Text(memory.content) }.accessibilityIdentifier("garden.source." + memory.id)
                            }
                        }
                    } else { Text("来源或空间已变化，请返回花园刷新。") }
                }.navigationTitle("记忆联系").navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("关闭") { selectedFactID = nil } } }
            }
        }
        .sheet(isPresented: $showRemoved) {
            NavigationStack {
                List {
                    Text("这里只改变这台手机的花园展示。原音、原文与服务端记忆仍保留。")
                    if removed.isEmpty { Text("没有移出的花。") }
                    ForEach(removed) { entry in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(entry.title)
                            Button("恢复展示") {
                                if let pairing {
                                    for id in entry.displayIDs {
                                        visibility.setHidden(id, hidden: false, pairing: pairing)
                                    }
                                }
                            }
                                .accessibilityIdentifier("garden.restore." + entry.id)
                        }
                    }
                }.navigationTitle("移出的花")
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { showRemoved = false } } }
            }
        }
        .alert("移出这台手机的花园？", isPresented: Binding(get: { removal != nil }, set: { if !$0 { removal = nil } })) {
            Button("移出展示") {
                if let removal, let pairing { visibility.setHidden(removal.id, hidden: true, pairing: pairing) }
                removal = nil
            }
            Button("取消", role: .cancel) { removal = nil }
        } message: { Text("原音、原文和记忆仍保留。可以从右上角恢复；需要删除记忆时，请打开记忆详情。") }
        .alert("删除这篇故事？", isPresented: Binding(get: { deletion != nil }, set: { if !$0 { deletion = nil } })) {
            Button("删除故事", role: .destructive) {
                if let context = deletion { Task { await deleteEntry(context) } }
                deletion = nil
            }
            Button("取消", role: .cancel) { deletion = nil }
        } message: { Text("删除整理后的故事或事件，原始录音和原文仍保留。") }
        .task { if fixture == nil, !model.isUsingRealtimeAudio { await model.refresh() } }
        .task(id: key) {
            visibility.configure(pairing)
            if fixture == nil, !model.isUsingRealtimeAudio { await workspace.reload(pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion) }
        }
        .onChange(of: key.scope) { _, _ in query = ""; facet = nil; selectedFactID = nil; showRemoved = false; showTwin = false }
        .onChange(of: playableEpisodeIDs) { previous, current in
            if let id = model.playbackID, previous.contains(id), !current.contains(id) { model.stopPlayback() }
        }
        .refreshable { if fixture == nil, !model.isUsingRealtimeAudio { await model.refresh(); await workspace.reload(model.pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion) } }
    }
    private var browseControls: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("沿着花径，重温往事。").font(.system(.title2, design: .serif))
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(GardenSurfaceMode.allCases) { value in
                        Button(value.rawValue) { mode = value; facet = nil }
                            .buttonStyle(.bordered).tint(mode == value ? RMColors.action : RMColors.secondaryText)
                            .accessibilityAddTraits(mode == value ? .isSelected : [])
                            .accessibilityIdentifier("garden.mode." + value.id)
                    }
                }
            }.accessibilityIdentifier("garden.modes")
            HStack {
                Button(searchOpen ? "收起查找" : "查找", systemImage: "magnifyingglass") { searchOpen.toggle() }
                    .accessibilityIdentifier("garden.search.toggle")
                Spacer()
                Button("换一处花园 · " + scene.title) { showScenes = true }.font(.caption)
                    .accessibilityIdentifier("garden.changeScene")
            }
            if searchOpen {
                TextField("找故事、人物或一句话", text: $query).textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("garden.search")
                if !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    HStack {
                        Button(model.isSearchingMemories ? "查找中…" : "查找相关内容") {
                            guard fixture == nil, !model.isGuestMode else { return }
                            model.memorySearchQuery = query; Task { await model.searchMemories() }
                        }.disabled(model.isSearchingMemories || model.isUsingRealtimeAudio || fixture != nil)
                        Spacer()
                        Button("问一问") { model.queryDraft = query.trimmingCharacters(in: .whitespacesAndNewlines); showTwin = true }
                    }
                }
            }
            if mode == .meadow || mode == .list || mode == .timeline {
                Menu {
                    Button("全部侧面") { facet = nil }
                    ForEach(GardenFacet.allCases) { value in Button(value.title) { facet = value } }
                } label: { Label(facet?.title ?? "按记忆侧面筛选", systemImage: "line.3.horizontal.decrease.circle") }
                NavigationLink("了解故事里的人") { GardenNarrativePeoplePage(workspace: workspace, fixture: fixture) }
                let pending = model.episodes.filter { $0.status != "ready" }.count
                NavigationLink("待整理 · \(pending) 段") { ArchiveView() }.font(.caption)
            }
        }.padding(16).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22))
    }
    private var emptyGarden: some View {
        VStack(alignment: .center, spacing: RMSpacing.md) {
            GardenBotanicalAccent(artwork: .wreath).frame(width: 200, height: 208)
            Text("这里还没有可展示的记录").font(RMTypography.heading)
            Text("讲述一段经历，AI 整理出事件后就会出现在这里。")
                .font(RMTypography.detail).foregroundStyle(Ink.muted)
            if !removed.isEmpty { Text("移出的记忆可以恢复展示。") .font(RMTypography.detail).foregroundStyle(Ink.muted) }
        }.frame(maxWidth: .infinity).padding(.vertical, RMSpacing.xxl).accessibilityIdentifier("garden.empty")
    }

    private var timeline: some View {
        LazyVStack(alignment: .leading, spacing: 0) {
            ForEach(GardenTimelineProjection.groups(visible)) { group in
                HStack(spacing: RMSpacing.md) {
                    Circle().fill(RMColors.brand).frame(width: 8, height: 8)
                        .frame(width: 40).accessibilityHidden(true)
                    Text(group.title).font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
                }.padding(.vertical, RMSpacing.sm).background(alignment: .leading) { timelineStem }
                ForEach(group.entries) { entry in
                    GardenBranch {
                        VStack(alignment: .leading, spacing: RMSpacing.sm) {
                            entryLink(entry)
                            ForEach(GardenTimelineProjection.linkedFacts(for: entry, items: graph)) { item in
                                GardenBranch(small: true) {
                                    Button { selectedFactID = item.id } label: {
                                        Label(item.fact.content, systemImage: "point.3.connected.trianglepath.dotted")
                                            .font(RMTypography.caption).multilineTextAlignment(.leading)
                                            .fixedSize(horizontal: false, vertical: true)
                                            .frame(minHeight: RMMetrics.touchTarget, alignment: .leading)
                                    }.buttonStyle(RMQuietPressStyle()).foregroundStyle(RMColors.action)
                                        .accessibilityIdentifier("garden.link." + item.id + "." + entry.id)
                                }
                            }
                        }.padding(.vertical, RMSpacing.md)
                    }
                }
            }
        }.accessibilityIdentifier("garden.timeline")
    }

    private var timelineStem: some View {
        Rectangle().fill(RMColors.stem.opacity(0.5)).frame(width: 1).padding(.leading, 20).accessibilityHidden(true)
    }

    private func entryLink(_ entry: GardenEntry) -> some View {
        NavigationLink {
            GardenEntryDetail(id: entry.id, workspace: workspace, visibility: visibility, fixture: fixture)
        } label: {
            HStack(alignment: .top, spacing: RMSpacing.sm) {
                VStack(alignment: .leading, spacing: RMSpacing.xs) {
                    Text(entry.section == .people ? "人物" : "故事").font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
                    Text(entry.title).font(RMTypography.heading).foregroundStyle(RMColors.text)
                        .lineLimit(typeSize.isAccessibilitySize ? nil : 3).fixedSize(horizontal: false, vertical: true)
                    if !entry.date.hasPrefix("录入") { Text(entry.date).font(RMTypography.caption).foregroundStyle(RMColors.secondaryText) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                GardenArtworkImage(artwork: GardenArtwork.forEntry(entry))
                    .frame(width: typeSize.isAccessibilitySize ? 68 : 100, height: typeSize.isAccessibilitySize ? 90 : 126)
                    .accessibilityHidden(true)
                Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(RMColors.secondaryText)
                    .padding(.top, RMSpacing.lg).accessibilityHidden(true)
            }.frame(minHeight: RMMetrics.touchTarget).contentShape(Rectangle())
        }.buttonStyle(RMQuietPressStyle()).accessibilityIdentifier("garden.entry." + entry.id)
            .contextMenu {
                Button("删除故事", systemImage: "trash", role: .destructive) {
                    if let pairing { deletion = GardenEditing(entry: entry,
                        record: workspace.overview?.records.first { entry.id == "record:" + $0.id }, pairing: pairing) }
                }.disabled(model.isBusy)
                Button("移出本机花园", systemImage: "leaf.arrow.triangle.circlepath") { removal = entry }
            }
    }
    private func deleteEntry(_ context: GardenEditing) async {
        let entry = context.entry, pairing = context.pairing
        if fixture != nil { visibility.setHidden(entry.id, hidden: true, pairing: pairing); return }
        _ = await model.deleteGardenEntry(entry, record: context.record, scope: ReviewScope(pairing))
        guard model.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return }
        await workspace.reload(pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
    }
}

private struct GardenBotanicalAccent: View {
    var artwork = GardenArtwork.wreath
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    @State private var visible = false
    @State private var origin = Date()
    private var paused: Bool {
        RMFlowerMotion.paused(reduceMotion: reduceMotion || animationsDisabled, sceneActive: scenePhase == .active,
                              visible: visible, state: .idle)
    }
    var body: some View {
        TimelineView(.animation(minimumInterval: RMAnimationTokens.frameInterval, paused: paused)) { timeline in
            let time = paused ? 0 : timeline.date.timeIntervalSince(origin)
            GardenArtworkImage(artwork: artwork)
                .rotationEffect(.degrees(paused ? 0 : sin(time * 0.3) * 0.7), anchor: .bottom)
                .offset(y: paused ? 0 : sin(time * 0.4) * 1.5)
                .overlay {
                    if !paused {
                        Canvas { context, size in
                            for particle in GardenPetalMotion.particles(time: time) {
                                var layer = context
                                layer.translateBy(x: size.width * particle.x, y: size.height * particle.y)
                                layer.rotate(by: .degrees(particle.angle))
                                layer.fill(FlowerPetal().path(in: CGRect(x: -2.5, y: -3.5, width: 5, height: 7)),
                                           with: .color(RMColors.flowerPetal.opacity(particle.opacity)))
                            }
                        }
                    }
                }
        }.accessibilityHidden(true).allowsHitTesting(false)
            .onAppear { visible = true }.onDisappear { visible = false }
    }
}

private struct GardenBranch<Content: View>: View {
    var small = false
    @ViewBuilder var content: Content
    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            Color.clear.frame(width: small ? 28 : 56)
            content
        }.background(alignment: .leading) {
            GardenBranchLine(small: small).stroke(RMColors.stem.opacity(0.5), style: StrokeStyle(lineWidth: 1, lineCap: .round))
                .frame(width: small ? 24 : 48).accessibilityHidden(true)
        }.overlay(alignment: .topLeading) {
            if !small {
                ForgetMeNotFlower(size: 26).frame(width: 40, height: 40).offset(y: 12)
                    .allowsHitTesting(false)
            }
        }
    }
}

private struct GardenBranchLine: Shape {
    var small = false
    func path(in rect: CGRect) -> Path {
        let x: CGFloat = small ? 4 : 20
        let y: CGFloat = 32
        var path = Path()
        path.move(to: CGPoint(x: x, y: 0))
        path.addLine(to: CGPoint(x: x, y: rect.height))
        path.move(to: CGPoint(x: x, y: max(0, y - 16)))
        path.addQuadCurve(to: CGPoint(x: rect.maxX, y: y), control: CGPoint(x: x, y: y))
        return path
    }
}

struct GardenEntryDetail: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let id: String
    @ObservedObject var workspace: MemoryGardenWorkspace
    @ObservedObject var visibility: GardenVisibility
    let fixture: GardenPreview?
    @State private var showRemove = false
    @State private var deletion: GardenEditing?
    @State private var editing: GardenEditing?
    @State private var didSave = false
    private var pairing: Pairing? { fixture?.pairing ?? model.pairing }
    private var entry: GardenEntry? {
        if let fixture { return fixture.entries.first { $0.id == id }.map(visibility.previewEntry) }
        guard let pairing, workspace.canDisplayEntries(for: pairing, revision: model.memoryContentRevision,
            memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion) else { return nil }
        return (GardenHomeProjection.entries(memories: model.memories, episodes: model.episodes,
            overview: workspace.currentOverview(for: pairing, revision: model.memoryContentRevision,
                memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)) +
            MemoryGardenProjection.entries(memories: model.memories, episodes: model.episodes,
                overview: workspace.currentOverview(for: pairing, revision: model.memoryContentRevision,
                    memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion))).first { $0.id == id }
    }
    var body: some View {
        List {
            if let entry {
                Section {
                    Text(entry.label).font(.caption).foregroundStyle(Ink.coral)
                    Text(entry.title).font(.title2.weight(.medium))
                    if entry.text != entry.title { Text(entry.text).lineSpacing(6) }
                    Text(entry.date).font(.caption).foregroundStyle(Ink.muted)
                }
                if !entry.memories.isEmpty {
                    Section("花瓣里的片段") { GardenPetalPages(entry: entry, scope: pairing.map(ReviewScope.init), workspace: workspace, fixture: fixture) }
                }
                let episodeIDs = Set(entry.evidence.map(\.episode_id) + entry.memories.map(\.episode_id))
                let originals = model.episodes.filter { episodeIDs.contains($0.id) && $0.source != "IOS_TEXT" }
                if !originals.isEmpty {
                    Section("相关原音") {
                        ForEach(originals) { episode in OriginalPlayer(episodeID: episode.id) }
                    }
                }
                if !entry.evidence.isEmpty {
                    Section("支持这条记录的原话") {
                        ForEach(entry.evidence) { source in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(source.excerpt)
                                Text(sourceLabel(source.source_type)).font(.caption).foregroundStyle(Ink.muted)
                            }
                        }
                    }
                }
                Section("原始记忆与管理") {
                    ForEach(entry.memories) { memory in
                        NavigationLink { GardenCurrentMemoryDetail(id: memory.id, scope: pairing.map(ReviewScope.init), fixture: fixture) } label: { Text(memory.content) }
                    }
                    if entry.memories.isEmpty { Text("这篇故事由原文整理，下面保留了原话依据。") }
                    Text("删除一条记忆会让相关理解和回答失效，原始录音仍保留。")
                        .font(.caption).foregroundStyle(Ink.muted)
                }
                if !entry.id.hasPrefix("episode:") { Section {
                    Button("手动编辑", systemImage: "pencil") {
                        if let pairing {
                            didSave = false
                            editing = GardenEditing(entry: entry,
                                record: workspace.overview?.records.first { entry.id == "record:" + $0.id }, pairing: pairing)
                        }
                    }.disabled(model.isBusy).accessibilityIdentifier("garden.edit")
                    Button("删除故事", role: .destructive) {
                        if let pairing { deletion = GardenEditing(entry: entry,
                            record: workspace.overview?.records.first { entry.id == "record:" + $0.id }, pairing: pairing) }
                    }
                        .disabled(model.isBusy).accessibilityIdentifier("garden.delete")
                    Text("删除整理后的故事或事件，原始录音和原文仍保留。")
                        .font(.caption).foregroundStyle(Ink.muted)
                    if let error = model.errorMessage { Text(error).foregroundStyle(.red) }
                } }
                Section {
                    Button("移出本机花园") { showRemove = true }.accessibilityIdentifier("garden.remove")
                    if let error = visibility.error { Text(error).foregroundStyle(.red) }
                    Text("只改变展示，可以恢复；不删除原音、原文或服务端记忆。")
                        .font(.caption).foregroundStyle(Ink.muted)
                }
            } else {
                Text(workspace.isLoading ? "正在重新核对来源…" : "来源或空间已变化，这条记录不再展示。请返回花园刷新。")
            }
        }.navigationTitle("花朵里的记忆").navigationBarTitleDisplayMode(.inline)
            .sheet(item: $editing, onDismiss: { if didSave { dismiss() } }) { context in
                GardenStoryEditor(entry: context.entry) { title, text in
                    if fixture != nil {
                        visibility.editPreview(context.entry, title: title, text: text); didSave = true; return nil
                    }
                    let saved = await model.saveGardenEntry(context.entry, record: context.record,
                        title: title, text: text, scope: ReviewScope(context.pairing))
                    guard saved else { return model.errorMessage ?? "未能保存，请刷新后重试。" }
                    guard model.pairing.map(ReviewScope.init) == ReviewScope(context.pairing) else { return "本人空间已变化，请重新打开故事。" }
                    await workspace.reload(context.pairing, revision: model.memoryContentRevision,
                        memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
                    didSave = true; return nil
                }
            }
            .alert("移出这台手机的花园？", isPresented: $showRemove) {
                Button("移出展示") { if let pairing { visibility.setHidden(id, hidden: true, pairing: pairing); if visibility.error == nil { dismiss() } } }
                Button("取消", role: .cancel) { }
            } message: { Text("原音、原文和记忆仍保留，可以从花园右上角恢复展示。") }
            .alert("删除这篇故事？", isPresented: Binding(get: { deletion != nil }, set: { if !$0 { deletion = nil } })) {
                Button("删除故事", role: .destructive) {
                    if let context = deletion { Task { await deleteEntry(context) } }
                    deletion = nil
                }
                Button("取消", role: .cancel) { deletion = nil }
            } message: { Text("删除整理后的故事或事件，原始录音和原文仍保留。") }
    }
    private func deleteEntry(_ context: GardenEditing) async {
        let entry = context.entry, pairing = context.pairing
        if fixture != nil {
            visibility.setHidden(entry.id, hidden: true, pairing: pairing)
            if visibility.error == nil { dismiss() }
            return
        }
        let deleted = await model.deleteGardenEntry(entry, record: context.record, scope: ReviewScope(pairing))
        guard model.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return }
        await workspace.reload(pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
        if deleted { dismiss() }
    }
}

private struct GardenStoryEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State private var title: String
    @State private var text: String
    @State private var saving = false
    @State private var error: String?
    private let save: (String, String) async -> String?
    init(entry: GardenEntry, save: @escaping (String, String) async -> String?) {
        _title = State(initialValue: entry.title); _text = State(initialValue: entry.text); self.save = save
    }
    private var valid: Bool {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return !title.isEmpty && title.count <= 120 && !text.isEmpty && text.count <= 1500
    }
    var body: some View {
        NavigationStack {
            Form {
                Section("标题") {
                    TextField("给这段经历起个名字", text: $title, axis: .vertical)
                        .accessibilityIdentifier("garden.editor.title")
                }
                Section("故事内容") {
                    TextEditor(text: $text).frame(minHeight: 220).accessibilityIdentifier("garden.editor.text")
                    Text("\(text.count) / 1500 字").font(.caption).foregroundStyle(Ink.muted)
                }
                Text("编辑整理内容，原始录音和原文保留。")
                    .font(.footnote).foregroundStyle(Ink.muted)
                if let error { Text(error).foregroundStyle(.red).accessibilityIdentifier("garden.editor.error") }
            }.navigationTitle("编辑故事").navigationBarTitleDisplayMode(.inline)
                .disabled(saving).interactiveDismissDisabled(saving)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() }.disabled(saving) }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(saving ? "保存中…" : "保存") {
                            saving = true; error = nil
                            Task {
                                error = await save(title.trimmingCharacters(in: .whitespacesAndNewlines),
                                                   text.trimmingCharacters(in: .whitespacesAndNewlines))
                                saving = false
                                if error == nil { dismiss() }
                            }
                        }.disabled(!valid || saving).accessibilityIdentifier("garden.editor.save")
                    }
                    ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("完成") { dismissKeyboard() } }
                }
        }
    }
    private func dismissKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }
}

struct GardenCurrentMemoryDetail: View {
    @EnvironmentObject private var model: AppModel
    let id: String
    let scope: ReviewScope?
    var fixture: GardenPreview? = nil
    var body: some View {
        if let fixture, scope == ReviewScope(fixture.pairing), let memory = fixture.entries.flatMap(\.memories).first(where: { $0.id == id }) {
            MemoryDetailView(memory: memory)
        } else if scope != nil, scope == model.pairing.map(ReviewScope.init), let memory = model.memories.first(where: { $0.id == id }) {
            MemoryDetailView(memory: memory)
        } else { Text("来源或空间已变化，请返回花园刷新。").padding() }
    }
}

struct GardenPreview {
    let pairing: Pairing
    let entries: [GardenEntry]
    let graphFacts: [GraphFactRecord]
    var overview: ReviewOverview? = nil
    var episodes: [EpisodeRecord] {
        entries.flatMap(\.memories).map { memory in
            EpisodeRecord(episode_id: memory.episode_id, status: "ready", source: memory.capture_source ?? "IOS_TEXT", recorded_at: memory.recorded_at,
                duration_ms: 1000, transcript: memory.transcript, stt_backend: nil, stt_model_version: nil, model_version: memory.model_version, error_code: nil)
        }
    }
    static var current: GardenPreview? {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("--uitest-memory-garden") else { return nil }
        let pairing = Pairing(baseURL: "https://fixture.invalid", fingerprint: String(repeating: "a", count: 64), token: "fixture",
                              actorID: "fixture-actor", subjectID: "fixture-subject", consentID: "fixture-consent")
        let entries = [("story-a", "那年在大学种下的一棵树", "当时我们一起去种树，后来每次回校都会去看看。", GardenSection.stories, "2026-10-14T00:00:00Z"),
                       ("story-b", "和家人一起做的一顿饭", "周末大家围坐在厨房，各自讲起最近遇到的小事。", .stories, "2026-05-09T00:00:00Z"),
                       ("person-a", "和老朋友一起散步的傍晚", "我们一边散步，一边聊起大学时的经历。", .stories, "2025-09-01T00:00:00Z")].map {
            GardenEntry(id: $0.0, title: $0.1, text: $0.2, label: $0.3 == .people ? "人物" : "故事", date: MemoryGardenProjection.recordingDate($0.4), sortDate: $0.4,
                        section: $0.3, memories: [MemoryRecord(memory_item_id: $0.0, episode_id: "fixture-episode-" + $0.0,
                            content: $0.2, memory_type: $0.3 == .people ? "PERSON" : "EVENT", domain: nil,
                            source_type: "SUBJECT", confidence: 1, model_version: "isolated-fixture", recorded_at: $0.4,
                            transcript: $0.2, stt_model_version: nil, capture_source: "IOS_TEXT",
                            evidence: [EvidenceRecord(evidence_id: "source-" + $0.0, excerpt: $0.2, source_type: "SUBJECT",
                                source_ref: "fixture-episode-" + $0.0, span_start: nil, span_end: nil)])], evidence: [])
        }
        var preview = GardenPreview(pairing: pairing, entries: entries, graphFacts: [
            GraphFactRecord(fact_id: "fixture-tree", subject_id: pairing.subjectID, kind: "EVENT", content: "大学时一起种树",
                            evidence_ids: ["source-story-a"], model_version: "isolated-fixture", valid_from: nil, valid_to: nil)])
        let sources = entries.flatMap(\.memories).flatMap { memory in
            memory.evidence.map { ReviewEvidence(evidence_id: $0.id, episode_id: memory.episode_id, excerpt: $0.excerpt ?? "",
                source_type: $0.source_type, temporal_context: nil) }
        }
        let rows: [(String, String, String, String, [String], Int)] = [
            ("fixture-life", "story", "那年种下的一棵树", entries[0].text, ["EXPERIENCE", "FEELINGS"], 0),
            ("fixture-person", "person", "一起散步的老朋友", entries[2].text, ["RELATIONSHIPS"], 2),
            ("fixture-choice", "observation", "和家人一起做饭", entries[1].text, ["PRACTICES", "VALUES", "WISHES", "IDENTITY"], 1),
            ("fixture-expression", "style", "关于回校的原话", entries[0].text, ["EXPRESSION"], 0)]
        let records = rows.map { item in
            let source = sources[item.5]
            return ReviewRecord(id: item.0, kind: item.1, title: item.2, text: item.3, evidence_ids: [source.id], facets: item.4,
                time_text: "", place_text: "", aliases: [], same_event: false, recipient_label: "", status: "confirmed", revision: 1,
                model_version: "isolated-fixture", prompt_version: "isolated-fixture", evidence: [source], source_valid: true, historical: false)
        }
        preview.overview = ReviewOverview(subject_id: pairing.subjectID, role: "owner", records: records, source_evidence: sources,
            style: ReviewStyle(enabled: false, revision: 0), understandings: [
                GardenUnderstanding(candidate_id: "fixture-understanding", statement: "想念一起经历过的日子", context: "回校时的讲述", status: "confirmed",
                    evidence_ids: [sources[0].id], counter_evidence_ids: [], evidence: [sources[0]], counter_evidence: [], model_version: "isolated-fixture")])
        return preview
        #else
        return nil
        #endif
    }
}

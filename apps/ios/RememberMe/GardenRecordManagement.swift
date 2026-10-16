import SwiftUI

private struct GardenRecordEditContext: Identifiable {
    let input: ReviewRecordInput
    let split: Bool
    var id: String { (split ? "split:" : "edit:") + input.title }
}

struct GardenNarrativeRecordDetail: View {
    @EnvironmentObject private var model: AppModel
    let id: String
    @ObservedObject var workspace: MemoryGardenWorkspace
    let fixture: GardenPreview?
    private let openedScope: ReviewScope?
    @State private var editor: GardenRecordEditContext?
    @State private var history: GardenHistoryReply?
    @State private var showHistory = false
    @State private var showReject = false
    @State private var busy = false
    @State private var error: String?
    @State private var selectedSource = ""
    init(id: String, workspace: MemoryGardenWorkspace, fixture: GardenPreview?) {
        self.id = id; self.workspace = workspace; self.fixture = fixture
        openedScope = fixture.map { ReviewScope($0.pairing) } ?? workspace.scope
    }
    private var overview: ReviewOverview? {
        if let fixture { return fixture.overview }
        guard !model.isGuestMode, let pairing = model.pairing, ReviewScope(pairing) == openedScope else { return nil }
        return workspace.currentOverview(for: pairing, revision: model.memoryContentRevision,
            memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
    }
    private var row: ReviewRecord? {
        guard let overview else { return nil }
        return overview.records.first { $0.id == id && ["pending", "confirmed"].contains($0.status) &&
            GardenNarrativeProjection.hasCurrentEvidence($0, overview: overview, episodes: fixture?.episodes ?? model.episodes) }
    }
    private var canWrite: Bool {
        fixture == nil && !busy && !model.isGuestMode && !model.isBusy && !model.isRecording && !model.isStartingRecording &&
            !model.realtimeVoice.isActive && !model.isSpeakerRecording && !model.isQueryRecording && !model.isVoiceRecording && !model.personReview.isMutating
    }
    private var originalIDs: [String] {
        guard let row else { return [] }
        let ids = Set(row.evidence.map(\.episode_id))
        return model.episodes.filter { ids.contains($0.id) && $0.status == "ready" && $0.source != "IOS_TEXT" }.map(\.id).sorted()
    }
    var body: some View {
        List {
            if let row {
                Section(GardenNarrativeProjection.kindTitle(row.kind) + " · " + (row.status == "confirmed" ? "本人已核对" : "待核对")) {
                    Text(row.title).font(.system(.title2, design: .serif))
                    Text(row.text).lineSpacing(6).textSelection(.enabled)
                    Text(row.facets.compactMap { GardenFacet(rawValue: $0)?.title }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                    if !row.time_text.isEmpty { Text("发生时间：" + row.time_text) }
                    if !row.place_text.isEmpty { Text("当时地点：" + row.place_text) }
                    if !row.aliases.isEmpty { Text("材料中的称呼：" + row.aliases.joined(separator: "、")) }
                    if !row.recipient_label.isEmpty { Text("想留给：" + row.recipient_label + " · 仍按录音开放范围") }
                }
                Section("为什么这样整理 · \(Set(row.evidence.map(\.episode_id)).count) 段来源") {
                    ForEach(row.evidence) { source in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(source.excerpt)
                            Text(sourceLabel(source.source_type)).font(.caption).foregroundStyle(.secondary)
                            NavigationLink("打开来源与完整原音") { GardenEpisodeSourceView(episodeID: source.episode_id, scope: openedScope) }
                        }
                    }
                }
                let stories = GardenNarrativeProjection.relatedStories(to: row,
                    records: GardenNarrativeProjection.records(overview, episodes: fixture?.episodes ?? model.episodes))
                if !stories.isEmpty {
                    Section("从这些故事继续了解") {
                        ForEach(stories) { story in
                            NavigationLink(story.title) { GardenNarrativeRecordDetail(id: story.id, workspace: workspace, fixture: fixture) }
                        }
                    }
                }
                Section("整理与核对") {
                    if row.status == "pending" {
                        Button("核对无误，确认整理") { Task { _ = await mutate(row, action: "confirm") } }.disabled(!canWrite)
                            .accessibilityIdentifier("garden.record.confirm")
                    }
                    Button("编辑内容 / 移出来源") { editor = GardenRecordEditContext(input: ReviewRecordInput(row), split: false) }
                        .disabled(!canWrite).accessibilityIdentifier("garden.record.edit")
                    if row.kind == "story" && row.evidence_ids.count > 1 {
                        Button("拆出新故事") {
                            var input = ReviewRecordInput(row); input.title = String((row.title + " · 拆分").prefix(120))
                            editor = GardenRecordEditContext(input: input, split: true)
                        }.disabled(!canWrite).accessibilityIdentifier("garden.record.split")
                    }
                    Button("变化历史") { Task { await loadHistory(row) } }.disabled(!canWrite).accessibilityIdentifier("garden.record.history")
                    if row.revision > 2 {
                        Button("恢复旧内容，再核对") { Task { _ = await mutate(row, action: "undo") } }.disabled(!canWrite)
                            .accessibilityIdentifier("garden.record.undo")
                    }
                    Button("撤回这项整理", role: .destructive) { showReject = true }.disabled(!canWrite)
                        .accessibilityIdentifier("garden.record.reject")
                    Text("整理保留版本与依据；修改和恢复后需要重新核对，原始录音保留。")
                        .font(.footnote).foregroundStyle(.secondary)
                    if busy { ProgressView("正在处理…") }
                    if let error { Text(error).font(.footnote).foregroundStyle(.red) }
                    Text("模型：\(row.model_version) · 版本 \(row.revision)").font(.caption).foregroundStyle(.secondary)
                }
            } else { Text("内容或来源已变化，请返回花园重新核对。") }
        }.navigationTitle("记忆里的侧面").navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .bottom) { transport }
            .onAppear { selectedSource = originalIDs.first ?? "" }
            .onChange(of: originalIDs) { _, ids in
                if !ids.contains(selectedSource) {
                    // A refresh may temporarily hide the document. It must not
                    // interrupt an original that remains available to this owner.
                    let stillAvailable = !model.isGuestMode && model.pairing.map(ReviewScope.init) == openedScope &&
                        model.episodes.contains { $0.id == selectedSource && $0.status == "ready" && $0.source != "IOS_TEXT" }
                    if !stillAvailable {
                        if model.playbackID == selectedSource { model.stopPlayback() }
                        selectedSource = ids.first ?? ""
                    }
                }
            }
            .onChange(of: model.pairing.map(ReviewScope.init)) { _, _ in editor = nil; history = nil; showHistory = false }
            .sheet(item: $editor) { context in
                GardenNarrativeEditor(input: context.input, sources: overview?.source_evidence ?? [], split: context.split) { input in
                    guard let row, row.revision == context.input.revision else { return "内容已变化，请返回花园刷新。" }
                    let success = await mutate(row, action: context.split ? "split" : "edit", input: input)
                    return success ? nil : error ?? "保存未完成，请重试。"
                }
            }
            .sheet(isPresented: $showHistory) {
                NavigationStack {
                    List {
                        if row != nil, let history, let overview {
                            ForEach(history.currentItems(evidenceIDs: Set(overview.source_evidence.map(\.id)))) { item in
                                Section("版本 \(item.revision) · \(historyAction(item.action))") {
                                    Text(item.record.title).font(.headline); Text(item.record.text)
                                    Text(item.created_at).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        } else { Text("来源已变化，历史内容暂不展示。") }
                    }.navigationTitle("理解怎样改变")
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("返回") { showHistory = false } } }
                }
            }
            .alert("撤回这项整理？", isPresented: $showReject) {
                Button("撤回整理", role: .destructive) { if let row { Task { _ = await mutate(row, action: "reject") } } }
                Button("取消", role: .cancel) { }
            } message: { Text("原始录音和原文保留，相关理解与回答将重新核验。") }
    }
    @ViewBuilder private var transport: some View {
        if !originalIDs.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                if originalIDs.count > 1 {
                    Picker("选择原音", selection: $selectedSource) {
                        ForEach(Array(originalIDs.enumerated()), id: \.element) { index, id in Text("原音 \(index + 1)").tag(id) }
                    }.pickerStyle(.menu).onChange(of: selectedSource) { old, new in
                        if old != new {
                            if model.playbackLoading { model.stopPlayback() }
                            else if model.playbackID == old, model.isPlaying { model.toggleCurrentPlayback() }
                        }
                    }
                }
                OriginalPlayer(episodeID: selectedSource).disabled(model.isRecording || model.realtimeVoice.isActive)
            }.padding(16).background(.regularMaterial)
        }
    }
    private func loadHistory(_ row: ReviewRecord) async {
        guard canWrite, let pairing = model.pairing, ReviewScope(pairing) == openedScope else { return }
        busy = true; error = nil; defer { busy = false }
        do {
            let client = try APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token)
            let reply = try await client.gardenRecordHistory(subject: pairing.subjectID, record: row.id)
            guard !Task.isCancelled, model.pairing.map(ReviewScope.init) == openedScope, self.row?.revision == row.revision else { return }
            history = reply; showHistory = true
        } catch { if model.pairing.map(ReviewScope.init) == openedScope { self.error = "历史未能读取，请重试。" } }
    }
    private func mutate(_ row: ReviewRecord, action: String, input: ReviewRecordInput? = nil) async -> Bool {
        guard canWrite, let pairing = model.pairing, ReviewScope(pairing) == openedScope,
              ["confirm", "reject", "undo", "edit", "split"].contains(action), self.row?.revision == row.revision,
              !row.id.isEmpty, row.id.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-")).contains($0) }) else { return false }
        if let input, let message = input.validationMessage(sources: overview?.source_evidence ?? []) { error = message; return false }
        if action == "split", let input, !(Set(input.evidence_ids).isStrictSubset(of: Set(row.evidence_ids))) {
            error = "拆分时选择部分来源，两个故事都须保留依据。"; return false
        }
        busy = true; model.isBusy = true; error = nil; history = nil
        let scope = ReviewScope(pairing)
        model.personReview.onMutation?(scope)
        var succeeded = false
        do {
            let client = try APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token)
            let body: Data
            if let input { body = try JSONEncoder().encode(input) }
            else { body = try JSONSerialization.data(withJSONObject: ["revision": row.revision]) }
            let suffix = "narrative/records/" + row.id + (action == "edit" ? "" : "/" + action)
            try await client.reviewWrite(subject: pairing.subjectID, suffix: suffix, method: action == "edit" ? "PUT" : "POST", body: body)
            succeeded = true
        } catch { if model.pairing.map(ReviewScope.init) == scope { self.error = error.localizedDescription } }
        busy = false
        guard model.pairing.map(ReviewScope.init) == scope, !model.isGuestMode else { return false }
        model.isBusy = false
        await model.personReview.reload()
        await model.refresh()
        await workspace.reload(pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
        return succeeded
    }
    private func historyAction(_ action: String) -> String {
        ["create": "创建", "edit": "修改", "split": "拆分", "confirm": "确认", "reject": "撤回", "undo": "恢复"][action] ?? "更新"
    }
}

struct GardenNarrativeEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State var input: ReviewRecordInput
    let sources: [ReviewEvidence]
    let split: Bool
    let save: (ReviewRecordInput) async -> String?
    @State private var saving = false
    @State private var error: String?
    init(input: ReviewRecordInput, sources: [ReviewEvidence], split: Bool, save: @escaping (ReviewRecordInput) async -> String?) {
        _input = State(initialValue: input)
        self.sources = split ? sources.filter { input.evidence_ids.contains($0.id) } : sources
        self.split = split; self.save = save
    }
    var body: some View {
        NavigationStack {
            Form {
                Section(split ? "拆分故事 · 两篇都保留依据" : "内容 · 保存后待核对") {
                    if input.revision == nil {
                        Picker("内容类型", selection: $input.kind) {
                            ForEach(["story", "person", "observation", "letter", "style"], id: \.self) { kind in Text(GardenNarrativeProjection.kindTitle(kind)).tag(kind) }
                        }.onChange(of: input.kind) { _, kind in
                            if ["letter", "style"].contains(kind), !input.facets.contains("EXPRESSION") { input.facets.append("EXPRESSION") }
                        }
                    }
                    TextField("标题", text: $input.title).accessibilityIdentifier("garden.record.editor.title")
                    TextEditor(text: $input.text).frame(minHeight: 180).accessibilityIdentifier("garden.record.editor.text")
                    Text("\(input.text.count) / 1500 字").font(.caption).foregroundStyle(.secondary)
                    TextField("发生时间 · 取自原文", text: $input.time_text)
                    TextField("地点 · 取自原文", text: $input.place_text)
                    TextField("想留给谁", text: $input.recipient_label)
                }
                Section("记忆侧面") {
                    ForEach(GardenFacet.allCases) { facet in
                        Toggle(facet.title, isOn: Binding(get: { input.facets.contains(facet.rawValue) }, set: { enabled in
                            input.facets.removeAll { $0 == facet.rawValue }; if enabled { input.facets.append(facet.rawValue) }
                        }))
                    }
                }
                Section("原文依据 · 可移出来源") {
                    ForEach(sources) { source in
                        Toggle(isOn: Binding(get: { input.evidence_ids.contains(source.id) }, set: { enabled in
                            input.evidence_ids.removeAll { $0 == source.id }; if enabled { input.evidence_ids.append(source.id) }
                        })) { Text(source.excerpt).font(.subheadline) }
                    }
                }
                if let error { Text(error).foregroundStyle(.red) }
                Text("原始录音保留。表达范例和寄语必须逐字取自本人原话，不能扩写。")
                    .font(.footnote).foregroundStyle(.secondary)
            }.navigationTitle(split ? "拆出新故事" : "编辑整理内容").navigationBarTitleDisplayMode(.inline)
                .disabled(saving).interactiveDismissDisabled(saving).rmDismissibleKeyboard()
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() }.disabled(saving) }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("保存") {
                            if let message = input.validationMessage(sources: sources) { error = message; return }
                            saving = true; error = nil
                            Task { error = await save(input); saving = false; if error == nil { dismiss() } }
                        }.disabled(saving).accessibilityIdentifier("garden.record.editor.save")
                    }
                }
        }
    }
}

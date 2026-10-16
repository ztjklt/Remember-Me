import SwiftUI

struct PersonReviewView: View {
    @EnvironmentObject private var app: AppModel
    @ObservedObject var review: PersonReviewModel
    @State private var section = "待核对"
    @State private var showGrouping = false

    var body: some View {
        List {
            Section {
                Text("原文是记忆；这里的整理和理解需要你核对。拒绝理解会保留原文，修改后需要重新确认。")
                    .font(.subheadline).foregroundStyle(.secondary)
                if app.pairing == nil {
                    Button("连接我的服务") { app.showConnection = true }
                }
                if let error = review.errorMessage { Text(error).foregroundStyle(.red).accessibilityIdentifier("review.error") }
                if let notice = review.notice { Text(notice).foregroundStyle(.secondary).accessibilityIdentifier("review.notice") }
                if review.isLoading || review.isMutating { ProgressView(review.isMutating ? "正在保存…" : "正在读取…") }
                Button("刷新") { Task { await review.reload() } }.disabled(review.isMutating)
            }
            if review.isReady || (review.isLoading && !review.sources.isEmpty) {
                Section("整理原文") {
                    if let consent = app.cloudConsentID {
                        Button("从原文整理候选理解") { Task { _ = await review.requestSuggestions(consentID: consent, narrative: false) } }
                            .disabled(review.isMutating || review.hasRunningJobs)
                        Button("整理故事与表达建议") { Task { _ = await review.requestSuggestions(consentID: consent, narrative: true) } }
                            .disabled(review.isMutating || review.hasRunningJobs)
                    } else {
                        NavigationLink("先授权云端 Twin，再使用模型整理") { TwinView() }
                    }
                    Text("模型整理会发送已授权的文字给服务端模型。提交后需等待任务完成，再由你核对。")
                        .font(.caption).foregroundStyle(.secondary)
                    ForEach(review.jobs) { job in
                        VStack(alignment: .leading) {
                            Text("整理任务：\(reviewStatus(job.status))")
                            if let error = job.error { Text(error).font(.caption).foregroundStyle(.red) }
                        }
                    }
                }
                Section {
                    Picker("查看内容", selection: $section) {
                        ForEach(["待核对", "已确认", "原文", "历史"], id: \.self) { Text($0) }
                    }.pickerStyle(.segmented)
                }
                if section == "原文" {
                    Section("有效原文 · 不等于独立事件数") {
                        Button("把多次讲述归为同一故事") { showGrouping = true }
                            .disabled(review.sources.count < 2 || review.isMutating)
                        if review.sources.isEmpty { Text("还没有可用原文。请先完成录音或文字核对。") }
                        ForEach(review.sources) { source in
                            NavigationLink { ReviewSourceDetail(review: review, source: source) } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(source.excerpt).lineLimit(4)
                                    Text(source.isOwnWords ? "本人原话" : "他人转述").font(.caption).foregroundStyle(.secondary)
                                }
                            }.accessibilityIdentifier("review.source.\(source.id)")
                        }
                    }
                } else {
                    let expected = section == "待核对" ? "pending" : "confirmed"
                    let historical = section == "历史"
                    let candidates = review.candidates.filter { historical ? !["pending", "confirmed"].contains($0.status) : $0.status == expected }
                    let records = review.records.filter { historical ? !["pending", "confirmed"].contains($0.status) : $0.status == expected }
                    Section("人物理解") {
                        if candidates.isEmpty { Text("暂无\(section)的人物理解。") }
                        ForEach(candidates) { candidate in
                            NavigationLink { ReviewCandidateDetail(review: review, candidate: candidate) } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(candidate.statement)
                                    Text("\(reviewStatus(candidate.status)) · \(reviewDomainLabel(candidate.domain))").font(.caption).foregroundStyle(.secondary)
                                }
                            }.accessibilityIdentifier("review.candidate.\(candidate.id)")
                        }
                    }
                    Section("故事与表达") {
                        if records.isEmpty { Text("暂无\(section)的整理内容。") }
                        ForEach(records) { record in
                            NavigationLink { ReviewRecordDetail(review: review, record: record) } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(record.title)
                                    Text("\(reviewKind(record.kind)) · \(reviewStatus(record.status))").font(.caption).foregroundStyle(.secondary)
                                }
                            }.accessibilityIdentifier("review.record.\(record.id)")
                        }
                    }
                    Section("理解之间的关联") {
                        ForEach(review.updates.filter { historical ? $0.status != "pending" : $0.status == expected }) { update in
                            ReviewUpdateCard(review: review, update: update)
                        }
                    }
                }
                Section("Twin 的表达") {
                    Toggle("使用已确认的本人原话范例", isOn: Binding(get: { review.style.enabled }, set: { value in
                        Task { _ = await review.setStyle(value) }
                    })).disabled(review.isMutating || (!review.style.enabled && !review.canUseStyle))
                        .accessibilityIdentifier("review.style")
                    Text("先从原文选择表达范例并确认，再启用。范例帮助表达，不能证明人格或保证完全复刻。")
                        .font(.caption).foregroundStyle(.secondary)
                    NavigationLink("向 Twin 提问并查看依据") { TwinView() }
                }
            }
        }
        .navigationTitle("核对我的理解")
        .sheet(isPresented: $showGrouping) { NavigationStack { ReviewStoryGrouping(review: review) }.environmentObject(app) }
        .task(id: app.pairing.map(ReviewScope.init)) {
            if review.scope != app.pairing.map(ReviewScope.init) { review.configure(app.pairing) }
            await review.reload()
        }
        .task(id: review.hasRunningJobs) {
            // Poll only while this screen is visible. Failed jobs require an explicit retry.
            for _ in 0..<30 where review.hasRunningJobs {
                do { try await Task.sleep(for: .seconds(2)) } catch { return }
                guard !Task.isCancelled else { return }
                await review.reload()
            }
        }
        .refreshable { await review.reload() }
    }
}

private func reviewStatus(_ status: String) -> String {
    ["pending": "待本人核对", "confirmed": "本人已确认", "rejected": "未采用", "stale": "依据已变化",
     "superseded": "已被更新", "applied": "已纳入更新", "conflicted": "存在不同说法",
     "queued": "排队中", "running": "处理中", "complete": "已完成", "completed": "已完成", "failed": "失败" ][status] ?? status
}
private func reviewKind(_ kind: String) -> String {
    ["story": "故事", "person": "人物", "observation": "情境观察", "letter": "寄语", "style": "表达范例"][kind] ?? kind
}
private func reviewDomainLabel(_ domain: String) -> String {
    ["IDENTITY": "我是谁", "EPISODIC_MEMORY": "生命片段", "RELATIONSHIPS": "人与关系",
     "PREFERENCES": "喜欢与不喜欢", "VALUES_BELIEFS": "珍视的事", "DECISION_PATTERNS": "做决定的方式",
     "EXPRESSION": "表达方式"][domain] ?? "情境观察"
}
private func relationName(_ action: String) -> String {
    ["SUPPORT": "补充支持", "CHANGE": "后来发生变化", "CONFLICT": "存在不同说法", "ADD": "新增理解"][action] ?? action
}

private struct ReviewEvidenceCard: View {
    @EnvironmentObject private var app: AppModel
    let source: ReviewEvidence
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(source.excerpt).textSelection(.enabled)
            Text(source.isOwnWords ? "本人原话" : "他人转述").font(.caption).foregroundStyle(.secondary)
            if let time = source.temporal_context, !time.isEmpty { Text(time).font(.caption).foregroundStyle(.secondary) }
            Button(app.playbackID == source.episode_id && app.isPlaying ? "停止播放" : "听原始录音") {
                if app.playbackID == source.episode_id && app.isPlaying { app.stopPlayback() }
                else { Task { await app.playOriginal(episodeID: source.episode_id) } }
            }.disabled(app.playbackLoading)
            Text("来源 \(source.id)").font(.caption2).foregroundStyle(.secondary)
        }
    }
}

private struct ReviewCandidateDetail: View {
    @ObservedObject var review: PersonReviewModel
    let candidate: ReviewCandidate
    private let scope: ReviewScope?
    @State private var relation = false
    init(review: PersonReviewModel, candidate: ReviewCandidate) {
        self.review = review; self.candidate = candidate; scope = review.scope
    }
    private var current: ReviewCandidate? { review.candidates.first { $0.id == candidate.id } }
    var body: some View {
        List {
            if let row = current, scope == review.scope {
                Section("情境化理解 · \(reviewStatus(row.status))") {
                    Text(row.statement).textSelection(.enabled)
                    if let context = row.context, !context.isEmpty { Text(context) }
                    Text("材料条数不代表独立事件数量；单次讲述不能直接当成稳定性格。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("支持原文") {
                    ForEach(review.sources.filter { row.evidence_ids.contains($0.id) }) { ReviewEvidenceCard(source: $0) }
                }
                Section("反例与限制") {
                    if row.counter_evidence_ids.isEmpty { Text("没有列出反例；这不代表不存在反例。") }
                    ForEach(review.sources.filter { row.counter_evidence_ids.contains($0.id) }) { ReviewEvidenceCard(source: $0) }
                }
                Section {
                    if row.status == "pending" {
                        Button("确认这项理解") { Task { _ = await review.decideCandidate(row, confirm: true) } }
                            .accessibilityIdentifier("review.confirmCandidate")
                        Button("关联已有理解") { relation = true }
                            .disabled(!review.candidates.contains { $0.canBeRelationTarget && $0.domain == row.domain && $0.kind == row.kind })
                    }
                    if ["pending", "confirmed"].contains(row.status) {
                        Button("只留原文，不采用这项理解", role: .destructive) { Task { _ = await review.decideCandidate(row, confirm: false) } }
                    }
                    Text("需要改写或重新分类时，可从原文新建观察；现有候选不支持直接改写。")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("模型 \(row.model_version) · 提示词 \(row.prompt_version)").font(.caption2).foregroundStyle(.secondary)
                }.disabled(review.isMutating || !review.isReady)
            } else { Text("资料或连接已变化，请返回后重新核对。") }
            if let error = review.errorMessage { Text(error).foregroundStyle(.red) }
        }
        .navigationTitle("核对人物理解")
        .sheet(isPresented: $relation) {
            NavigationStack { ReviewRelationEditor(review: review, candidate: candidate) }
        }
    }
}

private struct ReviewSourceDetail: View {
    @ObservedObject var review: PersonReviewModel
    let source: ReviewEvidence
    private let scope: ReviewScope?
    @State private var kind: String?
    init(review: PersonReviewModel, source: ReviewEvidence) { self.review = review; self.source = source; scope = review.scope }
    var body: some View {
        List {
            if scope == review.scope, let current = review.sources.first(where: { $0.id == source.id }) {
                Section("原文") { ReviewEvidenceCard(source: current) }
                Section("从这段原文整理") {
                    Button("新建情境观察") { kind = "observation" }
                    Button("选择为表达范例") { kind = "style" }.disabled(!current.isOwnWords)
                    Button("整理为故事") { kind = "story" }
                    Text("保存后进入待核对列表，不会直接成为已确认理解。")
                        .font(.caption).foregroundStyle(.secondary)
                }.disabled(review.isMutating || !review.isReady)
            } else { Text("此原文已不可用，请返回刷新。") }
        }.navigationTitle("查看原文")
            .sheet(isPresented: Binding(get: { kind != nil }, set: { if !$0 { kind = nil } })) {
                NavigationStack {
                    if let kind { ReviewRecordEditor(review: review, input: ReviewRecordInput(kind: kind, title: "", text: String(source.excerpt.prefix(1500)), evidenceIDs: [source.id], facets: [kind == "style" ? "EXPRESSION" : "EXPERIENCE"])) }
                }
            }
    }
}

private struct ReviewRecordDetail: View {
    @ObservedObject var review: PersonReviewModel
    let record: ReviewRecord
    private let scope: ReviewScope?
    @State private var editing = false
    init(review: PersonReviewModel, record: ReviewRecord) { self.review = review; self.record = record; scope = review.scope }
    var body: some View {
        List {
            if scope == review.scope, let row = review.records.first(where: { $0.id == record.id }) {
                Section("\(reviewKind(row.kind)) · \(reviewStatus(row.status))") {
                    Text(row.title).font(.headline)
                    Text(row.text).textSelection(.enabled)
                    Text(row.facets.compactMap { reviewFacets[$0] }.joined(separator: "、"))
                    if !row.time_text.isEmpty { Text("发生时间：\(row.time_text)") }
                    if !row.place_text.isEmpty { Text("地点：\(row.place_text)") }
                    if row.same_event { Text("本人确认归组后，这些讲述按同一事件处理。") }
                }
                Section("原文依据") {
                    ForEach(row.evidence) { ReviewEvidenceCard(source: $0) }
                    if !row.editable { Text("原文依据已变化，这条历史整理不能直接确认。") }
                }
                if row.editable {
                    Section {
                        Button("修改内容与分类") { editing = true }.accessibilityIdentifier("review.editRecord")
                        if row.status == "pending" {
                            Button("确认整理内容") { Task { _ = await review.decideRecord(row, confirm: true) } }
                                .accessibilityIdentifier("review.confirmRecord")
                        }
                        if ["pending", "confirmed"].contains(row.status) {
                            Button("只留原文，停用这条整理", role: .destructive) { Task { _ = await review.decideRecord(row, confirm: false) } }
                        }
                    }.disabled(review.isMutating || !review.isReady)
                }
                Section { Text("版本 \(row.revision) · 模型 \(row.model_version) · 提示词 \(row.prompt_version)").font(.caption) }
            } else { Text("资料或连接已变化，请返回后重新核对。") }
            if let error = review.errorMessage { Text(error).foregroundStyle(.red) }
        }.navigationTitle("核对整理内容")
            .sheet(isPresented: $editing) {
                NavigationStack {
                    if let row = review.records.first(where: { $0.id == record.id }) {
                        ReviewRecordEditor(review: review, input: ReviewRecordInput(row), recordID: row.id)
                    }
                }
            }
    }
}

private struct ReviewRecordEditor: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var review: PersonReviewModel
    @State var input: ReviewRecordInput
    var recordID: String?
    private let scope: ReviewScope?
    init(review: PersonReviewModel, input: ReviewRecordInput, recordID: String? = nil) {
        self.review = review; _input = State(initialValue: input); self.recordID = recordID; scope = review.scope
    }
    var body: some View {
        Form {
            Section("\(reviewKind(input.kind)) · 保存后待核对") {
                TextField("标题", text: $input.title).accessibilityIdentifier("review.editor.title")
                TextEditor(text: $input.text).frame(minHeight: 160).accessibilityIdentifier("review.editor.text")
                if ["style", "letter"].contains(input.kind) {
                    Text("请保留原文中的连续片段，不能改写、扩写或拼接。")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("分类 · 可多选") {
                ForEach(reviewFacetOrder, id: \.self) { facet in
                    Toggle(reviewFacets[facet]!, isOn: Binding(get: { input.facets.contains(facet) }, set: { enabled in
                        if enabled { if !input.facets.contains(facet) { input.facets.append(facet) } }
                        else { input.facets.removeAll { $0 == facet } }
                    })).accessibilityIdentifier("review.facet.\(facet)")
                }
            }
            Section("依据") {
                ForEach(review.sources.filter { input.evidence_ids.contains($0.id) }) { ReviewEvidenceCard(source: $0) }
            }
            if let message = input.validationMessage(sources: review.sources) { Text(message).font(.caption).foregroundStyle(.secondary) }
            if let error = review.errorMessage { Text(error).foregroundStyle(.red) }
            Button("保存为待核对") {
                Task { if scope == review.scope, await review.saveRecord(input, recordID: recordID) { dismiss() } }
            }.disabled(scope != review.scope || !review.isReady || review.isMutating || input.validationMessage(sources: review.sources) != nil)
                .accessibilityIdentifier("review.editor.save")
        }.navigationTitle(recordID == nil ? "从原文整理" : "修改整理内容")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } } }
            .onChange(of: review.scope) { _, _ in dismiss() }
    }
}

private struct ReviewStoryGrouping: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var review: PersonReviewModel
    @State private var selected = Set<String>()
    @State private var title = ""
    @State private var text = ""
    @State private var input: ReviewRecordInput?
    private let scope: ReviewScope?
    init(review: PersonReviewModel) { self.review = review; scope = review.scope }
    var body: some View {
        Form {
            Section {
                Text("仅选择确实在讲同一事件的原文。相同话题、同一人物，不一定是同一事件。保存后仍需确认。")
                TextField("故事标题", text: $title)
                TextField("说明这些讲述为何属于同一事件", text: $text, axis: .vertical)
            }
            Section("选择讲述") {
                ForEach(review.sources) { source in
                    Toggle(isOn: Binding(get: { selected.contains(source.id) }, set: { enabled in
                        if enabled { selected.insert(source.id) } else { selected.remove(source.id) }
                    })) { Text(source.excerpt).lineLimit(5) }
                }
            }
            Button("继续核对分类与原文") {
                var draft = ReviewRecordInput(kind: "story", title: title, text: text,
                                              evidenceIDs: review.sources.map(\.id).filter { selected.contains($0) }, facets: ["EXPERIENCE"])
                draft.same_event = true; input = draft
            }.disabled(scope != review.scope || !review.isReady || selected.count < 2 || title.isEmpty || text.isEmpty)
        }.navigationTitle("同一故事归组")
            .onChange(of: review.scope) { _, _ in dismiss() }
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } } }
            .sheet(isPresented: Binding(get: { input != nil }, set: { if !$0 { input = nil } })) {
                NavigationStack { if let input { ReviewRecordEditor(review: review, input: input) } }
            }
    }
}

private struct ReviewRelationEditor: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var review: PersonReviewModel
    let candidate: ReviewCandidate
    private let scope: ReviewScope?
    @State private var target = ""
    @State private var action = "SUPPORT"
    @State private var reason = ""
    @State private var time = ""
    init(review: PersonReviewModel, candidate: ReviewCandidate) { self.review = review; self.candidate = candidate; scope = review.scope }
    var body: some View {
        Form {
            Section("新理解") { Text(candidate.statement) }
            Picker("已有理解", selection: $target) {
                Text("请选择").tag("")
                ForEach(review.candidates.filter { $0.canBeRelationTarget && $0.domain == candidate.domain && $0.kind == candidate.kind }) {
                    Text($0.statement + ($0.status == "stale" ? "（需重新核对依据）" : "")).tag($0.id)
                }
            }
            Picker("关系", selection: $action) { ForEach(["SUPPORT", "CHANGE", "CONFLICT"], id: \.self) { Text(relationName($0)).tag($0) } }
            TextField("为什么这样关联", text: $reason, axis: .vertical)
            if action == "CHANGE" { TextField("何时发生变化（可写模糊时间）", text: $time) }
            Text("提交只是建议。再次核对新旧理解和依据，确认后才生效。")
            if let error = review.errorMessage { Text(error).foregroundStyle(.red) }
            Button("提交关联建议") {
                Task { if scope == review.scope, await review.proposeRelation(candidate: candidate, targetID: target, action: action, reason: reason, time: time) { dismiss() } }
            }.disabled(scope != review.scope || !review.isReady || review.isMutating || target.isEmpty || reason.isEmpty || (action == "CHANGE" && time.isEmpty))
        }.navigationTitle("关联已有理解")
            .onChange(of: review.scope) { _, _ in dismiss() }
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } } }
    }
}

private struct ReviewUpdateCard: View {
    @ObservedObject var review: PersonReviewModel
    let update: ReviewUpdate
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("\(relationName(update.action)) · \(reviewStatus(update.status))").font(.headline)
            if let target = review.candidates.first(where: { $0.id == update.target_candidate_id }) {
                NavigationLink("原理解：\(target.statement)") { ReviewCandidateDetail(review: review, candidate: target) }
            }
            if let new = review.candidates.first(where: { $0.id == update.candidate_id }) {
                NavigationLink("新理解：\(new.statement)") { ReviewCandidateDetail(review: review, candidate: new) }
            }
            Text(update.reason)
            if !update.time_text.isEmpty { Text("变化时间：\(update.time_text)") }
            if update.status == "pending" {
                Button("确认这次关联更新") { Task { _ = await review.decideUpdate(update, confirm: true) } }
                Button("不采用关联建议", role: .destructive) { Task { _ = await review.decideUpdate(update, confirm: false) } }
            }
        }.disabled(review.isMutating || !review.isReady)
    }
}

import SwiftUI

@MainActor
private func gardenOverview(_ workspace: MemoryGardenWorkspace, model: AppModel, fixture: GardenPreview?) -> ReviewOverview? {
    if let fixture { return fixture.overview }
    guard !model.isGuestMode, let pairing = model.pairing else { return nil }
    return workspace.currentOverview(for: pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
}

struct GardenNarrativePeoplePage: View {
    @EnvironmentObject private var model: AppModel
    @ObservedObject var workspace: MemoryGardenWorkspace
    let fixture: GardenPreview?
    var body: some View {
        ScrollView {
            GardenNarrativeBrowser(overview: gardenOverview(workspace, model: model, fixture: fixture),
                episodes: fixture?.episodes ?? model.episodes, facetsMode: false, query: "", workspace: workspace, fixture: fixture,
                initialView: .people).padding(20)
        }.background(RMColors.background).navigationTitle("故事里的人")
    }
}

struct GardenNarrativeBrowser: View {
    @EnvironmentObject private var model: AppModel
    let overview: ReviewOverview?
    let episodes: [EpisodeRecord]
    let facetsMode: Bool
    let query: String
    @ObservedObject var workspace: MemoryGardenWorkspace
    let fixture: GardenPreview?
    var initialView = GardenPersonView.life
    @State private var personView = GardenPersonView.life
    @State private var facet: GardenFacet?
    @State private var understandingIndex = 0
    @State private var showRecorder = false
    @State private var questionError: String?
    @State private var decidingQuestion = false
    @State private var showCreate = false
    private var records: [ReviewRecord] {
        GardenNarrativeProjection.records(overview, episodes: episodes, view: facetsMode ? nil : personView, facet: facet, query: query)
    }
    private var understandings: [GardenUnderstanding] {
        guard let overview, overview.role == "owner" else { return [] }
        return overview.understandings.filter { $0.isCurrent(sources: overview.source_evidence, episodes: episodes) }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if !understandings.isEmpty && !facetsMode {
                let selected = understandings[min(understandingIndex, understandings.count - 1)]
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("已确认的理解").font(.headline); Spacer()
                        Button { understandingIndex -= 1 } label: { Image(systemName: "chevron.left").frame(width: 40, height: 44) }.disabled(understandingIndex == 0).accessibilityLabel("上一条理解")
                        Text("\(understandingIndex + 1) / \(understandings.count)").font(.caption)
                        Button { understandingIndex += 1 } label: { Image(systemName: "chevron.right").frame(width: 40, height: 44) }.disabled(understandingIndex + 1 == understandings.count).accessibilityLabel("下一条理解")
                    }
                    Text(selected.statement).font(.body)
                    NavigationLink("查看情境与来源") { GardenUnderstandingDetail(id: selected.id, workspace: workspace, fixture: fixture) }
                }.padding(16).background(RMColors.surface, in: RoundedRectangle(cornerRadius: 18))
            }
            if !facetsMode {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 132))], spacing: 8) {
                    ForEach(GardenPersonView.allCases) { value in
                        Button(value.rawValue) { personView = value; facet = nil }.buttonStyle(.bordered)
                            .tint(personView == value ? RMColors.action : RMColors.secondaryText)
                            .accessibilityIdentifier("garden.person." + value.id)
                    }
                }
                if personView == .life {
                    Button(facet == .feelings ? "返回全部足迹" : "感受回看") { facet = facet == .feelings ? nil : .feelings }
                }
            }
            if facetsMode && facet == nil && query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                ForEach(GardenFacet.allCases) { value in
                    let samples = GardenNarrativeProjection.records(overview, episodes: episodes, facet: value)
                    Button { facet = value } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack { Label(value.title, systemImage: value.symbol).font(.headline); Spacer(); Image(systemName: "chevron.right") }
                            Text(samples.first?.text ?? "还没聊到").font(.subheadline).lineLimit(2).foregroundStyle(.secondary)
                            if !samples.isEmpty { Text("\(samples.count) 段内容").font(.caption) }
                        }.multilineTextAlignment(.leading).frame(maxWidth: .infinity, alignment: .leading).padding(18)
                            .background(RMColors.surface, in: RoundedRectangle(cornerRadius: 20))
                    }.buttonStyle(.plain).accessibilityIdentifier("garden.facet." + value.rawValue)
                }
            } else {
                if facetsMode, let facet {
                    HStack { Button("全部侧面") { self.facet = nil }; Spacer(); Text(facet.title).font(.headline) }
                }
                if records.isEmpty {
                    ContentUnavailableView("还没有已核对的相关内容", systemImage: "leaf", description: Text("新的讲述整理后，可在“整理与核对”确认内容。"))
                }
                ForEach(records) { row in
                    NavigationLink { GardenNarrativeRecordDetail(id: row.id, workspace: workspace, fixture: fixture) } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(GardenNarrativeProjection.kindTitle(row.kind)).font(.caption).foregroundStyle(RMColors.action)
                            Text(row.title).font(.system(.title3, design: .serif))
                            Text(row.text).font(.body).foregroundStyle(.secondary).lineLimit(5)
                            Text("\(Set(row.evidence.map(\.episode_id)).count) 段来源 · 本人已核对").font(.caption).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
                            .background(RMColors.surface, in: RoundedRectangle(cornerRadius: 20))
                    }.buttonStyle(.plain).accessibilityIdentifier("garden.record." + row.id)
                }
            }
            NavigationLink("整理与核对") { PersonReviewView(review: model.personReview) }.buttonStyle(.bordered)
                .accessibilityIdentifier("garden.review")
            Button("从原文组织故事 / 留下原话") { showCreate = true }
                .disabled(fixture != nil || model.recordingStartBlocked || overview?.source_evidence.isEmpty != false)
                .accessibilityIdentifier("garden.create")
            if let question = overview?.next_question, overview?.role == "owner",
               Set(question.evidence_ids).isSubset(of: Set(overview?.source_evidence.map(\.id) ?? [])) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("如果愿意，再聊一点").font(.headline)
                    Text(question.text); Text(question.reason).font(.footnote).foregroundStyle(.secondary)
                    HStack {
                        Button("就聊这个") { showRecorder = true }.disabled(model.recordingStartBlocked)
                        Button("稍后") { Task { await decideQuestion(question, action: "snoozed") } }
                        Button("跳过") { Task { await decideQuestion(question, action: "declined") } }
                    }.disabled(decidingQuestion || fixture != nil || model.isRecording || model.realtimeVoice.isActive)
                    if let questionError { Text(questionError).font(.footnote).foregroundStyle(.red) }
                }.padding(18).background(RMColors.surface, in: RoundedRectangle(cornerRadius: 20))
            }
        }.onAppear { personView = initialView }
            .onChange(of: overview?.subject_id) { _, _ in personView = initialView; facet = nil; understandingIndex = 0; showRecorder = false }
            .onChange(of: understandings.map(\.id)) { _, _ in understandingIndex = 0 }
            .fullScreenCover(isPresented: $showRecorder) { RecorderView(question: nil, calibration: nil) }
            .sheet(isPresented: $showCreate) {
                if let overview {
                    GardenNarrativeEditor(input: ReviewRecordInput(kind: "story", title: "", text: "", evidenceIDs: [], facets: ["EXPERIENCE"]),
                        sources: overview.source_evidence, split: false) { input in
                            guard !model.isGuestMode, let pairing = model.pairing, workspace.scope == ReviewScope(pairing),
                                  !model.isRecording, !model.realtimeVoice.isActive, !model.isBusy else { return "当前空间或录音状态已变化，请稍后重试。" }
                            let scope = ReviewScope(pairing)
                            await model.personReview.reload()
                            guard model.personReview.scope == scope, model.personReview.isReady else { return "原文暂不可用，请返回花园刷新。" }
                            let saved = await model.personReview.saveRecord(input)
                            guard model.pairing.map(ReviewScope.init) == scope, !model.isGuestMode else { return "本人空间已变化。" }
                            guard saved else { return model.personReview.errorMessage ?? "保存未完成。" }
                            await model.refresh()
                            await workspace.reload(pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
                            return nil
                        }
                }
            }
    }
    private func decideQuestion(_ question: GardenNextQuestion, action: String) async {
        guard !model.isGuestMode, let pairing = model.pairing, !decidingQuestion else { return }
        let scope = ReviewScope(pairing); decidingQuestion = true; questionError = nil
        defer { decidingQuestion = false }
        do {
            let client = try APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token)
            let body = try JSONSerialization.data(withJSONObject: ["id": question.id, "action": action])
            try await client.reviewWrite(subject: pairing.subjectID, suffix: "narrative/next-question", body: body)
            guard model.pairing.map(ReviewScope.init) == scope, !model.isGuestMode else { return }
            await workspace.reload(pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)
        } catch { if model.pairing.map(ReviewScope.init) == scope { questionError = "未能保存选择，请稍后重试。" } }
    }
}

struct GardenUnderstandingDetail: View {
    @EnvironmentObject private var model: AppModel
    let id: String
    @ObservedObject var workspace: MemoryGardenWorkspace
    let fixture: GardenPreview?
    var body: some View {
        List {
            let overview = gardenOverview(workspace, model: model, fixture: fixture)
            if let item = overview?.understandings.first(where: { $0.id == id && $0.isCurrent(sources: overview?.source_evidence ?? [], episodes: fixture?.episodes ?? model.episodes) }) {
                Section("本人确认的情境化理解") { Text(item.statement).font(.title3); if let context = item.context { Text("适用情境：" + context) } }
                sources(item.evidence, title: "支持这项理解的依据")
                sources(item.counter_evidence, title: "例外与反例")
                Section { Text("模型版本：" + item.model_version).font(.caption) }
            } else { Text("理解或来源已变化，请返回重新核对。") }
        }.navigationTitle("情境与来源").navigationBarTitleDisplayMode(.inline)
    }
    private func sources(_ sources: [ReviewEvidence], title: String) -> some View {
        Section(title) {
            ForEach(sources) { source in
                Text(source.excerpt)
                NavigationLink("查看来源故事") { GardenEpisodeSourceView(episodeID: source.episode_id, scope: model.pairing.map(ReviewScope.init)) }
            }
        }
    }
}

struct GardenEpisodeSourceView: View {
    @EnvironmentObject private var model: AppModel
    let episodeID: String
    let scope: ReviewScope?
    var body: some View {
        List {
            if !model.isGuestMode, scope != nil, model.pairing.map(ReviewScope.init) == scope,
               let episode = model.episodes.first(where: { $0.id == episodeID && $0.status == "ready" }) {
                Section { Text(MemoryGardenProjection.recordingDate(episode.recorded_at)).font(.caption); Text(episode.transcript ?? "核对文字暂未返回。") }
                if episode.source != "IOS_TEXT" { Section("完整原音") { OriginalPlayer(episodeID: episodeID).disabled(model.isRecording || model.realtimeVoice.isActive) } }
                Section("来源记忆") {
                    ForEach(model.memories.filter { $0.episode_id == episodeID }) { memory in
                        NavigationLink { GardenCurrentMemoryDetail(id: memory.id, scope: scope) } label: { Text(memory.content) }
                    }
                }
            } else { Text("来源或空间已变化，请返回花园刷新。") }
        }.navigationTitle("来源讲述").navigationBarTitleDisplayMode(.inline)
    }
}

struct GardenRelatedResults: View {
    @EnvironmentObject private var model: AppModel
    let query: String
    let fixture: GardenPreview?
    var body: some View {
        if fixture == nil, !model.isGuestMode, model.memorySearchQuery == query.trimmingCharacters(in: .whitespacesAndNewlines), model.memorySearchCompleted {
            VStack(alignment: .leading, spacing: 16) {
                Text("相关内容").font(.headline)
                if model.memorySearchResults.isEmpty { Text("暂未找到更多相关内容").font(.subheadline).foregroundStyle(.secondary) }
                ForEach(model.memorySearchResults) { hit in
                    let ready = Set(model.episodes.filter { $0.status == "ready" }.map(\.id))
                    if !hit.evidence.isEmpty && hit.evidence.allSatisfy({ ready.contains($0.episode_id) }) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(hit.statement)
                            ForEach(hit.evidence) { source in
                                Text(source.excerpt ?? "原文暂未返回").font(.subheadline).foregroundStyle(.secondary)
                                NavigationLink("打开来源") { GardenEpisodeSourceView(episodeID: source.episode_id, scope: model.pairing.map(ReviewScope.init)) }
                            }
                        }.padding(16).background(RMColors.surface, in: RoundedRectangle(cornerRadius: 18))
                    }
                }
            }
        }
    }
}

import SwiftUI
import CryptoKit

enum GardenSurfaceMode: String, CaseIterable, Identifiable {
    case meadow = "花田", list = "列表", timeline = "时间线", person = "了解这个人", facets = "记忆侧面"
    var id: String { rawValue }
}

enum GardenScene: String, CaseIterable, Identifiable {
    case meadow, lake, forest, coast, night, path
    var id: String { rawValue }
    var title: String {
        switch self { case .meadow: "草地"; case .lake: "湖畔"; case .forest: "林间"; case .coast: "海边"; case .night: "夜色"; case .path: "花径" }
    }
    var asset: String { "GardenScene" + rawValue.capitalized }
}

struct GardenSceneBackground: View {
    let scene: GardenScene
    var body: some View {
        GeometryReader { geometry in
            Image(scene.asset).resizable().scaledToFill().frame(width: geometry.size.width, height: geometry.size.height).clipped()
                .overlay(LinearGradient(colors: [.black.opacity(0.32), .black.opacity(0.1), .black.opacity(0.5)], startPoint: .top, endPoint: .bottom))
        }.ignoresSafeArea().accessibilityHidden(true).allowsHitTesting(false)
    }
}

struct GardenScenePicker: View {
    @Environment(\.dynamicTypeSize) private var typeSize
    @Binding var scene: GardenScene
    let close: () -> Void
    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: typeSize.isAccessibilitySize ? 1 : 2), spacing: 16) {
                    ForEach(GardenScene.allCases) { choice in
                        Button {
                            scene = choice; close()
                        } label: {
                            GeometryReader { geometry in
                                Image(choice.asset).resizable().scaledToFill()
                                    .frame(width: geometry.size.width, height: 128).clipped()
                                    .overlay(alignment: .bottomLeading) {
                                        HStack { Text(choice.title); Spacer(); if choice == scene { Image(systemName: "checkmark.circle.fill") } }
                                            .font(.headline).foregroundStyle(.white).padding(14).background(.black.opacity(0.48))
                                    }
                            }.frame(height: 128).clipShape(RoundedRectangle(cornerRadius: 18))
                                .contentShape(RoundedRectangle(cornerRadius: 18))
                        }.buttonStyle(.plain).accessibilityLabel(choice.title)
                            .accessibilityAddTraits(choice == scene ? .isSelected : [])
                            .accessibilityIdentifier("garden.scene." + choice.rawValue)
                    }
                }.padding(20)
                Text("选择喜欢的地方重温往事。场景只保存在这台手机。")
                    .font(.footnote).foregroundStyle(.secondary).padding(.horizontal, 20)
            }.navigationTitle("换一处花园").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("关闭", action: close) } }
        }
    }
}

struct GardenMeadow<Destination: View>: View {
    @Environment(\.dynamicTypeSize) private var typeSize
    let entries: [GardenEntry]
    let destination: (GardenEntry) -> Destination
    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: typeSize.isAccessibilitySize ? 1 : 2), alignment: .center, spacing: 22) {
            ForEach(entries) { entry in
                NavigationLink { destination(entry) } label: {
                    VStack(spacing: 2) {
                        Image(flowerAsset(entry.id)).resizable().scaledToFit().frame(height: 146)
                            .shadow(color: .black.opacity(0.18), radius: 12, y: 6).accessibilityHidden(true)
                        Text(entry.title).font(.system(.headline, design: .serif)).lineLimit(typeSize.isAccessibilitySize ? nil : 3)
                            .multilineTextAlignment(.center).foregroundStyle(.white).padding(.horizontal, 6)
                        Text("\(entry.memories.count) 个内容入口").font(.caption).foregroundStyle(.white.opacity(0.84))
                    }.frame(maxWidth: .infinity, minHeight: 218).padding(10)
                        .background(.black.opacity(0.22), in: RoundedRectangle(cornerRadius: 24))
                }.buttonStyle(RMQuietPressStyle()).accessibilityIdentifier("garden.entry." + entry.id)
            }
        }.accessibilityIdentifier("garden.meadow")
    }
    private func flowerAsset(_ id: String) -> String {
        let assets = ["GardenFlowerFront", "GardenFlowerSide", "GardenFlowerCupped"]
        let index = Int(Array(SHA256.hash(data: Data(id.utf8))).first ?? 0) % assets.count
        return assets[index]
    }
}

struct GardenPetalPages: View {
    @Environment(\.dynamicTypeSize) private var typeSize
    let entry: GardenEntry
    let scope: ReviewScope?
    @ObservedObject var workspace: MemoryGardenWorkspace
    var fixture: GardenPreview? = nil
    @State private var page = 0
    @State private var reading: GardenReadingSelection?
    private var pages: [[MemoryRecord]] { stride(from: 0, to: entry.memories.count, by: 5).map { Array(entry.memories[$0..<min($0 + 5, entry.memories.count)]) } }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("一片花瓣，一段值得停留的瞬间。").font(.subheadline).foregroundStyle(.secondary)
            if !entry.memories.isEmpty {
                let shown = pages[min(page, max(0, pages.count - 1))]
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: typeSize.isAccessibilitySize ? 1 : 2), spacing: 12) {
                    ForEach(shown) { memory in
                        Button { reading = GardenReadingSelection(id: memory.id) } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                Image("GardenFlowerFront").resizable().scaledToFit().frame(height: 72).frame(maxWidth: .infinity)
                                Text(memory.content).font(.body).lineLimit(typeSize.isAccessibilitySize ? nil : 4).multilineTextAlignment(.leading)
                                Text(sourceLabel(memory.source_type)).font(.caption).foregroundStyle(.secondary)
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
                                .background(RMColors.surface, in: RoundedRectangle(cornerRadius: 24))
                        }.buttonStyle(.plain).accessibilityIdentifier("garden.petal." + memory.id)
                    }
                }
                if pages.count > 1 {
                    HStack {
                        Button("上一组") { page -= 1 }.disabled(page == 0)
                        Spacer(); Text("\(page + 1) / \(pages.count) 组").font(.caption); Spacer()
                        Button("下一组") { page += 1 }.disabled(page + 1 >= pages.count)
                    }.accessibilityIdentifier("garden.petalPages")
                }
            }
        }.onChange(of: entry.memories.map(\.id)) { _, _ in page = 0; reading = nil }
            .fullScreenCover(item: $reading) { selected in
                GardenSourceReader(memoryID: selected.id, scope: scope, workspace: workspace, fixture: fixture)
            }
    }
}

private struct GardenReadingSelection: Identifiable { let id: String }

/// One fixed transport remains reachable even when a document has many citations.
struct GardenSourceReader: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let memoryID: String
    let scope: ReviewScope?
    @ObservedObject var workspace: MemoryGardenWorkspace
    var fixture: GardenPreview? = nil
    @State private var selectedSource = ""
    private var memory: MemoryRecord? {
        if let fixture, scope == ReviewScope(fixture.pairing) {
            return fixture.entries.flatMap(\.memories).first { $0.id == memoryID &&
                GardenMemorySourceProjection.isCurrent($0, sources: fixture.overview?.source_evidence, episodes: fixture.episodes) }
        }
        guard !model.isGuestMode, let pairing = model.pairing, scope != nil, ReviewScope(pairing) == scope,
              workspace.canDisplayEntries(for: pairing, revision: model.memoryContentRevision, memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion) else { return nil }
        let sources = workspace.currentOverview(for: pairing, revision: model.memoryContentRevision,
            memoryIDs: model.memories.map(\.id), modelVersion: model.modelVersion)?.source_evidence
        return model.memories.first { memory in
            memory.id == memoryID && GardenMemorySourceProjection.isCurrent(memory, sources: sources, episodes: model.episodes)
        }
    }
    private var originals: [EpisodeRecord] {
        guard let memory else { return [] }
        let ids = Set([memory.episode_id] + memory.evidence.map(\.source_ref))
        return model.episodes.filter { ids.contains($0.id) && $0.status == "ready" && $0.source != "IOS_TEXT" }.sorted { $0.id < $1.id }
    }
    var body: some View {
        NavigationStack {
            Group {
                if let memory {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            Label(sourceLabel(memory.source_type), systemImage: "leaf").font(.caption).foregroundStyle(.secondary)
                            Text(memory.content).font(.system(.title3, design: .serif)).lineSpacing(9).textSelection(.enabled)
                            Divider(); Text("它的来处").font(.headline)
                            ForEach(Array(memory.evidence.enumerated()), id: \.element.id) { index, evidence in
                                VStack(alignment: .leading, spacing: 10) {
                                    Text("\(index + 1) · " + sourceLabel(evidence.source_type)).font(.caption).foregroundStyle(.secondary)
                                    Text(evidence.excerpt ?? "原文暂未返回，请刷新来源。")
                                        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                        .background(RMColors.surface, in: RoundedRectangle(cornerRadius: 16))
                                }
                            }
                            Text("依据来自核对文字。没有可靠时间对齐时，播放完整原音。书面补充不属于录音原话。")
                                .font(.footnote).foregroundStyle(.secondary)
                            NavigationLink("查看来源、纠正或删除记忆") { GardenCurrentMemoryDetail(id: memoryID, scope: scope, fixture: fixture) }
                            if let error = model.errorMessage { Text(error).font(.footnote).foregroundStyle(.red) }
                        }.padding(24).frame(maxWidth: RMMetrics.maximumReadingWidth).frame(maxWidth: .infinity)
                    }.accessibilityIdentifier("garden.reader.document")
                        .safeAreaInset(edge: .bottom) { transport }
                } else { ContentUnavailableView("来源已变化", systemImage: "leaf", description: Text("请返回花园重新核对。")) }
            }.background(RMColors.background).navigationTitle("一片记忆").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("返回花朵") { dismiss() } } }
        }.onAppear { selectedSource = originals.first?.id ?? "" }
            .onChange(of: originals.map(\.id)) { _, ids in
                guard !(workspace.isLoading && ids.isEmpty) else { return }
                if !ids.contains(selectedSource) {
                    if model.playbackID == selectedSource { model.stopPlayback() }
                    selectedSource = ids.first ?? ""
                }
            }
            .onChange(of: memory?.id) { _, current in
                if current == nil, !workspace.isLoading, model.playbackID == selectedSource { model.stopPlayback() }
            }
            .onChange(of: workspace.isLoading) { _, loading in
                if !loading, memory == nil, model.playbackID == selectedSource { model.stopPlayback() }
            }
    }
    @ViewBuilder private var transport: some View {
        if !originals.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                if originals.count > 1 {
                    Picker("选择原音", selection: $selectedSource) {
                        ForEach(Array(originals.enumerated()), id: \.element.id) { index, episode in
                            Text("原音 \(index + 1) · " + MemoryGardenProjection.recordingDate(episode.recorded_at)).tag(episode.id)
                        }
                    }.pickerStyle(.menu).accessibilityIdentifier("garden.reader.source")
                        .onChange(of: selectedSource) { old, new in
                            if old != new {
                                if model.playbackLoading { model.stopPlayback() }
                                else if model.playbackID == old, model.isPlaying { model.toggleCurrentPlayback() }
                            }
                        }
                }
                OriginalPlayer(episodeID: selectedSource).accessibilityIdentifier("garden.reader.player")
                    .disabled(model.isRecording || model.realtimeVoice.isActive || model.isSpeakerRecording)
            }.padding(16).background(.regularMaterial)
        }
    }
}

struct GardenMiniPlayer: View {
    @EnvironmentObject private var model: AppModel
    let allowedEpisodeIDs: Set<String>
    var body: some View {
        if let id = model.playbackID, allowedEpisodeIDs.contains(id), !model.isGuestMode {
            HStack {
                Button { model.toggleCurrentPlayback() } label: {
                    Image(systemName: model.isPlaying ? "pause.fill" : "play.fill").frame(width: 48, height: 48)
                }.accessibilityLabel(model.isPlaying ? "暂停原音" : "继续播放原音")
                VStack(alignment: .leading) {
                    Text(model.playbackLoading ? "正在准备原音…" : model.isPlaying ? "正在听原音" : "原音已暂停").font(.subheadline)
                    Text("\(Int(model.playbackPosition)) / \(Int(model.playbackDuration)) 秒").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button { model.stopPlayback() } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }.accessibilityLabel("停止播放原音")
            }.padding(.horizontal, 12).background(.regularMaterial).accessibilityIdentifier("garden.miniPlayer")
        }
    }
}

import SwiftUI
import AVFoundation
import UIKit

enum Ink {
    static let paper = RMColors.background
    static let cream = RMColors.surface
    static let text = RMColors.text
    static let muted = RMColors.secondaryText
    static let coral = RMColors.action
    static let peach = RMColors.floralSurface
    static let olive = RMColors.success
    static let onPrimary = RMColors.onAction
}

private struct AtmosphereBackground: View {
    var body: some View {
        RMColors.background.allowsHitTesting(false).accessibilityHidden(true)
    }
}

func statusLabel(_ state: String) -> String {
    switch state {
    case "uploaded": return "原音已保存"
    case "transcribing": return "正在转成文字"
    case "reviewing": return "待核对文字"
    case "extracting", "modeling": return "正在整理记忆"
    case "ready": return "已整理"
    case "failed": return "处理未完成，可重试"
    default: return state
    }
}

func sourceLabel(_ source: String) -> String {
    switch source {
    case "SUBJECT": return "本人叙述"
    case "THIRD_PARTY": return "他人提供"
    case "AI_INFERENCE": return "AI 推测"
    default: return "来源待核对"
    }
}

private extension View {
    func journalCard() -> some View {
        rmCardSurface()
    }
}

private struct Eyebrow: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.system(.subheadline, design: .default).weight(.regular))
            .foregroundStyle(Ink.muted)
    }
}



enum BrandTreatment { case automatic, material, flat, monochrome }

/// Import mark-material-1024.png into an Image Set and pass that asset's name.
/// This is a static brand image, never a microphone or processing indicator.
struct RememberMeBrand: View {
    var size: CGFloat = 48
    var treatment: BrandTreatment = .automatic
    var materialAsset: String? = nil
    var bundle: Bundle? = nil
    var monochromeColor: Color = .primary
    var label: String? = nil

    private var dimension: CGFloat { max(16, size) }
    private var useMaterial: Bool {
        materialAsset != nil && (treatment == .material || (treatment == .automatic && dimension >= 64))
    }
    var body: some View {
        Group {
            if useMaterial, let asset = materialAsset {
                Image(asset, bundle: bundle).resizable().scaledToFit()
            } else {
                Canvas { context, canvas in
                    let mono = treatment == .monochrome
                    let blue = RMColors.flowerMark
                    var petal = Path()
                    petal.move(to: CGPoint(x: 128, y: 125))
                    petal.addCurve(to: CGPoint(x: 88, y: 71), control1: CGPoint(x: 111, y: 119), control2: CGPoint(x: 91, y: 96))
                    petal.addCurve(to: CGPoint(x: 122, y: 22), control1: CGPoint(x: 85, y: 45), control2: CGPoint(x: 98, y: 23))
                    petal.addCurve(to: CGPoint(x: 166, y: 70), control1: CGPoint(x: 148, y: 20), control2: CGPoint(x: 168, y: 43))
                    petal.addCurve(to: CGPoint(x: 132, y: 125), control1: CGPoint(x: 164, y: 94), control2: CGPoint(x: 145, y: 118))
                    petal.closeSubpath()
                    context.scaleBy(x: canvas.width / 256, y: canvas.height / 256)
                    for i in 0..<5 {
                        var layer = context
                        layer.translateBy(x: 128, y: 128)
                        layer.rotate(by: .degrees(Double(i) * 72))
                        layer.translateBy(x: -128, y: -128)
                        layer.fill(petal, with: .color(mono ? monochromeColor : blue))
                    }
                    let r: CGFloat = mono ? 9 : 12
                    let heart = Path(ellipseIn: CGRect(x: 128-r, y: 128-r, width: 2*r, height: 2*r))
                    context.fill(heart, with: .color(mono ? monochromeColor : RMColors.flowerMarkCenter))
                }
            }
        }
        .frame(width: dimension, height: dimension)
        .accessibilityLabel(Text(label ?? ""))
        .accessibilityHidden(label == nil)
    }
}

struct ActionButton: View {
    let title: String
    let icon: String
    var fill: Color = Ink.coral
    var isLoading = false
    let action: () -> Void
    var body: some View {
        RMButton(title: title, icon: icon, isLoading: isLoading, fill: fill, action: action)
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        Group {
            if model.isGuestMode { GuestAccessTabs(guest: model.guestAccess) }
            else { SimpleFlowTabs() }
        }
        .tint(Ink.coral)
        .sheet(isPresented: $model.showConnection) {
            NavigationStack {
                ServiceConnectionView().toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("关闭") { model.showConnection = false }
                    }
                }
            }
        }
        .alert("需要留意", isPresented: Binding(
            get: { model.errorMessage != nil && !model.isRecorderPresented },
            set: { if !$0 && !model.isRecorderPresented { model.errorMessage = nil } }
        )) {
            Button("知道了") { model.errorMessage = nil }
            if model.errorMessage?.contains("麦克风权限") == true {
                Button("前往设置") {
                    if let url = URL(string: UIApplication.openSettingsURLString) {
                        UIApplication.shared.open(url)
                    }
                }
            }
        } message: { Text(model.errorMessage ?? "") }
    }
}

/// The everyday iOS route: capture, review, read memories, ask the Twin.
/// Existing review/voice implementations stay in source without unfinished
/// product entries in this route.
struct SimpleFlowTabs: View {
    @EnvironmentObject private var model: AppModel
    @State private var selection = 0
    var body: some View {
        RMTabBar(selection: $selection) {
            NavigationStack { SimpleRecordingHome(selection: $selection) }
                .tabItem { Label("录音", systemImage: "mic") }.tag(0)
            NavigationStack { MemoryGardenHome() }
                .tabItem { Label("记忆", systemImage: "books.vertical") }.tag(1)
            NavigationStack { TwinView() }
                .tabItem { Label("孪生", systemImage: "bubble.left.and.bubble.right") }.tag(2)
            NavigationStack { SimpleSettingsHome() }
                .tabItem { Label("我的", systemImage: "person.crop.circle") }.tag(3)
        }
        .onChange(of: selection) { _, _ in RMKeyboard.dismiss() }
        .fullScreenCover(isPresented: $model.showActiveRecording) {
            RecorderView(question: nil, calibration: nil, simplified: true)
        }
    }
}

private struct SimpleRecordingHome: View {
    @EnvironmentObject private var model: AppModel
    @Binding var selection: Int
    private enum RecordingPresentation: String, Identifiable {
        case new
        var id: String { rawValue }
    }
    @State private var recordingPresentation: RecordingPresentation?
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: RMSpacing.lg) {
                VStack(spacing: RMSpacing.sm) {
                    ForgetMeNotSprig().frame(width: RMMetrics.heroFlower, height: RMMetrics.heroFlower)
                    Text("勿忘我").font(RMTypography.title).foregroundStyle(RMColors.text)
                }.frame(maxWidth: .infinity).padding(.vertical, RMSpacing.sm)
                ActionButton(title: model.isRecording ? "返回正在录音" : "开始录音", icon: "mic.fill") {
                    if model.isRecording { recordingPresentation = .new; return }
                    guard model.prepareNewRecording() else { return }
                    model.isRecorderPresented = true
                    recordingPresentation = .new
                }.disabled(model.recordingStartBlocked && !model.isRecording)
                    .accessibilityIdentifier("flow.record")
                HStack(alignment: .top, spacing: RMSpacing.sm) {
                    NavigationLink { MyRecordingsView() } label: {
                        recordingShortcut("我的录音", icon: "waveform", detail: "录音与对话")
                    }.accessibilityIdentifier("flow.myRecordings")
                        .accessibilityLabel("我的录音").accessibilityHint("查看录音与对话")
                    NavigationLink { DeviceConnectionsView(devices: model.devices) } label: {
                        recordingShortcut("蓝牙连接", icon: "dot.radiowaves.left.and.right", detail: "录音豆与耳机")
                    }.accessibilityIdentifier("flow.devices")
                        .accessibilityLabel("蓝牙连接").accessibilityHint("连接录音豆与耳机，查看当前状态")
                }.buttonStyle(.plain)
                if let record = model.latestCaptureDraft { CaptureDraftCard(record: record) }
                CaptureQueueSummary()
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("--uitest-live-activity") {
                    Text(model.liveActivityPreviewStatus).accessibilityIdentifier("activity.preview.status")
                    Button("结束界面预览") { model.endLiveActivityPreview() }.accessibilityIdentifier("activity.preview.end")
                }
                #endif
            }.padding(RMSpacing.page).frame(maxWidth: RMMetrics.maximumReadingWidth)
        }
        .background(Ink.paper.ignoresSafeArea()).navigationTitle("录音").navigationBarTitleDisplayMode(.inline)
        .rmDismissibleKeyboard()
        .refreshable { await model.refresh() }
        .task(id: model.pairing.map(RecordingOwner.init)) {
            while !Task.isCancelled {
                model.processDeviceRecordingQueue()
                await model.refreshCaptureDrafts()
                do { try await Task.sleep(for: .seconds(4)) } catch { return }
            }
        }
        .fullScreenCover(item: $recordingPresentation) { presentation in
            RecorderView(question: nil, calibration: nil, simplified: true, startImmediately: presentation == .new,
                         onShowMemories: { selection = 1 })
        }
    }
    private func recordingShortcut(_ title: String, icon: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: RMSpacing.sm) {
            Image(systemName: icon).font(.title3).foregroundStyle(RMColors.action)
            Text(title).font(RMTypography.heading).foregroundStyle(RMColors.text)
            Text(detail).font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
        }
        .frame(maxWidth: .infinity, minHeight: 94, alignment: .leading)
        .padding(RMSpacing.md).rmCardSurface()
        .accessibilityElement(children: .combine)
    }
}

private enum RecordingDeletionTarget {
    case local(LocalRecording), remote(EpisodeRecord), dialogue(DialogueMaterial), group(LocalSpeakerRecording), conversation(HistoricalChatTurn)
    var title: String {
        if case .conversation = self { return "删除这段对话？" }
        return "删除这段录音？"
    }
    var message: String {
        switch self {
        case .local(let record) where record.episodeID == nil:
            return "将删除手机中的这段原音和转写，无法恢复。"
        case .local, .remote:
            return "将删除这段原音、转写和由它生成的记忆，并更新记忆花园与人物模型，无法恢复。"
        case .dialogue:
            return "将删除这段对话资料及由它生成的记忆；独立的聊天记录会保留。"
        case .group:
            return "将删除这段多人录音及其识别结果，无法恢复。"
        case .conversation:
            return "将删除这次问答、生成的声音及相关聊天检索资料，无法恢复。已单独保存的录音和原话资料仍保留，可在本页分别删除。"
        }
    }
}

private extension View {
    func recordingDeleteAction(disabled: Bool, action: @escaping () -> Void) -> some View {
        self.swipeActions(edge: .trailing, allowsFullSwipe: false) {
            Button("删除", systemImage: "trash", role: .destructive, action: action).disabled(disabled)
        }
        .contextMenu { Button("删除", systemImage: "trash", role: .destructive, action: action).disabled(disabled) }
        .accessibilityAction(named: "删除") { if !disabled { action() } }
    }
}

private struct MyRecordingsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var resumeRecording = false
    @State private var pendingDeletion: RecordingDeletionTarget?
    @State private var deletionOwner: RecordingOwner?
    @StateObject private var groupArchive = SpeakerLocalArchive()
    @State private var groupRecording: LocalSpeakerRecording?
    @State private var showGroupRecording = false
    private var unmatchedEpisodes: [EpisodeRecord] {
        let localIDs = Set(model.visibleLocalRecordings.compactMap(\.episodeID))
        return model.episodes.filter { $0.capture_origin != "natural_dialogue" && !localIDs.contains($0.id) }
    }
    var body: some View {
        List {
            if model.draft != nil {
                Button("继续查看上一段") { model.isRecorderPresented = true; resumeRecording = true }
                    .disabled(model.connectionChangeBlocked)
            }
            if model.visibleLocalRecordings.isEmpty && unmatchedEpisodes.isEmpty && model.visibleDialogueMaterials.isEmpty && model.visibleTwinArchive.isEmpty && groupArchive.visible(to: model.pairing).isEmpty {
                Text("还没有录音或保存的对话原话").font(RMTypography.detail).foregroundStyle(RMColors.secondaryText)
            }
            ForEach(model.visibleLocalRecordings) { record in
                NavigationLink { LocalRecordingDetailView(recordingID: record.id, simplified: true) } label: {
                    LocalRecordingRow(record: record)
                }
                .accessibilityIdentifier("recordings.local." + record.id)
                .recordingDeleteAction(disabled: model.connectionChangeBlocked || model.deviceUploadingRecordingID == record.id) { requestDeletion(.local(record)) }
            }
            ForEach(unmatchedEpisodes) { episode in
                NavigationLink { EpisodeDetailView(initial: episode) } label: { EpisodeRow(episode: episode) }
                    .accessibilityIdentifier("recordings.remote." + episode.id)
                    .recordingDeleteAction(disabled: model.connectionChangeBlocked) { requestDeletion(.remote(episode)) }
            }
            if let pairing = model.pairing, !model.visibleDialogueMaterials.isEmpty {
                Section {
                    ForEach(model.visibleDialogueMaterials) { material in
                        NavigationLink { DialogueMaterialView(material: material, owner: RecordingOwner(pairing)) } label: {
                            VStack(alignment: .leading, spacing: RMSpacing.xs) {
                                Text(material.text).font(RMTypography.detail).lineLimit(2)
                                Text(material.recorded_at.prefix(10)).font(RMTypography.caption).foregroundStyle(Ink.muted)
                                Text(material.status == "pending" ? "可以稍后核对" : "已保存").font(RMTypography.caption).foregroundStyle(Ink.muted)
                            }
                        }
                        .accessibilityIdentifier("recordings.dialogue." + material.id)
                        .recordingDeleteAction(disabled: model.connectionChangeBlocked) { requestDeletion(.dialogue(material)) }
                    }
                } header: { Text("与 TwinAgent 对话时记下的原话") }
                  footer: { Text("保留你的原话与可用原音。左滑可以删除这段资料。") }
            }
            if model.cloudConsentID != nil || !model.visibleTwinArchive.isEmpty {
                Section {
                    ForEach(model.visibleTwinArchive) { turn in
                        NavigationLink { TwinArchiveTurnView(turnID: turn.id, owner: model.pairing.map(RecordingOwner.init)) } label: {
                            VStack(alignment: .leading, spacing: RMSpacing.xs) {
                                Label(turn.question, systemImage: "bubble.left.and.bubble.right")
                                    .font(RMTypography.detail).lineLimit(2)
                                Text(turn.created_at.prefix(10)).font(RMTypography.caption).foregroundStyle(Ink.muted)
                                if turn.deletion_pending == true {
                                    Text("左滑重试清理").font(RMTypography.caption).foregroundStyle(RMColors.danger)
                                } else if let answer = turn.answer {
                                    Text("TwinAgent：" + answer).font(RMTypography.caption).foregroundStyle(Ink.muted).lineLimit(2)
                                }
                            }
                        }
                        .accessibilityIdentifier("recordings.conversation." + turn.id)
                        .recordingDeleteAction(disabled: model.connectionChangeBlocked) { requestDeletion(.conversation(turn)) }
                    }
                    if model.isLoadingTwinArchive { ProgressView("正在载入对话…") }
                    if let error = model.twinArchiveError {
                        Text(error).font(RMTypography.caption).foregroundStyle(Ink.muted)
                        Button("重试载入对话") { Task { await model.loadTwinArchive() } }
                    }
                    if model.twinArchiveCursor != nil {
                        Button("查看更早的对话") { Task { await model.loadTwinArchive(nextPage: true) } }
                            .disabled(model.isLoadingTwinArchive)
                    }
                    if model.visibleTwinArchive.isEmpty && !model.isLoadingTwinArchive && model.twinArchiveError == nil {
                        Text("还没有与 TwinAgent 的对话").font(RMTypography.detail).foregroundStyle(Ink.muted)
                    }
                } header: { Text("与 TwinAgent 的对话") }
                  footer: { Text("主用户的文字和语音问答保存在这里，可左滑删除。游客对话不做记录。") }
            }
            if let error = groupArchive.error { Text(error).foregroundStyle(Ink.muted) }
            ForEach(groupArchive.visible(to: model.pairing)) { local in
                Button { groupRecording = local; showGroupRecording = true } label: {
                    VStack(alignment: .leading, spacing: RMSpacing.xs) {
                        Label("多人录音", systemImage: "person.2.wave.2")
                        Text(local.recordedAt.formatted(date: .abbreviated, time: .shortened)).font(RMTypography.caption)
                    }
                }
                .recordingDeleteAction(disabled: model.connectionChangeBlocked) { requestDeletion(.group(local)) }
            }
            if model.isBusy { ProgressView("正在处理…") }
            if let error = model.errorMessage {
                Text(error).font(RMTypography.detail).foregroundStyle(Ink.muted).accessibilityIdentifier("recordings.deleteError")
            }
        }
        .scrollContentBackground(.hidden).background(Ink.paper)
        .navigationTitle("我的录音").navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) {
            Button("多人录音", systemImage: "person.2.wave.2") { groupRecording = nil; showGroupRecording = true }
                .disabled(model.connectionChangeBlocked).accessibilityIdentifier("speaker.open")
        } }
        .alert(pendingDeletion?.title ?? "删除这段录音？", isPresented: Binding(get: { pendingDeletion != nil }, set: { if !$0 { pendingDeletion = nil } })) {
            if let target = pendingDeletion {
                Button("删除", role: .destructive) {
                    let owner = deletionOwner
                    Task { await delete(target, owner: owner) }
                }
            }
            Button("取消", role: .cancel) { pendingDeletion = nil }
        } message: { Text(pendingDeletion?.message ?? "") }
        .task { await loadArchive() }
        .refreshable { groupArchive.reload(); await loadArchive() }
        .fullScreenCover(isPresented: $showGroupRecording) {
            SpeakerRecordingView(archive: groupArchive, local: groupRecording)
        }
        .fullScreenCover(isPresented: $resumeRecording) {
            RecorderView(question: nil, calibration: nil, simplified: true)
        }
    }
    private func requestDeletion(_ target: RecordingDeletionTarget) {
        model.errorMessage = nil
        deletionOwner = model.pairing.map(RecordingOwner.init)
        pendingDeletion = target
    }
    private func loadArchive() async {
        await model.refresh()
        await model.loadDialogueMaterials()
        await model.loadTwinArchive()
    }
    private func delete(_ target: RecordingDeletionTarget, owner: RecordingOwner?) async {
        guard model.pairing.map(RecordingOwner.init) == owner else { return }
        switch target {
        case .local(let record): _ = await model.deleteRecording(localID: record.id, owner: owner)
        case .remote(let episode): _ = await model.deleteRecording(remoteID: episode.id, owner: owner)
        case .dialogue(let material):
            if let owner { _ = await model.saveDialogue(material, text: nil, owner: owner) }
        case .group(let record): _ = await model.deleteGroupRecording(record, archive: groupArchive)
        case .conversation(let turn):
            if let owner, await model.deleteArchivedTwinTurn(turn, owner: owner) { await model.loadTwinArchive() }
        }
    }
}

private struct TwinArchiveTurnView: View {
    @EnvironmentObject private var model: AppModel
    let turnID: String
    let owner: RecordingOwner?
    private var turn: HistoricalChatTurn? {
        guard !model.isGuestMode, model.pairing.map(RecordingOwner.init) == owner else { return nil }
        return model.visibleTwinArchive.first { $0.id == turnID }
    }
    var body: some View {
        ScrollView {
            if let turn {
            VStack(alignment: .leading, spacing: RMSpacing.lg) {
                Text(turn.created_at.prefix(10)).font(RMTypography.caption).foregroundStyle(Ink.muted)
                VStack(alignment: .leading, spacing: RMSpacing.xs) {
                    Text("你").font(RMTypography.heading)
                    Text(turn.question).textSelection(.enabled)
                }
                Divider()
                VStack(alignment: .leading, spacing: RMSpacing.xs) {
                    Text("TwinAgent").font(RMTypography.heading)
                    if let answer = turn.answer { Text(answer).textSelection(.enabled) }
                    else { Text(turn.deletion_pending == true ? "对话内容已删除，声音清理待重试。" : "当时的回复已失效，不再参与记忆。").foregroundStyle(Ink.muted) }
                }
            }.padding(RMSpacing.page).frame(maxWidth: RMMetrics.maximumReadingWidth, alignment: .leading)
            } else {
                ContentUnavailableView("对话暂不可见", systemImage: "bubble.left.and.exclamationmark.bubble.right",
                    description: Text("请确认当前主用户空间与对话所属空间一致。"))
            }
        }.background(Ink.paper).navigationTitle("TwinAgent 对话").navigationBarTitleDisplayMode(.inline)
    }
}

struct EpisodeMemoriesView: View {
    @EnvironmentObject private var model: AppModel
    let episodeID: String
    var body: some View {
        List {
            ForEach(model.memories.filter { $0.episode_id == episodeID }) { memory in
                NavigationLink { MemoryDetailView(memory: memory) } label: { Text(memory.content) }
            }
            if !model.memories.contains(where: { $0.episode_id == episodeID }) {
                Text("这段录音已保留，暂没有提取出可用的记忆。")
            }
        }.navigationTitle("这段录音的记忆")
            .task { await model.refresh() }.refreshable { await model.refresh() }
    }
}

private struct SimpleSettingsHome: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        List {
            Section("我的记忆空间") {
                if let pairing = model.pairing {
                    Text(pairing.displayName ?? "已连接")
                    Text(pairing.spaceName ?? "本人空间").foregroundStyle(Ink.muted)
                } else { Text("尚未登录，录音仍可先保存在手机。") }
                Button(model.pairing == nil ? "登录记忆服务" : "管理账号与连接") { model.showConnection = true }
                    .accessibilityIdentifier("flow.connection")
            }
            Section("访问模式") {
                NavigationLink("亲友开放范围") { GuestSharingView() }
                    .disabled(model.pairing == nil || model.connectionChangeBlocked)
                Button("进入亲友／游客模式") { Task { await model.enterGuestMode() } }
                    .disabled(model.pairing == nil || model.connectionChangeBlocked)
                    .accessibilityIdentifier("guest.enter")
                Text("亲友免密码访问已开放的记忆花园和 TwinAgent，返回主用户需验证账号密码。")
                    .font(.footnote).foregroundStyle(Ink.muted)
            }
            Section("数据与授权") {
                NavigationLink {
                    if model.pairing?.isCloud == true {
                        TwinVoiceCallView(call: model.realtimeVoice)
                    } else {
                        ScrollView { VoiceSetupView().padding(20) }.navigationTitle("个人声音")
                    }
                } label: { Text("个人声音与语音通话") }
                    .accessibilityIdentifier("settings.voiceCall")
                    .disabled(model.pairing == nil)
                Toggle("录音结束后自动转成文字", isOn: Binding(get: { model.automaticTranscriptionEnabled }, set: { model.automaticTranscriptionEnabled = $0 }))
                    .disabled(model.connectionChangeBlocked).accessibilityIdentifier("recording.autoTranscribe")
                Text("原音先保存在手机。云端转写用途随开始录音确认，结束后自动转写。核对文字后才整理记忆。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
                if model.cloudConsentID != nil {
                    Button("撤销 Twin 对话授权", role: .destructive) { Task { await model.revokeCloudTwin() } }
                }
                Button("管理麦克风权限") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                }
            }
            Section {
                #if DEBUG
                NavigationLink { DesignSystemShowcase() } label: { Label("组件预览", systemImage: "square.grid.2x2") }
                    .accessibilityIdentifier("design.open")
                #endif
                DisclosureGroup("更多：核对人物理解") {
                    NavigationLink { PersonReviewView(review: model.personReview) } label: { Text("核对我的理解") }
                        .accessibilityIdentifier("portrait.review")
                }
                Text("颜色与字号跟随系统设置。")
                    .font(.caption).foregroundStyle(Ink.muted)
            }
        }.scrollContentBackground(.hidden).background(Ink.paper).navigationTitle("我的")
    }
}

struct PairingView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 23) {
                Spacer(minLength: 45)
                Image(systemName: "sparkle")
                    .font(.system(.title, design: .default).weight(.semibold))
                    .foregroundStyle(Ink.coral)
                    .frame(width: 72, height: 72)
                    .background(Ink.peach.opacity(0.55), in: RoundedRectangle(cornerRadius: 22))
                Eyebrow(text: "REMEMBER ME · 私人手记")
                Text("把说过的话，\n慢慢变成懂你的记忆。")
                    .font(.system(.title, design: .default).weight(.semibold))
                    .foregroundStyle(Ink.text)
                    .fixedSize(horizontal: false, vertical: true)
                Text("原音只在你的手机与本机 Mac 之间传送；Mac 转写后，先由你核对文字并确认，再交给 DeepSeek 整理记忆。先用一次性配对码连接，再由你决定什么时候开始录。")
                    .font(.system(.subheadline, design: .default).weight(.regular))
                    .foregroundStyle(Ink.muted)
                    .lineSpacing(5)
                VStack(alignment: .leading, spacing: 15) {
                    Eyebrow(text: "连接到你的 Mac")
                    TextField("https://192.168.1.2:8000", text: $model.pairingServer)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textContentType(.URL)
                    Divider()
                    SecureField("一次性配对码", text: $model.pairingCode)
                        .textInputAutocapitalization(.never)
                    Divider()
                    TextField("证书 SHA-256 指纹", text: $model.pairingFingerprint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                .journalCard()
                Text("也可以在 iPhone 上打开 Mac 给出的配对链接，自动填写这三项。")
                    .font(.subheadline)
                    .foregroundStyle(Ink.muted)
                ActionButton(title: model.isBusy ? "正在连接…" : "安全连接", icon: "lock.shield") {
                    Task { await model.connect() }
                }
                .disabled(model.isBusy)
            }
            .padding(24)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
    }
}

private struct MainTabs: View {
    var body: some View {
        TabView {
            NavigationStack { HomeView() }.tabItem { Label("今天", systemImage: "sun.max") }
            NavigationStack { ArchiveView() }.tabItem { Label("档案", systemImage: "books.vertical") }
            NavigationStack { TwinView() }.tabItem { Label("孪生", systemImage: "bubble.left.and.bubble.right") }
            NavigationStack { ProfileView() }.tabItem { Label("我的", systemImage: "person.crop.circle") }
        }
    }
}

struct ArchiveView: View {
    @State private var segment = 0
    @State private var query = ""
    var body: some View {
        VStack(spacing: 0) {
            Picker("档案内容", selection: $segment) {
                Text("录音").tag(0)
                Text("记忆").tag(1)
            }.pickerStyle(.segmented).padding(.horizontal, 20).padding(.vertical, 12)
            if segment == 0 { EpisodesView(query: query) } else { MemoriesView(query: query) }
        }
        .background(AtmosphereBackground())
        .navigationTitle("档案")
        .searchable(text: $query, prompt: "搜索录音文字或记忆")
    }
}

struct ProfileView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        List {
            Section {
                Text("由你决定留下什么。").font(.title2.weight(.semibold))
                Text("原音先保存在手机，提交后传给你配对的本机服务。确认文字后才进入记忆整理。").font(.body)
            }
            Section("数据与授权") {
                NavigationLink("系统如何理解我") { ModelView() }
                NavigationLink("个人声音与独立授权") {
                    if model.pairing?.isCloud == true {
                        TwinVoiceCallView(call: model.realtimeVoice)
                    } else {
                        ScrollView { VoiceSetupView().padding(20) }.navigationTitle("个人声音")
                    }
                }
                if model.cloudConsentID != nil {
                    Button("撤销云端对话授权", role: .destructive) { Task { await model.revokeCloudTwin() } }
                }
                Button("管理系统麦克风权限") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                }
            }
            Section("外观") { LabeledContent("颜色与字号", value: "跟随系统") }
            Section("连接") { Text(model.pairing == nil ? "尚未连接" : model.pairing?.isCloud == true ? "已连接云端服务" : "已配对本机服务") }
        }
        .scrollContentBackground(.hidden).background(AtmosphereBackground()).navigationTitle("我的")
    }
}

private struct RecordRowStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(configuration.isPressed ? Ink.coral.opacity(0.08) : Color.clear, in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct EpisodeRow: View {
    let episode: EpisodeRecord
    var body: some View {
        HStack(spacing: 12) {
            MemoryGlyph(kind: .voice,size: 24)
            VStack(alignment: .leading, spacing: 5) {
                Text(episode.transcript?.isEmpty == false ? String((episode.transcript ?? "").prefix(48)) : "一段原始录音")
                    .font(.body.weight(.medium)).foregroundStyle(Ink.text).lineLimit(2)
                Text(String(episode.recorded_at.prefix(10))).font(.subheadline).foregroundStyle(Ink.muted)
                if episode.status != "ready" {
                    Text(episode.error_code == "SOURCE_DELETE_PENDING" ? "删除未完成，左滑可重试" : statusLabel(episode.status)).font(.subheadline)
                        .foregroundStyle(episode.status == "reviewing" || episode.status == "failed" ? Ink.coral : Ink.muted)
                }
            }.frame(maxWidth: .infinity,alignment: .leading)
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(Ink.muted).accessibilityHidden(true)
        }.multilineTextAlignment(.leading).padding(.vertical,14).frame(minHeight: 48)
    }
}

private struct EpisodesView: View {
    var query = ""
    @EnvironmentObject private var model: AppModel
    @State private var showRecorder = false
    private var local: [LocalRecording] {
        model.visibleLocalRecordings.filter {
            query.isEmpty || ($0.reviewDraft ?? $0.reviewedTranscript ?? $0.machineTranscript ?? "本机录音")
                .localizedCaseInsensitiveContains(query)
        }
    }
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                Button("再录一段") {
                    if model.prepareNewRecording() { showRecorder = true }
                }.buttonStyle(.bordered).disabled(model.isRecording || model.isBusy || model.isPollingEpisode || model.isLocalTranscribing)
                    .accessibilityIdentifier("archive.newRecording")
                if !local.isEmpty {
                    Text("本机录音 · \(local.count) 段").font(.headline).padding(.top, 16)
                    Text("未提交和已完成的原音都留在手机。每一段可以单独回听、核对和继续整理。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    ForEach(local) { record in
                        NavigationLink { LocalRecordingDetailView(recordingID: record.id) } label: {
                            LocalRecordingRow(record: record)
                        }.buttonStyle(.plain)
                        Divider()
                    }
                }
                if model.episodes.isEmpty && local.isEmpty {
                    MemoryGlyph(kind: .archive,size: 88)
                    Text("这里会保存你录下的原音和转写。即使没有抽出记忆，录音仍然在。")
                        .foregroundStyle(Ink.muted)
                        .journalCard()
                }
                if !model.episodes.isEmpty {
                    Text("服务端录音").font(.headline).padding(.top, 16)
                    Text("服务端列表需要连接；本机原音可以离线回听。")
                        .font(.caption).foregroundStyle(Ink.muted)
                }
                ForEach(model.episodes.filter { query.isEmpty || ($0.transcript ?? "").localizedCaseInsensitiveContains(query) }) { episode in
                    NavigationLink { EpisodeDetailView(initial: episode) } label: {
                        EpisodeRow(episode: episode)
                    }
                    .buttonStyle(RecordRowStyle())
                    Divider()
                }
            }
            .padding(20)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .navigationTitle("档案")
        .refreshable { await model.refresh() }
        .fullScreenCover(isPresented: $showRecorder) { RecorderView(question: nil, calibration: nil) }
    }
}

private struct EpisodeDetailView: View {
    @EnvironmentObject private var model: AppModel
    let initial: EpisodeRecord
    private var episode: EpisodeRecord { model.episodes.first(where: { $0.id == initial.id }) ?? initial }
    private var isText: Bool { episode.source == "IOS_TEXT" }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Eyebrow(text: "\(isText ? "保存的原话" : "原始录音") · \(statusLabel(episode.status))")
                Text("这一段，\n完整地留着。")
                    .font(.system(.title, design: .default).weight(.semibold))
                    .foregroundStyle(Ink.text)
                VStack(alignment: .leading, spacing: 12) {
                    if !isText {
                        Eyebrow(text: "原音")
                        OriginalPlayer(episodeID: episode.id)
                    }
                    Text("录入时间：\(episode.recorded_at)")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                }
                .journalCard()
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: isText ? "保存的原话" : "原始转写")
                    if let report = episode.speaker_report {
                        ForEach(report.speakers) { speaker in
                            Label(speaker.is_subject == true ? "匹配本人声音" : speaker.name.map { "说话人：\($0)" } ?? "说话人暂未匹配", systemImage: "waveform")
                                .font(.caption).foregroundStyle(Ink.muted)
                        }
                    }
                    Text(episode.transcript ?? (isText ? "暂时没有文字。" : "还没有转写。原音已保存，可以稍后再看。"))
                        .font(.system(.body, design: .default).weight(.regular))
                        .foregroundStyle(Ink.text)
                    DisclosureGroup("处理详情") {
                        Text("转写版本：\(episode.stt_model_version ?? "等待中") · 整理版本：\(episode.model_version ?? "等待中")")
                            .font(.subheadline).foregroundStyle(Ink.muted)
                    }
                }
                .journalCard()
                if episode.status == "failed" {
                    ActionButton(title: "重新处理这段录音", icon: "arrow.clockwise") {
                        Task { await model.retryEpisode(episode.id) }
                    }
                }
            }
            .padding(20)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .navigationTitle(isText ? "原话详情" : "录音详情")
        .refreshable { await model.refresh() }
    }
}

private struct HomeView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var showRecorder = false
    @State private var selectedQuestion: QuestionRecord?
    private let speaker = AVSpeechSynthesizer()
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    RememberMeBrand(size: 32)
                    Text("Remember Me").font(.body.weight(.medium)).foregroundStyle(Ink.text)
                    Spacer()
                    Text(Date().formatted(.dateTime.month(.wide).day()))
                        .font(.subheadline).foregroundStyle(Ink.muted)
                }
                .padding(.top, 4)

                VStack(alignment: .leading, spacing: 8) {
                    Text("今天，想记住什么？").font(.title2.weight(.medium)).foregroundStyle(Ink.text)
                    Text("一件小事，也可以慢慢说。").font(.subheadline).foregroundStyle(Ink.muted)
                }
                VStack(spacing: 6) {
                    ActionButton(title: "开始录音", icon: "mic") {
                        selectedQuestion = nil
                        showRecorder = true
                    }
                    Text("原音先留在手机 · 录音豆待连接")
                        .font(.subheadline)
                        .foregroundStyle(Ink.muted)
                }

                if model.draft != nil || model.episodeID != nil {
                    Button { showRecorder = true } label: {
                        HStack(spacing: 12) {
                            MemoryGlyph(kind: .review,size: 40)
                            VStack(alignment: .leading,spacing: 4) {
                                Text("继续查看或重试").font(.body.weight(.medium)).foregroundStyle(Ink.text)
                                Text(model.processingStatus.isEmpty ? "原音已保存在手机" : statusLabel(model.processingStatus))
                                    .font(.subheadline).foregroundStyle(Ink.muted)
                            }.frame(maxWidth: .infinity,alignment: .leading)
                            Image(systemName: "chevron.right").font(.caption).accessibilityHidden(true)
                        }.padding(.vertical,12).frame(minHeight: 48)
                    }.buttonStyle(RecordRowStyle())
                    Divider()
                }

                Text("最近记录").font(.headline.weight(.medium))
                if model.episodes.isEmpty {
                    MemoryGlyph(kind: .memory,size: 88)
                    Text("从第一段声音开始，不必准备完整的故事。").foregroundStyle(Ink.muted)
                }
                ForEach(Array(model.episodes.prefix(3))) { episode in
                    NavigationLink { EpisodeDetailView(initial: episode) } label: {
                        EpisodeRow(episode: episode)
                    }.buttonStyle(RecordRowStyle())
                    Divider()
                }
                if let question = model.questions.first {
                    VStack(alignment: .leading, spacing: 16) {
                        Eyebrow(text: "给你的一个小问题")
                        Text(question.text)
                            .font(.system(.title3, design: .default).weight(.semibold))
                            .foregroundStyle(Ink.text)
                        HStack(spacing: 12) {
                            Button {
                                let utterance = AVSpeechUtterance(string: question.text)
                                utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
                                speaker.speak(utterance)
                            } label: {
                                Label("听问题", systemImage: "speaker.wave.2")
                            }
                            .buttonStyle(.bordered)
                            Button {
                                selectedQuestion = question
                                showRecorder = true
                            } label: {
                                Label("录下回答", systemImage: "mic")
                            }
                            .buttonStyle(.borderedProminent)
                        }
                    }
                    .padding(.vertical, 12)
                }

            }
            .padding(20)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .fullScreenCover(isPresented: $showRecorder) { RecorderView(question: selectedQuestion, calibration: nil) }
        .refreshable { await model.refresh() }
    }
}

struct RecorderView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let question: QuestionRecord?
    let calibration: CalibrationRecord?
    var simplified = false
    var startImmediately = false
    var onShowMemories: (() -> Void)? = nil
    @State private var showClose = false
    @State private var showOrganizeConsent = false
    @State private var showPairing = false
    @State private var showUploadConsent = false
    @State private var uploadPolicy: String?
    @State private var uploadScope: ReviewScope?
    @State private var uploadRecordingID: String?
    private func autoTranscribe(force: Bool = false) async {
        let scope = model.pairing.map(ReviewScope.init)
        let id = model.draft?.id
        if let policy = await model.transcribeFinishedRecordingAutomatically(force: force),
           model.pairing.map(ReviewScope.init) == scope, model.draft?.id == id {
            uploadPolicy = policy; uploadScope = scope; uploadRecordingID = id; showUploadConsent = true
        }
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: RMSpacing.lg) {
                    Text(model.isTranscriptReviewReady && simplified ? "核对这段文字" : simplified && model.processingStatus == "ready" ? "这段录音已整理完成" : calibration?.question ?? question?.text ?? "讲讲今天想留下的事。")
                        .font(RMTypography.title).foregroundStyle(Ink.text)
                    Text(model.isRecording ? (model.isPaused ? "已暂停" : "正在录音") : model.draft != nil ? "录音已保存在手机" : "由你决定什么时候开始")
                        .foregroundStyle(Ink.muted).accessibilityAddTraits(.updatesFrequently)
                    if !simplified || !model.isTranscriptReviewReady && model.processingStatus != "ready" {
                    HStack {
                        Spacer()
                        VoiceReactiveFlower(state: model.isPaused ? .paused : model.isRecording ? .listening : .idle,
                                            audioLevel: model.isRecording && !model.isPaused ? Double(model.meterLevels.last ?? 0) : nil,
                                            size: RMMetrics.recordingFlower)
                        Spacer()
                    }.padding(.vertical, RMSpacing.sm)
                    Text(String(format: "%02d:%02d", model.recordedSeconds / 60, model.recordedSeconds % 60))
                        .font(RMTypography.timer).monospacedDigit()
                        .frame(maxWidth: .infinity)
                    RMRecordingWaveform(levels: model.isRecording ? model.meterLevels : [], paused: model.isPaused || !model.isRecording)
                    }
                    if !model.isRecording {
                        if model.draft != nil { OriginalPlayer(episodeID: nil) }
                        else if let id = model.episodeID ?? calibration?.human_episode_id { OriginalPlayer(episodeID: id) }
                    }
                    if !simplified, let draft = model.draft, !model.isRecording, model.episodeID == nil {
                        NavigationLink("查看本机录音与离线转写") { LocalRecordingDetailView(recordingID: draft.id) }
                            .accessibilityIdentifier("recorder.localDetail")
                    }
                    if model.isTranscriptReviewReady {
                        Text("先核对，再整理记忆").font(.title3.weight(.semibold))
                        Text(model.episodeID == nil ? "修改识别不准确的地方。核对文字保存在手机，连接服务后可以整理记忆。" : "修改识别不准确的地方。确认后才会把文字发送给 DeepSeek 提取记忆。").foregroundStyle(Ink.muted)
                        CaptureTextEditor(title: "核对并修改转写文字", text: $model.transcriptDraft)
                            .rmInputSurface()
                            .onChange(of: model.transcriptDraft) { _, _ in model.saveTranscriptDraft() }
                        TranscriptCorrectionReview(original: model.currentTranscriptReview?.machine_transcript,
                            correction: model.currentTranscriptReview?.automatic_correction, text: $model.transcriptDraft,
                            disabled: model.isBusy)
                        Text("补充信息（可选）").font(.subheadline.weight(.semibold))
                        CaptureTextEditor(title: "补充信息（可选）", text: $model.transcriptSupplement, minimumHeight: 100)
                            .rmInputSurface()
                            .onChange(of: model.transcriptSupplement) { _, value in
                                if value.count > 3000 { model.transcriptSupplement = String(value.prefix(3000)) }
                                model.saveTranscriptDraft()
                            }
                        if simplified {
                            Text(model.organizeNotice).font(.caption).foregroundStyle(Ink.muted)
                        }
                    }
                    if !model.processingStatus.isEmpty {
                        Text(statusLabel(model.processingStatus)).foregroundStyle(Ink.coral)
                    }
                    if model.isBusy || model.isPollingEpisode || model.isPreparingAutomaticTranscription || model.isLocalTranscribing {
                        RMProgressIndicator(title: "正在转写或读取结果…").accessibilityIdentifier("recorder.processing")
                    }
                    if let error = model.errorMessage {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("操作未完成", systemImage: "exclamationmark.circle").font(.headline)
                            Text(error).font(.body)
                                .accessibilityIdentifier("recorder.error")
                            if error.contains("麦克风权限") {
                                Button("打开麦克风设置") {
                                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                                }
                            }
                        }.padding(16).background(Ink.cream, in: RoundedRectangle(cornerRadius: 16))
                    }
                    if simplified && model.processingStatus == "ready" {
                        Text("文字已整理成记忆。你可以查看原话、回听录音，再向 Twin 提问。")
                            .foregroundStyle(Ink.muted)
                    }
                    DisclosureGroup("数据去向") {
                        Text(model.recordingTransferNotice).font(RMTypography.detail).foregroundStyle(Ink.muted)
                    }.font(RMTypography.caption)
                }.padding(RMSpacing.page).frame(maxWidth: RMMetrics.maximumReadingWidth)
            }
            .background(AtmosphereBackground().ignoresSafeArea())
            .rmDismissibleKeyboard()
            .navigationTitle(simplified ? "录音与核对" : "留下一段声音").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) {
                Button("关闭") { if model.isRecording { showClose = true } else { dismiss() } }
                    .disabled(model.isStartingRecording)
            } }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 10) {
                    if model.isRecording {
                        RMButton(title: model.isPaused ? "继续录音" : "暂停录音",
                                 icon: model.isPaused ? "play.fill" : "pause.fill", kind: .secondary) { model.pauseOrResume() }
                        ActionButton(title: simplified && model.automaticTranscriptionEnabled ? "结束录音" : "完成并保存", icon: "stop.fill") {
                            model.finishRecording()
                            if simplified, calibration == nil, model.automaticTranscriptionEnabled,
                               model.pendingAutomaticCaptures.contains(where: { $0.id == model.draft?.id }) {
                                // The home owns the durable upload/review queue. The
                                // next microphone session need not wait for a model.
                                dismiss()
                            } else if simplified { Task { await autoTranscribe() } }
                        }.accessibilityIdentifier("recorder.finish")
                    } else if model.isTranscriptReviewReady {
                        ActionButton(title: model.isBusy ? "正在提交…" : model.episodeID == nil ? "保存核对文字" : "保存到记忆", icon: "checkmark.circle", isLoading: model.isBusy) {
                            if simplified { Task { await model.submitTranscript() } }
                            else { showOrganizeConsent = true }
                        }.disabled(model.isBusy || model.transcriptDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    } else if simplified && model.processingStatus == "文字已保存在手机" {
                        ActionButton(title: "完成", icon: "checkmark") { dismiss() }
                    } else if model.processingStatus == "已保存，正在后台整理" {
                        ActionButton(title: "完成，后台继续整理", icon: "checkmark") { dismiss() }
                    } else if simplified && model.processingStatus == "ready" {
                        ActionButton(title: calibration == nil ? "查看记忆" : "返回回答比较", icon: calibration == nil ? "book.closed" : "arrow.left.arrow.right") {
                            if calibration == nil { onShowMemories?() }; dismiss()
                        }.accessibilityIdentifier("recorder.memories")
                    } else if let id = model.episodeID, model.draft == nil {
                        ActionButton(title: model.isBusy || model.isPollingEpisode ? "正在查看处理进度…" : model.processingStatus == "failed" ? "重新处理并查看文字" : "查看处理进度", icon: "arrow.clockwise") {
                            Task {
                                if model.processingStatus == "failed" { await model.retryEpisode(id) }
                                else { await model.pollEpisode() }
                            }
                        }.disabled(model.isBusy || model.isPollingEpisode)
                    } else if model.draft != nil {
                        if model.pairing == nil && simplified {
                            ActionButton(title: model.isLocalTranscribing ? "正在本机转写…" : "重试转成文字", icon: "text.bubble") { Task { await autoTranscribe(force: true) } }
                                .disabled(model.connectionChangeBlocked)
                        } else { RecordingUploadButton() }
                        Button("保留这段，再录一段") {
                            if model.prepareNewRecording() { Task { await model.startRecording(questionID: question?.id, calibrationID: calibration?.id) } }
                        }.buttonStyle(.bordered).disabled(model.isBusy || model.isPollingEpisode || model.isLocalTranscribing)
                    } else {
                        ActionButton(title: model.isStartingRecording ? "正在打开麦克风…" : "开始录音", icon: "mic.fill") { Task { await model.startRecording(questionID: question?.id, calibrationID: calibration?.id) } }
                            .disabled(model.connectionChangeBlocked)
                    }
                }.padding(RMSpacing.md).background(RMColors.background)
            }
            .sheet(isPresented: $showPairing) {
                NavigationStack {
                    ServiceConnectionView().toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("关闭") { showPairing = false }
                        }
                    }
                    .onChange(of: model.pairing?.baseURL) { _, url in
                        if url != nil { showPairing = false }
                    }
                }
            }
            .interactiveDismissDisabled(model.isRecording || model.isStartingRecording)
            .onChange(of: scenePhase) { _, phase in
                if phase == .background { model.pausePlayback() }
            }
            .task {
                model.isRecorderPresented = true
                if model.episodeID != nil { await model.pollEpisode() }
                else if startImmediately && model.draft == nil { await model.startRecording(questionID: question?.id, calibrationID: calibration?.id) }
            }
            .onDisappear {
                model.isRecorderPresented = false; model.errorMessage = nil
                model.processDeviceRecordingQueue()
            }
            .confirmationDialog("启用录完自动转成文字？", isPresented: $showUploadConsent, titleVisibility: .visible) {
                Button("同意自动转写") {
                    if let policy = uploadPolicy, let scope = uploadScope, let id = uploadRecordingID {
                        Task { await model.approveAutomaticTranscription(policy, recordingID: id, scope: scope) }
                    }
                }
                Button("仅保存这段录音", role: .cancel) { model.processingStatus = "原音已保存，待转写" }
            } message: { Text((model.cloudCapabilities?.uploadNotice ?? model.recordingTransferNotice) + "\n同意后，同一账号与空间、相同转写用途下，后续录音结束自动转写。可在「我的」关闭。") }
            .confirmationDialog("要结束这段录音吗？", isPresented: $showClose, titleVisibility: .visible) {
                Button("收起，继续后台录音") { dismiss() }
                Button("完成并保存") { model.finishRecording(); dismiss() }
                Button("继续录音", role: .cancel) { }
            }
            .confirmationDialog("确认文字并整理记忆？", isPresented: $showOrganizeConsent, titleVisibility: .visible) {
                Button("同意并整理") { Task { await model.submitTranscript() } }
                Button("暂不整理，只保留文字", role: .cancel) { model.saveTranscriptDraft() }
            } message: {
                Text(model.organizeNotice)
            }
        }
    }
}

struct OriginalPlayer: View {
    @EnvironmentObject private var model: AppModel
    let episodeID: String?
    private var identity: String { episodeID ?? model.draft?.id ?? "" }
    private var selected: Bool { model.playbackID == identity }
    var body: some View {
        RMAudioPlayer(status: model.playbackLoading ? "正在打开原音…" : selected && model.isPlaying ? "正在播放" : nil,
                      playing: selected && model.isPlaying, loading: model.playbackLoading,
                      position: selected ? model.playbackPosition : 0, duration: selected ? model.playbackDuration : 0,
                      showsProgress: selected,
                      play: {
                          if selected { model.toggleCurrentPlayback() }
                          else if let episodeID { Task { await model.playOriginal(episodeID: episodeID) } }
                          else { model.togglePlayback() }
                      }, seek: model.seekPlayback)
    }
}

private struct MemoriesView: View {
    var query = ""
    @EnvironmentObject private var model: AppModel
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                Eyebrow(text: "有据可循的记忆")
                Text("说过的话，留下痕迹。")
                    .font(.system(.title, design: .default).weight(.semibold))
                    .foregroundStyle(Ink.text)
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow(text: "在自己的记忆里找")
                    TextField("例如：我为什么喜欢散步？", text: $model.memorySearchQuery)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { Task { await model.searchMemories() } }
                    Button("查找相关记忆") { Task { await model.searchMemories() } }
                        .buttonStyle(.bordered)
                    ForEach(model.memorySearchResults) { result in
                        if let memory = model.memories.first(where: { $0.id == result.id }) {
                            NavigationLink { MemoryDetailView(memory: memory) } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(result.statement).font(.subheadline).foregroundStyle(Ink.text)
                                    Text(result.evidence.first?.excerpt ?? "查看记忆详情")
                                        .font(.subheadline).foregroundStyle(Ink.muted)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .journalCard()
                if model.memories.isEmpty {
                    Text("还没有记忆。试着录下第一段真实的故事。")
                        .foregroundStyle(Ink.muted)
                        .journalCard()
                }
                ForEach(model.memories.filter { query.isEmpty || $0.content.localizedCaseInsensitiveContains(query) }) { memory in
                    NavigationLink { MemoryDetailView(memory: memory) } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            Eyebrow(text: memory.domain ?? memory.memory_type)
                            Text(memory.content)
                                .font(.system(.title3, design: .default).weight(.semibold))
                                .foregroundStyle(Ink.text)
                                .multilineTextAlignment(.leading)
                            Text(memory.evidence.first?.excerpt ?? "查看来源")
                                .font(.subheadline)
                                .foregroundStyle(Ink.muted)
                                .lineLimit(2)
                        }
                        .padding(.vertical, 16)
                    }
                    .buttonStyle(.plain)
                    Divider()
                }
            }
            .padding(20)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .navigationTitle("档案")
        .refreshable { await model.refresh() }
    }
}

struct TwinView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    var simplified = true
    @State private var panel: TwinPanel?
    @State private var showQueryConsent = false
    @State private var queryPolicy: String?
    @State private var showNewChat = false
    @State private var replacementQuestion: String?
    @State private var showReplaceDraft = false
    @State private var loadingOriginalID: String?
    @FocusState private var inputFocused: Bool
    private enum TwinPanel: Identifiable {
        case tools, evidence(String), feedback, review, voiceCall, historyMemory, learning, personalModel, entrustment, remember(UUID), rememberPicker
        var id: String {
            switch self {
            case .tools: "tools"
            case .evidence(let id): "evidence-" + id
            case .feedback: "feedback"
            case .review: "review"
            case .voiceCall: "voiceCall"
            case .remember(let id): "remember-" + id.uuidString
            case .rememberPicker: "rememberPicker"
            case .historyMemory: "historyMemory"
            case .learning: "learning"
            case .personalModel: "personalModel"
            case .entrustment: "entrustment"
            }
        }
    }
    private var canSend: Bool {
        model.pairing != nil && model.cloudConsentID != nil && !model.isBusy && !model.isRestoringChat &&
        !model.personReview.isMutating && !model.isQueryRecording && !model.isRecording &&
        !model.queryDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    private var presenceName: String {
        let name = model.pairing?.spaceName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return name.isEmpty ? "另一个我" : name
    }
    private var presenceState: RMFlowerState {
        if playingTwinOriginal { return .speaking }
        return model.isAskingTwin || model.isRestoringChat ? .thinking : .idle
    }
    private var playingTwinOriginal: Bool {
        guard model.isPlaying, let playbackID = model.playbackID else { return false }
        return model.twinChat.turns.contains { turn in
            guard !turn.invalidated, let answer = turn.answer, !answer.stale else { return false }
            return answer.evidence.contains { $0.episode_id == playbackID && $0.source_type == "SUBJECT" && $0.has_audio == true }
        }
    }
    private var chatAnimation: Animation? {
        reduceMotion || animationsDisabled ? nil : .easeInOut(duration: 0.25)
    }
    private var latestUsable: Bool {
        guard let answer = model.twinAnswer else { return false }
        return !answer.stale && !model.twinChat.turns.contains { $0.answer?.id == answer.id && $0.invalidated }
    }
    private func openEvidence(_ answerID: String) {
        inputFocused = false; panel = .evidence(answerID)
        Task { await model.refreshChatAnswer(answerID) }
    }
    private func correctAnswer(_ answer: TwinAnswerRecord) {
        inputFocused = false
        Task {
            if model.calibrationRun?.twin_answer_id != answer.id { await model.startCalibration(answerID: answer.id) }
            if model.calibrationRun?.twin_answer_id == answer.id { panel = .feedback }
        }
    }
    private func editQuestion(_ question: String) {
        if model.queryDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.queryDraft == question {
            model.queryDraft = question; inputFocused = true
        } else {
            replacementQuestion = question; inputFocused = false; showReplaceDraft = true
        }
    }
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: RMSpacing.lg) {
                    presence
                    if model.twinChat.turns.isEmpty { welcome }
                    if model.isRestoringChat {
                        Label("正在恢复聊天…", systemImage: "arrow.clockwise").font(.caption).foregroundStyle(RMTwinColors.secondaryText)
                    }
                    ForEach(model.twinChat.turns) { turn in
                        chatTurn(turn)
                    }
                    Color.clear.frame(height: 1).id("chat.bottom")
                }
                .padding(.horizontal, RMSpacing.page).padding(.vertical, RMSpacing.md)
                .frame(maxWidth: RMMetrics.maximumReadingWidth)
                .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .contentShape(Rectangle())
            .simultaneousGesture(TapGesture().onEnded { inputFocused = false })
            .onChange(of: model.twinChat.turns.count) { _, _ in
                withAnimation(chatAnimation) { proxy.scrollTo("chat.bottom", anchor: .bottom) }
            }
            .onChange(of: model.isAskingTwin) { _, _ in
                withAnimation(chatAnimation) { proxy.scrollTo("chat.bottom", anchor: .bottom) }
            }
            .onChange(of: model.isRestoringChat) { _, restoring in
                if !restoring { proxy.scrollTo("chat.bottom", anchor: .bottom) }
            }
            .onChange(of: inputFocused) { _, focused in
                if focused { proxy.scrollTo("chat.bottom", anchor: .bottom) }
            }
        }
        .background { TwinAtmosphere().ignoresSafeArea() }
        .foregroundStyle(RMTwinColors.text)
        .tint(RMTwinColors.accent)
        .safeAreaInset(edge: .top, spacing: 0) { memoryShortcut }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .navigationTitle("孪生")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(RMTwinColors.background, for: .navigationBar, .tabBar)
        .toolbarBackground(.visible, for: .navigationBar, .tabBar)
        .toolbarColorScheme(.dark, for: .navigationBar, .tabBar)
        .onDisappear { inputFocused = false; RMKeyboard.dismiss() }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button { inputFocused = false; panel = .learning } label: {
                    Image(systemName: "chart.bar.doc.horizontal")
                }.accessibilityLabel("个人模型训练与复刻验证").accessibilityIdentifier("twin.learning")
            }
            ToolbarItem(placement: .topBarLeading) {
                Button { inputFocused = false; panel = .entrustment } label: { Image(systemName: "gift") }
                    .accessibilityLabel("留下数字托付").accessibilityIdentifier("twin.entrustment")
                    .disabled(model.pairing == nil || model.isBusy || model.entrustmentCaptureState.blocked)
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button { inputFocused = false; panel = .voiceCall } label: { Image(systemName: "phone.fill") }
                    .accessibilityLabel("和孪生语音通话").accessibilityIdentifier("twin.voiceCall")
                    .disabled(model.pairing == nil || model.isBusy || model.isRecording || model.isQueryRecording)
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button { inputFocused = false; panel = .personalModel } label: { Image(systemName: "person.crop.circle") }
                    .accessibilityLabel("人物模型 Personal Model").accessibilityIdentifier("twin.personalModel")
            }
        }
        .sheet(item: $panel) { selection in
            NavigationStack {
                Group {
                    switch selection {
                    case .tools: tools
                    case .evidence(let id): evidence(answerID: id)
                    case .feedback: TwinFeedbackContent()
                    case .review: PersonReviewView(review: model.personReview)
                    case .voiceCall: TwinVoiceCallView(call: model.realtimeVoice)
                    case .remember(let id): RememberChatMessageView(turnID: id)
                    case .rememberPicker: rememberPicker
                    case .historyMemory: ChatHistoryMemoryView()
                    case .learning: PersonalLearningView()
                    case .personalModel: PersonalModelView()
                    case .entrustment: EntrustmentSetupView()
                    }
                }
                .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("关闭") { panel = nil }.disabled(model.realtimeVoice.isActive || model.isVoiceRecording) } }
            }
        }
        .confirmationDialog("使用云端转写提问？", isPresented: $showQueryConsent, titleVisibility: .visible) {
            Button("同意并录下问题") { Task { await model.startQueryRecording(cloudASRPolicy: queryPolicy) } }
            Button("取消", role: .cancel) { }
        } message: { Text(model.cloudCapabilities?.uploadNotice ?? "") }
        .alert("替换当前草稿？", isPresented: $showReplaceDraft) {
            Button("替换为这条问题") {
                if let replacementQuestion { model.queryDraft = replacementQuestion }
                replacementQuestion = nil; inputFocused = true
            }
            Button("保留当前草稿", role: .cancel) { replacementQuestion = nil; inputFocused = true }
        } message: { Text("输入栏里还有未发送的文字。你可以先保留，再编辑之前的问题。") }
        .environment(\.colorScheme, .dark)
        .tint(RMTwinColors.accent)
    }
    private var memoryShortcut: some View {
        HStack(spacing: RMSpacing.md) {
            if model.cloudCapabilities?.chat_history_memory == true {
                Button {
                    inputFocused = false; panel = .historyMemory
                } label: {
                    HStack {
                        Image(systemName: "clock.arrow.circlepath")
                        if !dynamicTypeSize.isAccessibilitySize { Text("旧聊天") }
                    }.frame(minWidth: RMMetrics.touchTarget, minHeight: RMMetrics.touchTarget)
                }
                    .accessibilityLabel("旧聊天记忆").accessibilityIdentifier("twin.historyMemoryShortcut")
                    .disabled(model.cloudConsentID == nil || model.isBusy)
            }
            Button {
                inputFocused = false; panel = .review
            } label: {
                HStack {
                    Image(systemName: "person.text.rectangle")
                    if !dynamicTypeSize.isAccessibilitySize { Text("理解与表达") }
                }.frame(minWidth: RMMetrics.touchTarget, minHeight: RMMetrics.touchTarget)
            }
                .accessibilityLabel("我的理解与表达").accessibilityIdentifier("twin.reviewShortcut")
            Spacer(minLength: 0)
            Image(systemName: "sparkle").foregroundStyle(RMTwinColors.accent).accessibilityHidden(true)
        }
        .font(.caption).buttonStyle(RMQuietPressStyle())
        .frame(minHeight: RMMetrics.touchTarget)
        .padding(.horizontal, RMSpacing.page)
        .background(RMTwinColors.background.opacity(0.94))
    }
    private var presence: some View {
        VStack(spacing: RMSpacing.xs) {
            TwinPresence(state: presenceState, size: model.twinChat.turns.isEmpty ? 124 : 92,
                         original: playingTwinOriginal, audioLevel: playingTwinOriginal ? model.playbackAudioLevel : nil)
                .environment(\.rmAnimationsDisabled, animationsDisabled || panel != nil)
            Text(presenceName)
                .font(.system(.title2, design: .serif)).tracking(2)
                .foregroundStyle(RMTwinColors.text)
            Text("数字孪生 · 依据你留下的讲述")
                .font(RMTypography.caption).foregroundStyle(RMTwinColors.secondaryText)
            if model.isAskingTwin {
                Text("正在查找记忆，整理回应…")
                    .font(RMTypography.caption).foregroundStyle(RMTwinColors.accent)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, RMSpacing.xs).padding(.bottom, RMSpacing.md)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("twin.presence")
    }
    private var welcome: some View {
        VStack(alignment: .leading, spacing: RMSpacing.lg) {
            VStack(spacing: RMSpacing.xs) {
                Text("和另一个自己聊聊").font(.system(.title3, design: .serif))
                Text("从一段回忆，或今天的心事开始。")
                    .font(RMTypography.detail).foregroundStyle(RMTwinColors.secondaryText)
            }.frame(maxWidth: .infinity).padding(.bottom, RMSpacing.xs)
            if model.pairing == nil { ConnectionNotice() }
            else if model.cloudConsentID == nil {
                VStack(alignment: .leading, spacing: RMSpacing.md) {
                    Label("先确认聊天用途", systemImage: "checkmark.shield").font(.headline)
                    Text("问题、相关旧聊天、会话摘要和记忆文字会发送给云端模型。你可以查看、关闭或清除聊天记忆；纠正回答时也会使用核对后的文字。可在「我的」撤销授权。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    ActionButton(title: "同意使用云端孪生", icon: "checkmark.shield") {
                        Task { await model.enableCloudTwin() }
                    }.disabled(model.isBusy)
                }.padding(RMSpacing.md).twinGlass()
            } else {
                DisclosureGroup("选择一个问题") {
                    ForEach(["你记得我喜欢什么吗？", "时间很紧时，我通常会怎么选择？"], id: \.self) { question in
                        Button { editQuestion(question) } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Text(question).font(.subheadline).multilineTextAlignment(.leading)
                                Spacer(minLength: 8)
                                Image(systemName: "arrow.up.left").font(.caption).padding(.top, 3)
                            }.padding(RMSpacing.md).frame(maxWidth: .infinity, minHeight: RMMetrics.buttonHeight, alignment: .leading)
                                .twinGlass(cornerRadius: 14)
                        }.buttonStyle(.plain).accessibilityIdentifier("twin.suggestedQuestion.\(question)")
                    }
                }
                Button {
                    inputFocused = false; panel = .voiceCall
                } label: {
                    Label("直接语音通话", systemImage: "phone.fill")
                        .font(RMTypography.heading).frame(maxWidth: .infinity, minHeight: RMMetrics.buttonHeight)
                        .twinGlass(cornerRadius: 26)
                }.buttonStyle(RMQuietPressStyle())
                    .disabled(model.isBusy || model.isRecording || model.isQueryRecording)
                    .accessibilityIdentifier("twin.voiceCallPrimary")
            }
        }.foregroundStyle(RMTwinColors.text)
    }
    private func chatTurn(_ turn: TwinChatTurn) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Spacer(minLength: 48)
                Text(turn.question).textSelection(.enabled)
                    .padding(.horizontal, RMSpacing.md).padding(.vertical, RMSpacing.sm)
                    .foregroundStyle(RMTwinColors.text)
                    .twinGlass(cornerRadius: 18)
                    .accessibilityIdentifier("twin.userMessage")
                    .contextMenu {
                        Button("复制我的消息", systemImage: "doc.on.doc") { UIPasteboard.general.string = turn.question }
                        Button("记住这句话", systemImage: "bookmark") { inputFocused = false; panel = .remember(turn.id) }
                            .disabled(model.cloudCapabilities?.chat_memory != true || model.pairing == nil || model.isBusy || (turn.answer?.id ?? turn.savedAnswerID) == nil)
                    }
            }
            HStack(alignment: .top, spacing: 8) {
                ForgetMeNotFlower(size: RMSpacing.lg).padding(.top, 3).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 8) {
                    if let answer = turn.answer {
                        Text("另一个我 · \(answer.response_type == "ORIGINAL" ? "本人原话" : answer.response_type == "SIMULATION" ? "根据记忆推测" : answer.response_type == "CONVERSATION" ? "对话回应" : "目前无法确定")")
                            .font(.caption).foregroundStyle(answer.response_type == "ORIGINAL" ? RMTwinColors.gold : RMTwinColors.secondaryText)
                        Text(turn.invalidated ? "相关记忆已有变化，请重新提问。" : answer.displayText)
                            .textSelection(.enabled)
                            .padding(.horizontal, RMSpacing.md).padding(.vertical, RMSpacing.sm)
                            .foregroundStyle(RMTwinColors.text)
                            .twinGlass(cornerRadius: 18, original: answer.response_type == "ORIGINAL" && !turn.invalidated && !answer.stale)
                            .accessibilityIdentifier("twin.answerMessage")
                        if answer.response_type == "ORIGINAL", !answer.stale, !turn.invalidated,
                           let source = answer.evidence.first(where: { $0.source_type == "SUBJECT" && $0.has_audio == true }) {
                            originalRecording(source)
                        }
                        if !turn.invalidated, answer.checkedExpression != nil {
                            Text("参考已确认的表达范例 · 仍是推测")
                                .font(.caption).foregroundStyle(RMTwinColors.secondaryText).accessibilityIdentifier("twin.expression")
                        }
                        if !turn.invalidated {
                            HStack(spacing: 18) {
                                Button("查看回答依据") { openEvidence(answer.id) }
                                    .font(.caption).frame(minHeight: RMMetrics.touchTarget)
                                    .accessibilityIdentifier("twin.evidence.\(answer.id)")
                                    .disabled(model.isBusy || model.isRestoringChat)
                                Menu {
                                    Button("复制回答", systemImage: "doc.on.doc") { UIPasteboard.general.string = answer.displayText }
                                    if ["ORIGINAL", "SIMULATION"].contains(answer.response_type) {
                                        Button("纠正这条回答", systemImage: "square.and.pencil") { correctAnswer(answer) }
                                            .disabled(model.pairing == nil || model.cloudConsentID == nil || model.isBusy || model.isRestoringChat)
                                    }
                                } label: {
                                    Image(systemName: "ellipsis").frame(width: 44, height: 44)
                                }.accessibilityLabel("这条回答的更多操作").accessibilityIdentifier("twin.answerActions.\(answer.id)")
                            }
                        }
                    } else if let failure = turn.failure {
                        Text(failure).font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                        Button(turn.savedAnswerID == nil ? "重试" : "重新加载回答") {
                            Task { await model.retryTwin(turn.id) }
                        }.disabled(model.pairing == nil || model.cloudConsentID == nil || model.isBusy || model.isRestoringChat)
                            .accessibilityIdentifier("twin.retry.\(turn.id)")
                        Button("重新编辑问题") { editQuestion(turn.question) }
                            .font(.subheadline)
                    } else {
                        HStack(spacing: 8) { ProgressView(); Text(model.isRestoringChat ? "正在恢复回答…" : "正在查找记忆…").font(.subheadline).foregroundStyle(RMTwinColors.secondaryText) }
                    }
                }
                Spacer(minLength: 30)
            }
        }
    }
    private func originalRecording(_ source: TwinEvidenceRecord) -> some View {
        let playing = model.playbackID == source.episode_id && model.isPlaying
        let loading = loadingOriginalID == source.episode_id && model.playbackLoading
        return Button {
            loadingOriginalID = source.episode_id
            Task {
                await model.playOriginal(episodeID: source.episode_id)
                loadingOriginalID = nil
            }
        } label: {
            HStack(alignment: .top, spacing: RMSpacing.sm) {
                Group {
                    if loading { ProgressView().tint(RMTwinColors.gold) }
                    else { Image(systemName: playing ? "pause.circle.fill" : "play.circle.fill").font(.title2) }
                }.foregroundStyle(RMTwinColors.gold).frame(width: 28, height: 28)
                VStack(alignment: .leading, spacing: RMSpacing.xs) {
                    Text(loading ? "正在载入本人原声…" : playing ? "正在播放本人原声" : "回听本人原始录音")
                        .font(RMTypography.detail).foregroundStyle(RMTwinColors.gold)
                    if let excerpt = source.excerpt, !excerpt.isEmpty {
                        Text("“\(excerpt)”").font(.system(.subheadline, design: .serif))
                            .foregroundStyle(RMTwinColors.text).lineLimit(3)
                    }
                    Text("来自这条回答的录音依据")
                        .font(RMTypography.caption).foregroundStyle(RMTwinColors.secondaryText)
                }
                Spacer(minLength: 0)
            }.padding(RMSpacing.md).frame(maxWidth: .infinity, alignment: .leading)
                .twinGlass(cornerRadius: 16, original: true)
        }
        .buttonStyle(RMQuietPressStyle())
        .disabled(model.pairing == nil || model.isBusy || model.playbackLoading || model.isRecording || model.isQueryRecording || model.isVoiceRecording)
        .accessibilityIdentifier("twin.originalRecording.\(source.id)")
    }
    private var composer: some View {
        VStack(spacing: RMSpacing.xs) {
            if let notice = model.chatNotice { Text(notice).font(.caption).foregroundStyle(RMTwinColors.secondaryText) }
            if model.isQueryRecording {
                HStack {
                    Label("正在录下问题 · \(model.auxiliarySeconds) 秒", systemImage: "waveform").font(.subheadline)
                    Spacer()
                    Button("结束并转写") { Task { await model.finishAuxiliaryRecording() } }.disabled(model.isBusy)
                }.foregroundStyle(Ink.coral)
            }
            if inputFocused {
                HStack {
                    Spacer()
                    Button("收起键盘", systemImage: "keyboard.chevron.compact.down") {
                        inputFocused = false; RMKeyboard.dismiss()
                    }.font(RMTypography.caption).frame(minHeight: RMMetrics.touchTarget)
                        .accessibilityIdentifier("keyboard.dismiss")
                }
            }
            HStack(alignment: .bottom, spacing: RMSpacing.xs) {
                RMIconButton(title: "更多孪生功能", icon: "plus") { inputFocused = false; panel = .tools }
                    .accessibilityIdentifier("twin.plus")
                TextField("输入消息", text: $model.queryDraft, axis: .vertical)
                    .lineLimit(1...5).font(RMTypography.body).foregroundStyle(RMTwinColors.text)
                    .padding(RMSpacing.sm).twinGlass(cornerRadius: 22).focused($inputFocused)
                    .accessibilityLabel("核对或修改孪生问题").accessibilityIdentifier("twin.input")
                    .disabled(model.isQueryRecording)
                RMIconButton(title: "发送消息", icon: "arrow.up", isLoading: model.isAskingTwin, selected: canSend) {
                    inputFocused = false
                    Task { await model.askTwin() }
                }.disabled(!canSend).accessibilityIdentifier("twin.send")
            }
        }
        .padding(.horizontal, RMSpacing.md).padding(.vertical, RMSpacing.sm)
        .background(RMTwinColors.background)
    }
    private var tools: some View {
        List {
            Section {
                Button {
                    panel = nil
                    Task {
                        if model.isQueryRecording { await model.finishAuxiliaryRecording() }
                        else if model.pairing?.isCloud == true {
                            if let policy = await model.prepareCloudASR() { await model.startQueryRecording(cloudASRPolicy: policy) }
                        } else { await model.startQueryRecording() }
                    }
                } label: { Label(model.isQueryRecording ? "结束并识别问题" : "语音提问", systemImage: "mic") }
                    .disabled(model.pairing == nil || model.cloudConsentID == nil || model.isBusy || model.isRecording)
                if model.cloudCapabilities?.chat_history_memory == true {
                    Button { panel = .historyMemory } label: { Label("旧聊天与长期记忆", systemImage: "clock.arrow.circlepath") }
                        .accessibilityIdentifier("twin.historyMemory").disabled(model.cloudConsentID == nil || model.isBusy)
                }
                Button { panel = .learning } label: { Label("个人模型训练与复刻验证", systemImage: "chart.bar.doc.horizontal") }
                    .accessibilityIdentifier("twin.learningTools")
                Button { panel = .review } label: { Label("我的理解与表达", systemImage: "person.text.rectangle") }
                    .accessibilityIdentifier("twin.review")
            } footer: { Text("语音转成文字后会填入输入栏，由你核对后发送。") }
            if let answer = model.twinAnswer {
                Section("最近一条回答") {
                    Button { openEvidence(answer.id) } label: { Label("查看回答依据", systemImage: "quote.bubble") }
                        .disabled(!latestUsable || model.isRestoringChat)
                    if ["ORIGINAL", "SIMULATION"].contains(answer.response_type) {
                        Button {
                            correctAnswer(answer)
                        } label: { Label("纠正这条回答", systemImage: "square.and.pencil") }
                            .accessibilityIdentifier("twin.feedback")
                            .disabled(!latestUsable || model.pairing == nil || model.cloudConsentID == nil || model.isBusy || model.isRestoringChat)
                    }
                }
            }
            if model.calibrationRun != nil {
                Button { panel = .feedback } label: { Label("我的回答与比较结果", systemImage: "arrow.left.arrow.right") }
                    .accessibilityIdentifier("twin.comparison")
            }
            if model.cloudCapabilities?.chat_memory == true, model.twinChat.turns.contains(where: { ($0.answer?.id ?? $0.savedAnswerID) != nil }) {
                Button { panel = .rememberPicker } label: { Label("从聊天留下记忆", systemImage: "bookmark") }
                    .accessibilityIdentifier("twin.remember").disabled(model.isBusy || model.isRestoringChat)
            }
            Section {
                Button { showNewChat = true } label: { Label("开始新的聊天", systemImage: "square.and.pencil") }
                    .disabled(model.isBusy || model.isRestoringChat || model.isQueryRecording || model.twinChat.turns.isEmpty && model.queryDraft.isEmpty)
                    .accessibilityIdentifier("twin.newChat")
            } footer: { Text(model.cloudCapabilities?.chat_history_memory == true ? "手机恢复最近 20 组消息；已开启的旧聊天记忆还能检索更早及其他会话的内容。" : "手机恢复最近 20 组消息；录音和已确认的记忆单独保留。") }
        }
        .foregroundStyle(Ink.text).navigationTitle("孪生功能").navigationBarTitleDisplayMode(.inline)
        .presentationDetents([.medium, .large])
        .alert("开始新的聊天？", isPresented: $showNewChat) {
            Button("清空当前聊天并开始", role: .destructive) { model.newTwinChat(); panel = nil }
            Button("取消", role: .cancel) { }
        } message: { Text("手机上的当前聊天索引和未发送文字会清空，原始录音、记忆及已保存的比较结果仍保留。") }
    }
    private var rememberPicker: some View {
        List {
            Section {
                ForEach(model.twinChat.turns.filter { ($0.answer?.id ?? $0.savedAnswerID) != nil }) { turn in
                    Button(turn.question) { panel = .remember(turn.id) }
                }
            } header: { Text("选择你自己的真实描述") }
              footer: { Text("只保存你确认的本人原话。孪生的回答不会成为你的经历。") }
        }.navigationTitle("选择本人描述").navigationBarTitleDisplayMode(.inline)
    }
    private func evidence(answerID: String) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if model.isBusy { ProgressView("正在检查回答来源…") }
                if !model.isBusy, let turn = model.twinChat.turns.first(where: { $0.answer?.id == answerID }),
                   let answer = turn.answer, !turn.invalidated {
                    Text(answer.question).font(.headline)
                    if answer.response_type == "CONVERSATION" { Text("这是当前会话的回应，不是对你人格的预测。已承接 \(answer.context_turn_count ?? 0) 轮近期前文，并找回 \(answer.recalled_turn_count ?? 0) 段旧聊天。聊天记录可帮助回顾；人物理解仍需本人核对。") .font(.subheadline).foregroundStyle(Ink.muted) }
                    if let ids = answer.recalled_answer_ids, !ids.isEmpty {
                        HistoricalChatSources(answerIDs: ids)
                    }
                    if answer.evidence.isEmpty && answer.response_type != "CONVERSATION" { Text("这次没有可展示的原文依据。可以先录下相关经历。") }
                    ForEach(answer.evidence) { source in
                        VStack(alignment: .leading, spacing: 10) {
                            Text("“\(source.excerpt ?? "原文摘录暂不可用")”")
                            Text(sourceLabel(source.source_type)).font(.caption).foregroundStyle(Ink.muted)
                            if source.has_audio != false {
                                Button("听当时的原始录音") { Task { await model.playOriginal(episodeID: source.episode_id) } }
                                    .buttonStyle(.bordered).disabled(model.pairing == nil || model.isBusy)
                            } else { Text("本人确认的文字记忆，没有原音。") .font(.caption).foregroundStyle(Ink.muted) }
                        }.journalCard()
                    }
                    if answer.checkedExpression != nil {
                        DisclosureGroup("查看措辞调整前的回答") { Text(answer.answer) }
                            .accessibilityIdentifier("twin.baseAnswer")
                    }
                    DisclosureGroup("回答来源详情") {
                        Text("理解版本 \(answer.person_model_version) · \(answer.model_version)").font(.footnote)
                    }
                } else if !model.isBusy { Text("这条回答暂时不可用，请回到聊天重新加载或提问。") }
            }.foregroundStyle(Ink.text).padding(20)
        }.background(Ink.paper).navigationTitle("回答依据").navigationBarTitleDisplayMode(.inline)
    }
}

private struct RememberChatMessageView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let turnID: UUID
    @State private var ownStatement = false
    private var turn: TwinChatTurn? { model.twinChat.turns.first { $0.id == turnID } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let turn {
                    Text("保留你真正说过的话").font(.title2.weight(.semibold))
                    Text(turn.question).textSelection(.enabled).journalCard().accessibilityIdentifier("twin.rememberText")
                    Text("这句话会保存为本人文字记忆，今后可以检索、纠正或删除。它会交给已配置的云端模型整理人物理解候选，新的理解仍由你核对。孪生自己的回答不会保存成你的经历。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    Toggle("这是我自己的真实描述", isOn: $ownStatement)
                        .accessibilityIdentifier("twin.rememberOwnWords")
                    ActionButton(title: model.isBusy ? "正在保存…" : "确认并记住", icon: "bookmark") {
                        Task { if await model.rememberChatTurn(turnID) { dismiss() } }
                    }.disabled(!ownStatement || model.isBusy || model.cloudCapabilities?.chat_memory != true || model.pairing == nil || model.cloudConsentID == nil)
                        .accessibilityIdentifier("twin.confirmRemember")
                } else { Text("这条消息暂时不可见，请回到当前本人会话。") }
            }.padding(20).foregroundStyle(Ink.text)
        }.background(Ink.paper).navigationTitle("记住这句话").navigationBarTitleDisplayMode(.inline)
    }
}

private struct TwinFeedbackContent: View {
    @EnvironmentObject private var model: AppModel
    @State private var showCalibrationRecorder = false
    @Environment(\.dismiss) private var dismiss
    private let dimensionNames = ["DECISION": "做决定", "REASONING": "考虑理由",
                                  "VALUE_PRIORITY": "价值优先", "EMOTIONAL_REACTION": "情绪反应",
                                  "EXPRESSION": "表达方式"]
    private let alignmentNames = ["MATCH": "相近", "PARTIAL": "部分相近",
                                  "DIFFERENT": "有差异", "NOT_OBSERVED": "尚未提及"]
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("先保留孪生的回答，再录下你真正会怎么回答。核对后的本人文字会与锁定的回答一起发送到云端比较。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
                if let run = model.calibrationRun {
                    VStack(alignment: .leading, spacing: 12) {
                        Eyebrow(text: run.status == "complete" ? "这次回答的差异" : run.status == "stale" ? "需要重新比较" : "我的真实回答")
                        Text(run.question)
                            .font(.system(.title3, design: .default).weight(.semibold)).foregroundStyle(Ink.text)
                        if run.status == "stale" {
                            Text("原始证据或授权已有变化，请重新提问并锁定新回答。")
                                .font(.subheadline).foregroundStyle(Ink.coral)
                        } else {
                            Text("Twin 先回答并锁定：“\(run.locked_answer ?? "")”")
                                .font(.subheadline).foregroundStyle(Ink.muted)
                            if run.status == "awaiting_human" {
                                if run.human_episode_id == nil {
                                    ActionButton(title: "录下我真正的回答", icon: "mic") {
                                        if model.prepareNewRecording() { showCalibrationRecorder = true }
                                    }.disabled(model.isBusy || model.isPollingEpisode || model.isRecording || model.isQueryRecording || model.isLocalTranscribing)
                                } else if model.episodes.first(where: { $0.id == run.human_episode_id })?.status == "ready" {
                                    ActionButton(title: model.isBusy ? "正在比较…" : "比较 Twin 和我的回答",
                                                 icon: "arrow.left.arrow.right") {
                                        Task { await model.completeCalibration(run.id) }
                                    }
                                    .disabled(model.isBusy)
                                } else {
                                    Text("回答已保存。请核对转写并等待记忆处理完成；之后可重试比较。")
                                        .font(.subheadline).foregroundStyle(Ink.muted)
                                    Button(model.episodes.first(where: { $0.id == run.human_episode_id })?.status == "reviewing" ? "核对我的回答文字" : "查看回答录音进度") {
                                        if model.resumeCalibrationTranscript(run) { showCalibrationRecorder = true }
                                    }.buttonStyle(.bordered)
                                        .disabled(model.isBusy || model.isPollingEpisode || model.isRecording || model.isQueryRecording)
                                        .accessibilityIdentifier("twin.resumeReview")
                                }
                            } else if run.status == "complete" {
                                Text(run.summary ?? "校准完成")
                                    .font(.subheadline).foregroundStyle(Ink.text)
                                ForEach(run.dimensions) { dimension in
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text("\(dimensionNames[dimension.dimension] ?? dimension.dimension) · \(alignmentNames[dimension.alignment] ?? dimension.alignment)")
                                            .font(.footnote.weight(.semibold)).foregroundStyle(Ink.coral)
                                        Text(dimension.note)
                                            .font(.subheadline).foregroundStyle(Ink.text)
                                        if let excerpt = dimension.human_excerpt {
                                            Text("本人原话：“\(excerpt)”")
                                                .font(.subheadline).foregroundStyle(Ink.muted)
                                        }
                                    }
                                }
                                if let next = run.suggested_question {
                                    Button("继续追问：\(next)") { model.queryDraft = next; dismiss() }
                                        .font(.subheadline)
                                }
                                Text("这是一次回答的比较，不能代表整体人格还原率。新的理解仍需要你核对确认。")
                                    .font(.subheadline).foregroundStyle(Ink.muted)
                                NavigationLink("整理并核对我的新理解") {
                                    PersonReviewView(review: model.personReview)
                                }.accessibilityIdentifier("twin.reviewFeedback")
                                Text("比较模型：\(run.comparison_model_version ?? "未知")")
                                    .font(.subheadline).foregroundStyle(Ink.muted)
                            }
                        }
                    }
                    .journalCard()
                }

            }.padding(20)
        }
        .background(Ink.paper).navigationTitle("纠正与比较").navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showCalibrationRecorder) {
            if let run = model.calibrationRun { RecorderView(question: nil, calibration: run, simplified: true) }
        }
    }
}

private struct VoiceSetupView: View {
    @EnvironmentObject private var model: AppModel
    @State private var ownVoiceConfirmed = false
    private let guide = "今天我想留下一段自己的声音。希望以后听见它时，还能想起现在的自己。"
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow(text: "只在本机的个人声音")
            if model.pairing?.isCloud == true {
                Text("当前云端接入暂未启用个人声音生成。普通录音、原音播放、文字问答和校准仍可使用。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
            } else if model.voiceProfileReady {
                Text("你的声音样本已就绪。生成只发生在配对的 Mac 上。")
                    .font(.subheadline).foregroundStyle(Ink.text)
                Button("撤销声音授权并删除样本", role: .destructive) {
                    Task { await model.revokeVoice() }
                }
                .font(.subheadline)
            } else {
                Text("请在安静的地方自然地读 5–15 秒，例如：\n“\(guide)”")
                    .font(.subheadline).foregroundStyle(Ink.text)
                Button {
                    Task {
                        if model.isVoiceRecording { await model.finishAuxiliaryRecording() }
                        else { await model.startVoiceSample() }
                    }
                } label: {
                    Label(model.isVoiceRecording ? "结束声音样本" : "录制专用声音样本",
                          systemImage: model.isVoiceRecording ? "stop.circle" : "waveform")
                }
                .buttonStyle(.bordered)
                if model.isVoiceRecording {
                    Text("已录 \(model.auxiliarySeconds) 秒 · 目标 5–15 秒")
                        .font(.subheadline).foregroundStyle(Ink.coral)
                }
                if model.voiceSampleURL != nil {
                    Button(model.playbackID == "voice-sample" && model.isPlaying ? "暂停样本" : "试听声音样本") {
                        if model.playbackID == "voice-sample" { model.toggleCurrentPlayback() }
                        else { model.playVoiceSample() }
                    }.buttonStyle(.bordered)
                    Text("请对照录音核对实际说出的文字；普通记忆录音不会被用作声音样本。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    TextEditor(text: $model.voiceSampleTranscript)
                        .frame(minHeight: 100)
                        .padding(8)
                        .background(Ink.paper, in: RoundedRectangle(cornerRadius: 14))
                        .onChange(of: model.voiceSampleTranscript) { _, text in
                            UserDefaults.standard.set(text, forKey: "pending-voice-transcript")
                        }
                    Toggle("我确认样本中只有自己的声音", isOn: $ownVoiceConfirmed)
                        .font(.subheadline)
                    ActionButton(title: model.isBusy ? "正在提交…" : "单独授权并保存声音样本",
                                 icon: "lock.shield") {
                        Task { await model.enrollVoice() }
                    }
                    .disabled(model.isBusy || !ownVoiceConfirmed ||
                              model.voiceSampleTranscript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                if model.voiceConsentID != nil {
                    Button("撤销声音授权并删除样本", role: .destructive) {
                        Task { await model.revokeVoice() }
                    }
                    .font(.subheadline)
                }
            }
        }
        .journalCard()
    }
}

struct MemoryDetailView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let memory: MemoryRecord
    @State private var correction = ""
    @State private var showDelete = false
    @State private var showDetails = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: RMSpacing.lg) {
                HStack { Spacer(); ForgetMeNotSprig().frame(width: RMMetrics.heroFlower, height: RMMetrics.heroFlower); Spacer() }
                Text(memory.content).font(RMTypography.title).foregroundStyle(RMColors.text)
                    .lineLimit(3).fixedSize(horizontal: false, vertical: true)
                if memory.capture_source != "IOS_TEXT" { OriginalPlayer(episodeID: memory.episode_id) }
                else { Text("本人确认的聊天文字").font(RMTypography.caption).foregroundStyle(RMColors.secondaryText) }
                RMButton(title: "查看记忆详情", icon: "text.alignleft", kind: .text) { showDetails = true }
                    .accessibilityIdentifier("memory.details")
            }.padding(RMSpacing.page).frame(maxWidth: RMMetrics.maximumReadingWidth)
        }.background(RMColors.background.ignoresSafeArea())
            .navigationTitle("记忆").navigationBarTitleDisplayMode(.inline)
            .sheet(isPresented: $showDetails) {
                NavigationStack {
                    details.toolbar { ToolbarItem(placement: .topBarTrailing) { Button("关闭") { showDetails = false } } }
                }
            }
    }
    private var details: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(spacing: 14) {
                    RememberMeBrand(size: 24)
                    Eyebrow(text: "记忆 · \(sourceLabel(memory.source_type))")
                }
                Text(memory.content)
                    .font(.system(.title2, design: .default).weight(.medium))
                    .lineSpacing(8)
                    .foregroundStyle(Ink.text)
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "当时说过的话")
                    Divider()
                    ForEach(memory.evidence) { evidence in
                        Text("“\(evidence.excerpt ?? "")”")
                            .font(.body).lineSpacing(8).foregroundStyle(Ink.text)
                    }
                    Divider()
                    if memory.capture_source != "IOS_TEXT" { OriginalPlayer(episodeID: memory.episode_id) }
                    else { Text("本人确认的聊天文字，没有原音。") .font(.subheadline).foregroundStyle(Ink.muted) }
                    Text("\(memory.capture_source == "IOS_TEXT" ? "本人文字" : "原始转写")：\(memory.transcript ?? "暂无")")
                        .font(.subheadline)
                        .foregroundStyle(Ink.muted)
                    DisclosureGroup("来源与处理详情") {
                        Text("录入：\(memory.recorded_at) · 转写版本 \(memory.stt_model_version ?? "未知") · 整理版本 \(memory.model_version)")
                            .font(.subheadline).foregroundStyle(Ink.muted)
                    }
                }
                .padding(.vertical, 12)
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "如果我理解错了")
                    RMMultilineInput(title: "写下正确的说法", text: $correction, minimumHeight: RMMetrics.sampleEditorHeight)
                    ActionButton(title: "保存纠正", icon: "checkmark") {
                        Task { if await model.correct(memory, to: correction) { showDetails = false; dismiss() } }
                    }
                    .disabled(correction.trimmingCharacters(in: .whitespaces).isEmpty)
                    Button("删除这条记忆", role: .destructive) { showDelete = true }
                        .font(.subheadline)
                }
                .journalCard()
            }
            .padding(RMSpacing.page)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .rmDismissibleKeyboard()
        .navigationTitle("记忆详情")
        .confirmationDialog("删除这条记忆？原始录音和纠错记录仍会保留。", isPresented: $showDelete) {
            Button("删除记忆", role: .destructive) {
                Task { if await model.delete(memory) { showDetails = false; dismiss() } }
            }
        }
    }
}

struct ModelView: View {
    @EnvironmentObject private var model: AppModel
    private let names = [
        "IDENTITY": "我是谁", "EPISODIC_MEMORY": "生命片段",
        "RELATIONSHIPS": "人与关系", "PREFERENCES": "喜欢与不喜欢",
        "VALUES_BELIEFS": "珍视的事", "DECISION_PATTERNS": "做决定的方式",
        "EXPRESSION": "表达方式",
    ]
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 15) {
                Eyebrow(text: "PERSON MODEL · v\(model.modelVersion)")
                Text("一点一点，\n拼成现在的你。")
                    .font(.system(.title, design: .default).weight(.semibold))
                    .foregroundStyle(Ink.text)
                Text("七个维度会随着你的叙述慢慢丰富。矛盾的记忆会一起保留，等你确认。")
                    .font(.subheadline)
                    .foregroundStyle(Ink.muted)
                ForEach(model.domains) { domain in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text(names[domain.domain] ?? domain.domain)
                                .font(.system(.title3, design: .default).weight(.semibold))
                                .foregroundStyle(Ink.text)
                            Spacer()
                            Text("\(domain.traits.count)")
                                .foregroundStyle(Ink.coral)
                        }
                        if domain.traits.isEmpty {
                            Text("还没有足够的记录，留待以后慢慢补上。")
                                .font(.subheadline)
                                .foregroundStyle(Ink.muted)
                        }
                        ForEach(domain.traits) { trait in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(trait.statement)
                                    .font(.subheadline)
                                    .foregroundStyle(Ink.text)
                                if trait.status == "unresolved" {
                                    Label("有不同说法，等待确认", systemImage: "questionmark.circle")
                                        .font(.subheadline)
                                        .foregroundStyle(Ink.coral)
                                }
                            }
                            .padding(.leading, 10)
                            .overlay(alignment: .leading) { Capsule().fill(Ink.peach).frame(width: 3) }
                        }
                    }
                    .journalCard()
                }
            }
            .padding(20)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .navigationTitle("关于我")
        .refreshable { await model.refresh() }
    }
}

// BEGIN GENERATED MEMORY GLYPHS
private enum MemoryGlyphKind { case voice, archive, memory, quote, review, recall }
private struct MemoryGlyph: View {
    let kind: MemoryGlyphKind
    var size: CGFloat = 96
    var label: String? = nil
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    private var shapes: [(String,Path)] {
        switch kind {
        case .voice: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:31,y:18));p.addQuadCurve(to:CGPoint(x:39,y:10),control:CGPoint(x:31,y:10));p.addLine(to:CGPoint(x:65,y:10));p.addQuadCurve(to:CGPoint(x:73,y:18),control:CGPoint(x:73,y:10));p.addLine(to:CGPoint(x:73,y:68));p.addQuadCurve(to:CGPoint(x:65,y:76),control:CGPoint(x:73,y:76));p.addLine(to:CGPoint(x:39,y:76));p.addQuadCurve(to:CGPoint(x:31,y:68),control:CGPoint(x:31,y:76));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:21,y:28));p.addQuadCurve(to:CGPoint(x:29,y:20),control:CGPoint(x:21,y:20));p.addLine(to:CGPoint(x:57,y:20));p.addQuadCurve(to:CGPoint(x:65,y:28),control:CGPoint(x:65,y:20));p.addLine(to:CGPoint(x:65,y:78));p.addQuadCurve(to:CGPoint(x:57,y:86),control:CGPoint(x:65,y:86));p.addLine(to:CGPoint(x:29,y:86));p.addQuadCurve(to:CGPoint(x:21,y:78),control:CGPoint(x:21,y:86));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:31,y:49));p.addLine(to:CGPoint(x:31,y:61));p.move(to:CGPoint(x:39,y:39));p.addLine(to:CGPoint(x:39,y:70));p.move(to:CGPoint(x:47,y:44));p.addLine(to:CGPoint(x:47,y:65));p.move(to:CGPoint(x:55,y:51));p.addLine(to:CGPoint(x:55,y:59));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:62,y:20));p.addCurve(to:CGPoint(x:77,y:16),control1:CGPoint(x:62,y:13),control2:CGPoint(x:72,y:11));p.addCurve(to:CGPoint(x:62,y:20),control1:CGPoint(x:75,y:23),control2:CGPoint(x:67,y:25));p.closeSubpath();return p }())
        ]
        case .archive: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:23,y:14));p.addQuadCurve(to:CGPoint(x:29,y:8),control:CGPoint(x:23,y:8));p.addLine(to:CGPoint(x:70,y:8));p.addQuadCurve(to:CGPoint(x:76,y:14),control:CGPoint(x:76,y:8));p.addLine(to:CGPoint(x:76,y:65));p.addQuadCurve(to:CGPoint(x:70,y:71),control:CGPoint(x:76,y:71));p.addLine(to:CGPoint(x:29,y:71));p.addQuadCurve(to:CGPoint(x:23,y:65),control:CGPoint(x:23,y:71));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:14,y:29));p.addQuadCurve(to:CGPoint(x:21,y:22),control:CGPoint(x:14,y:22));p.addLine(to:CGPoint(x:64,y:22));p.addQuadCurve(to:CGPoint(x:71,y:29),control:CGPoint(x:71,y:22));p.addLine(to:CGPoint(x:71,y:80));p.addQuadCurve(to:CGPoint(x:64,y:87),control:CGPoint(x:71,y:87));p.addLine(to:CGPoint(x:21,y:87));p.addQuadCurve(to:CGPoint(x:14,y:80),control:CGPoint(x:14,y:87));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:26,y:38));p.addLine(to:CGPoint(x:57,y:38));p.move(to:CGPoint(x:26,y:48));p.addLine(to:CGPoint(x:48,y:48));p.move(to:CGPoint(x:26,y:63));p.addCurve(to:CGPoint(x:57,y:60),control1:CGPoint(x:36,y:53),control2:CGPoint(x:44,y:74));p.move(to:CGPoint(x:26,y:75));p.addLine(to:CGPoint(x:40,y:75));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:61,y:12));p.addLine(to:CGPoint(x:69,y:12));p.addLine(to:CGPoint(x:69,y:35));p.addLine(to:CGPoint(x:65,y:31));p.addLine(to:CGPoint(x:61,y:35));p.closeSubpath();return p }())
        ]
        case .memory: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:30,y:16));p.addLine(to:CGPoint(x:70,y:11));p.addQuadCurve(to:CGPoint(x:77,y:18),control:CGPoint(x:76,y:11));p.addLine(to:CGPoint(x:84,y:69));p.addQuadCurve(to:CGPoint(x:79,y:76),control:CGPoint(x:85,y:75));p.addLine(to:CGPoint(x:39,y:81));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:14,y:20));p.addQuadCurve(to:CGPoint(x:21,y:13),control:CGPoint(x:14,y:13));p.addLine(to:CGPoint(x:61,y:13));p.addQuadCurve(to:CGPoint(x:68,y:20),control:CGPoint(x:68,y:13));p.addLine(to:CGPoint(x:68,y:79));p.addQuadCurve(to:CGPoint(x:61,y:86),control:CGPoint(x:68,y:86));p.addLine(to:CGPoint(x:21,y:86));p.addQuadCurve(to:CGPoint(x:14,y:79),control:CGPoint(x:14,y:86));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:39,y:66));p.addCurve(to:CGPoint(x:48,y:40),control1:CGPoint(x:43,y:57),control2:CGPoint(x:47,y:49));p.move(to:CGPoint(x:42,y:61));p.addQuadCurve(to:CGPoint(x:30,y:54),control:CGPoint(x:32,y:61));p.addQuadCurve(to:CGPoint(x:43,y:58),control:CGPoint(x:39,y:52));p.move(to:CGPoint(x:45,y:53));p.addQuadCurve(to:CGPoint(x:57,y:46),control:CGPoint(x:55,y:52));return p }()),
            ("blue",{ var p=Path();p.move(to:CGPoint(x:46,y:39));p.addCurve(to:CGPoint(x:39,y:25),control1:CGPoint(x:29,y:40),control2:CGPoint(x:29,y:24));p.addCurve(to:CGPoint(x:52,y:27),control1:CGPoint(x:39,y:14),control2:CGPoint(x:54,y:16));p.addCurve(to:CGPoint(x:57,y:41),control1:CGPoint(x:62,y:22),control2:CGPoint(x:70,y:37));p.addCurve(to:CGPoint(x:47,y:48),control1:CGPoint(x:66,y:51),control2:CGPoint(x:50,y:60));p.addCurve(to:CGPoint(x:46,y:39),control1:CGPoint(x:36,y:56),control2:CGPoint(x:29,y:41));p.closeSubpath();return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:52,y:38));p.addCurve(to:CGPoint(x:44,y:38),control1:CGPoint(x:52,y:43),control2:CGPoint(x:44,y:43));p.addCurve(to:CGPoint(x:52,y:38),control1:CGPoint(x:44,y:33),control2:CGPoint(x:52,y:33));p.closeSubpath();return p }())
        ]
        case .quote: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:24,y:13));p.addLine(to:CGPoint(x:77,y:13));p.addQuadCurve(to:CGPoint(x:84,y:20),control:CGPoint(x:84,y:13));p.addLine(to:CGPoint(x:84,y:61));p.addQuadCurve(to:CGPoint(x:77,y:68),control:CGPoint(x:84,y:68));p.addLine(to:CGPoint(x:62,y:68));p.addLine(to:CGPoint(x:51,y:79));p.addLine(to:CGPoint(x:51,y:68));p.addLine(to:CGPoint(x:24,y:68));p.addQuadCurve(to:CGPoint(x:17,y:61),control:CGPoint(x:17,y:68));p.addLine(to:CGPoint(x:17,y:20));p.addQuadCurve(to:CGPoint(x:24,y:13),control:CGPoint(x:17,y:13));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:15,y:25));p.addLine(to:CGPoint(x:65,y:25));p.addQuadCurve(to:CGPoint(x:73,y:33),control:CGPoint(x:73,y:25));p.addLine(to:CGPoint(x:73,y:71));p.addQuadCurve(to:CGPoint(x:65,y:79),control:CGPoint(x:73,y:79));p.addLine(to:CGPoint(x:34,y:79));p.addLine(to:CGPoint(x:21,y:87));p.addLine(to:CGPoint(x:21,y:79));p.addLine(to:CGPoint(x:15,y:79));p.addQuadCurve(to:CGPoint(x:8,y:71),control:CGPoint(x:8,y:79));p.addLine(to:CGPoint(x:8,y:33));p.addQuadCurve(to:CGPoint(x:15,y:25),control:CGPoint(x:8,y:25));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:23,y:43));p.addLine(to:CGPoint(x:34,y:43));p.addLine(to:CGPoint(x:34,y:54));p.addLine(to:CGPoint(x:23,y:54));p.closeSubpath();p.move(to:CGPoint(x:34,y:54));p.addQuadCurve(to:CGPoint(x:26,y:65),control:CGPoint(x:34,y:62));p.move(to:CGPoint(x:45,y:43));p.addLine(to:CGPoint(x:56,y:43));p.addLine(to:CGPoint(x:56,y:54));p.addLine(to:CGPoint(x:45,y:54));p.closeSubpath();p.move(to:CGPoint(x:56,y:54));p.addQuadCurve(to:CGPoint(x:48,y:65),control:CGPoint(x:56,y:62));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:68,y:14));p.addLine(to:CGPoint(x:77,y:14));p.addLine(to:CGPoint(x:77,y:32));p.addLine(to:CGPoint(x:72,y:28));p.addLine(to:CGPoint(x:68,y:32));p.closeSubpath();return p }())
        ]
        case .review: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:30,y:10));p.addLine(to:CGPoint(x:68,y:10));p.addQuadCurve(to:CGPoint(x:76,y:18),control:CGPoint(x:76,y:10));p.addLine(to:CGPoint(x:76,y:69));p.addQuadCurve(to:CGPoint(x:68,y:77),control:CGPoint(x:76,y:77));p.addLine(to:CGPoint(x:30,y:77));p.addQuadCurve(to:CGPoint(x:22,y:69),control:CGPoint(x:22,y:77));p.addLine(to:CGPoint(x:22,y:18));p.addQuadCurve(to:CGPoint(x:30,y:10),control:CGPoint(x:22,y:10));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:19,y:23));p.addLine(to:CGPoint(x:57,y:23));p.addQuadCurve(to:CGPoint(x:65,y:31),control:CGPoint(x:65,y:23));p.addLine(to:CGPoint(x:65,y:79));p.addQuadCurve(to:CGPoint(x:57,y:87),control:CGPoint(x:65,y:87));p.addLine(to:CGPoint(x:19,y:87));p.addQuadCurve(to:CGPoint(x:11,y:79),control:CGPoint(x:11,y:87));p.addLine(to:CGPoint(x:11,y:31));p.addQuadCurve(to:CGPoint(x:19,y:23),control:CGPoint(x:11,y:23));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:24,y:39));p.addLine(to:CGPoint(x:51,y:39));p.move(to:CGPoint(x:24,y:50));p.addLine(to:CGPoint(x:43,y:50));p.move(to:CGPoint(x:24,y:62));p.addLine(to:CGPoint(x:37,y:62));return p }()),
            ("blue",{ var p=Path();p.move(to:CGPoint(x:62,y:50));p.addCurve(to:CGPoint(x:62,y:82),control1:CGPoint(x:88,y:50),control2:CGPoint(x:88,y:82));p.addCurve(to:CGPoint(x:62,y:50),control1:CGPoint(x:40,y:82),control2:CGPoint(x:40,y:50));p.closeSubpath();return p }()),
            ("lightline",{ var p=Path();p.move(to:CGPoint(x:55,y:66));p.addLine(to:CGPoint(x:61,y:72));p.addLine(to:CGPoint(x:72,y:60));return p }())
        ]
        case .recall: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:50,y:12));p.addCurve(to:CGPoint(x:66,y:81),control1:CGPoint(x:88,y:12),control2:CGPoint(x:94,y:67));p.addCurve(to:CGPoint(x:12,y:50),control1:CGPoint(x:43,y:95),control2:CGPoint(x:11,y:77));p.addCurve(to:CGPoint(x:50,y:12),control1:CGPoint(x:12,y:28),control2:CGPoint(x:29,y:12));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:44,y:22));p.addCurve(to:CGPoint(x:61,y:75),control1:CGPoint(x:72,y:22),control2:CGPoint(x:84,y:62));p.addCurve(to:CGPoint(x:19,y:49),control1:CGPoint(x:39,y:89),control2:CGPoint(x:18,y:69));p.addCurve(to:CGPoint(x:44,y:22),control1:CGPoint(x:20,y:34),control2:CGPoint(x:29,y:22));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:31,y:47));p.addCurve(to:CGPoint(x:61,y:46),control1:CGPoint(x:33,y:30),control2:CGPoint(x:57,y:31));p.addCurve(to:CGPoint(x:32,y:59),control1:CGPoint(x:67,y:64),control2:CGPoint(x:41,y:74));p.move(to:CGPoint(x:31,y:35));p.addLine(to:CGPoint(x:31,y:47));p.addLine(to:CGPoint(x:42,y:47));p.move(to:CGPoint(x:45,y:44));p.addLine(to:CGPoint(x:45,y:54));p.addLine(to:CGPoint(x:53,y:59));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:71,y:19));p.addCurve(to:CGPoint(x:87,y:19),control1:CGPoint(x:72,y:10),control2:CGPoint(x:85,y:11));p.addCurve(to:CGPoint(x:71,y:19),control1:CGPoint(x:82,y:27),control2:CGPoint(x:74,y:27));p.closeSubpath();return p }())
        ]
        }
    }
    var body: some View {
        let dimension=min(192,max(16,size))
        let flat=dimension<=32 || reduceTransparency || contrast == .increased
        let material=dimension>=64 && !flat
        Canvas { context,canvas in
            context.scaleBy(x:canvas.width/96,y:canvas.height/96)
            let ink = RMColors.action, paper = RMColors.surface, end = RMColors.subtle
            let blue = kind == .memory ? RMColors.flowerGlyph : RMColors.action
            let accent = kind == .memory ? RMColors.flowerMarkCenter : RMColors.brand
            for (role,path) in shapes where !(flat && role == "back") {
                if flat || role == "line" || role == "lightline" {
                    context.stroke(path,with:.color(flat || role == "line" ? ink : RMColors.onAction),style:StrokeStyle(lineWidth:flat ? 6 : 3,lineCap:.round,lineJoin:.round))
                } else {
                    var layer=context
                    if material && (role == "paper" || role == "blue") { layer.addFilter(.shadow(color:RMColors.shadow,radius:2.2,x:0,y:2.5)) }
                    if role == "paper" && material {
                        layer.fill(path,with:.linearGradient(Gradient(colors:[paper,end]),startPoint:.zero,endPoint:CGPoint(x:77,y:96)))
                    } else {
                        layer.fill(path,with:.color(role == "back" ? RMColors.brand.opacity(0.4) : role == "blue" ? blue : role == "gold" ? accent : paper))
                    }
                    if material && role == "paper" { var rim=context;rim.clip(to:path);rim.stroke(path,with:.color(RMColors.surface.opacity(0.55)),lineWidth:1.5) }
                }
            }
        }.frame(width:dimension,height:dimension).accessibilityLabel(Text(label ?? "")).accessibilityHidden(label == nil)
    }
}
// END GENERATED MEMORY GLYPHS

private struct ChatHistoryMemoryView: View {
    @EnvironmentObject private var model: AppModel
    var showsArchiveTitle = false
    @State private var query = ""
    @State private var confirmClear = false
    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 12) {
                    Label(showsArchiveTitle ? "与 TwinAgent 聊过的事" : "聊过的事，还能找回来", systemImage: "clock.arrow.circlepath")
                        .font(.title3.weight(.semibold)).foregroundStyle(Ink.text)
                    Text("按问题找回以前的聊天，摘要保留原消息来源。不限于当前聊天的最近 20 轮；人物理解仍由你核对。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                }.padding(.vertical, 8)
                if let memory = model.chatHistoryMemory {
                    Toggle("参考旧聊天", isOn: Binding(get: { memory.enabled }, set: { enabled in Task { await model.setChatHistoryMemory(enabled: enabled) } }))
                        .disabled(model.isBusy || model.isLoadingChatMemory)
                    Label("可检索 \(memory.available_turn_count) 段聊天", systemImage: "text.bubble")
                        .font(.caption).foregroundStyle(Ink.muted)
                    if !memory.enabled {
                        Label("检索已关闭，开启后才能在新回答中参考旧聊天。", systemImage: "pause.circle")
                            .font(.caption).foregroundStyle(Ink.muted)
                    }
                }
                HStack {
                    TextField("找以前聊过的事", text: $query).submitLabel(.search)
                        .accessibilityIdentifier("chatMemory.searchInput")
                        .onSubmit { Task { await model.loadChatHistoryMemory(query: query) } }
                    Button("搜索") { Task { await model.loadChatHistoryMemory(query: query) } }
                        .frame(minWidth: 44, minHeight: 44).disabled(model.isLoadingChatMemory)
                }
                if model.isLoadingChatMemory { ProgressView("正在查找旧聊天…") }
            }
            if let memory = model.chatHistoryMemory {
                if !memory.summaries.isEmpty {
                    Section("聊天摘要") {
                        ForEach(memory.summaries) { summary in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(summary.summary).textSelection(.enabled).lineSpacing(4)
                                Text("根据原消息整理，可在下方核对；不是已确认的人物理解。")
                                    .font(.caption).foregroundStyle(Ink.muted)
                            }
                        }
                    }
                }
                Section("原始消息") {
                    ForEach(memory.items) { turn in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(turn.created_at.prefix(10)).font(.caption).foregroundStyle(Ink.muted)
                            Text("你：" + turn.question).textSelection(.enabled).lineSpacing(4)
                            if let answer = turn.answer { Text("孪生当时回复：" + answer).font(.subheadline).foregroundStyle(Ink.muted) }
                            else if turn.assistant_stale { Text("当时的孪生回复已失效，不再参与记忆。") .font(.caption).foregroundStyle(Ink.muted) }
                        }
                    }
                    if memory.items.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Label(!memory.enabled ? "旧聊天检索已关闭" : query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "这里还没有旧聊天" : "没有找到匹配的聊天", systemImage: "text.magnifyingglass")
                                .font(.subheadline.weight(.medium))
                            Text(!memory.enabled ? "开启上面的「参考旧聊天」即可继续使用。" : query.isEmpty ? "之后的聊天会逐渐积累在这里。" : "试试更短的关键词，或换一种说法。")
                                .font(.caption).foregroundStyle(Ink.muted)
                        }.padding(.vertical, 8)
                    }
                }
                Section {
                    Button("清除以前的聊天记忆", role: .destructive) { confirmClear = true }
                        .disabled(model.isBusy || model.isLoadingChatMemory)
                } footer: { Text("清除后，旧聊天不再被总结或检索。已经单独保存的本人文字记忆，可在记忆页删除。") }
            }
        }.scrollContentBackground(.hidden).background(Ink.paper)
            .rmDismissibleKeyboard()
            .navigationTitle(showsArchiveTitle ? "TwinAgent 对话" : "旧聊天记忆").navigationBarTitleDisplayMode(.inline)
            .task { await model.loadChatHistoryMemory() }
            .alert("清除以前的聊天记忆？", isPresented: $confirmClear) {
                Button("清除聊天记忆", role: .destructive) { Task { await model.clearChatHistoryMemory() } }
                Button("取消", role: .cancel) { }
            } message: { Text("旧聊天记录仍保留在历史中，但不会重新进入聊天记忆。之后的新聊天可以继续积累。") }
    }
}

private struct HistoricalChatSources: View {
    @EnvironmentObject private var model: AppModel
    let answerIDs: [String]
    @State private var show = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button(show ? "收起旧聊天来源" : "核对本次找回的旧聊天") {
                show.toggle()
                if show { Task { await model.loadChatHistoryMemory(answerIDs: answerIDs) } }
            }.buttonStyle(.bordered)
            if show {
                if model.isLoadingChatMemory { ProgressView() }
                ForEach((model.chatHistoryMemory?.items ?? []).filter { answerIDs.contains($0.answer_id) }) { turn in
                    Text("\(turn.created_at.prefix(10)) · 你：\(turn.question)")
                    if let answer = turn.answer { Text("孪生当时回复：" + answer).font(.caption).foregroundStyle(Ink.muted) }
                }
            }
        }
    }
}

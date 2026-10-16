import SwiftUI

struct SpeakerRecordingView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var phase
    @ObservedObject var archive: SpeakerLocalArchive
    @StateObject private var workspace: SpeakerRecordingWorkspace
    @State private var deleteRequested = false
    @State private var revokeRequested = false
    private let introduction = "可以直接聊天，也可以自然说一句“我叫小王”。"
    init(archive: SpeakerLocalArchive, local: LocalSpeakerRecording? = nil) {
        self.archive = archive
        _workspace = StateObject(wrappedValue: SpeakerRecordingWorkspace(local: local))
    }
    private var currentOwner: Bool {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-speaker-recording") { return true }
        #endif
        guard let pairing = model.pairing else { return false }
        return workspace.local == nil || workspace.local?.owner == RecordingOwner(pairing)
    }
    private var scopeID: String {
        guard let pairing = model.pairing else { return "offline" }
        return pairing.baseURL + pairing.actorID + pairing.subjectID
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: RMSpacing.lg) {
                    if workspace.local == nil || workspace.recording {
                        VStack(spacing: RMSpacing.sm) {
                            ForgetMeNotFlower(size: RMMetrics.heroFlower, state: workspace.recording ? .listening : .idle)
                            Text(workspace.recording ? "正在记录大家的回忆" : "一起留下一段回忆").font(RMTypography.heading)
                        }.frame(maxWidth: .infinity)
                        Text("直接开始聊天即可，系统会按声音区分发言。说到名字时会自动关联，没听清也不影响转写。")
                            .font(RMTypography.detail).foregroundStyle(Ink.muted)
                        Text(workspace.capabilities?.introduction_guide ?? introduction)
                            .font(RMTypography.body).rmCardSurface().accessibilityIdentifier("speaker.introduction")
                    }
                    if let error = workspace.error ?? archive.error {
                        RMFeedback(title: "需要留意", message: error, kind: .error).accessibilityIdentifier("speaker.error")
                    }
                    if workspace.archiveSavePending {
                        Button("重试保存录音档案") { workspace.retryArchiveSave(archive: archive) }
                    }
                    if workspace.capabilities?.available != true && workspace.reply == nil {
                        Text("自动识别暂不可用，原音可以先保留在手机。")
                            .font(RMTypography.caption).foregroundStyle(Ink.muted)
                    }
                    if workspace.local == nil {
                        Text("点击开始，即同意本次录音、云端转写和声音识别。")
                            .font(RMTypography.caption).foregroundStyle(Ink.muted).accessibilityIdentifier("speaker.startNotice")
                    }
                    if let notice = workspace.capabilities?.notice {
                        DisclosureGroup("录音与识别用途") { Text(notice).font(RMTypography.caption) }
                    }
                    if workspace.recording {
                        Text("已录 \(workspace.seconds) 秒").font(RMTypography.detail).monospacedDigit()
                    } else if let local = workspace.local, currentOwner {
                        HStack {
                            Text(local.recordedAt.formatted(date: .abbreviated, time: .shortened)).font(RMTypography.caption)
                            Spacer()
                            Button("回听原音", systemImage: "play.circle") { workspace.play(archive: archive) }
                                .accessibilityIdentifier("speaker.playOriginal")
                        }
                        if let report = workspace.reply?.report {
                            if report.identification_status == "text_only" { Text("文字已保留，说话人暂未分清。").font(RMTypography.caption).foregroundStyle(Ink.muted) }
                            VStack(alignment: .leading, spacing: RMSpacing.sm) {
                                Text("本段说话人").font(RMTypography.heading)
                                ForEach(Array(report.speakers.enumerated()), id: \.element.id) { index, speaker in
                                    Text("说话人 \(index + 1)\(speaker.name.map { " · " + $0 } ?? "")").font(RMTypography.detail)
                                }
                            }
                            ForEach(report.segments) { segment in
                                VStack(alignment: .leading, spacing: RMSpacing.sm) {
                                    HStack {
                                        Text(segment.label).font(RMTypography.heading).foregroundStyle(Ink.coral)
                                        Spacer()
                                        Text(segment.timing_estimated == true ? "整段文字" : timestamp(segment.start_ms)).font(RMTypography.caption).foregroundStyle(Ink.muted)
                                    }
                                    Text(segment.text).font(RMTypography.body).textSelection(.enabled)
                                    Button("回听这一句", systemImage: "speaker.wave.2") { workspace.play(archive: archive, segment: segment) }
                                        .font(RMTypography.caption)
                                }.rmCardSurface().accessibilityIdentifier("speaker.segment." + segment.id)
                            }
                        } else {
                            Text(status).font(RMTypography.detail).foregroundStyle(Ink.muted)
                        }
                        if let error = workspace.reply?.error { Text(error).font(RMTypography.detail).foregroundStyle(Ink.muted) }
                        Text("这段多人录音单独保存，不会自动变成本人资料或音色样本。")
                            .font(RMTypography.caption).foregroundStyle(Ink.muted)
                        if local.remoteID != nil {
                            Button("撤销本段识别授权并删除", role: .destructive) { revokeRequested = true }
                                .disabled(workspace.busy)
                        }
                        Button("删除这段多人录音", role: .destructive) { deleteRequested = true }
                            .disabled(workspace.busy)
                    }
                }.padding(RMSpacing.page).frame(maxWidth: RMMetrics.maximumReadingWidth)
            }.background(Ink.paper)
                .navigationTitle("多人录音").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .topBarTrailing) {
                    Button("关闭") { dismiss() }.disabled(workspace.recording || workspace.busy || workspace.archiveSavePending)
                } }
                .safeAreaInset(edge: .bottom) {
                    VStack(spacing: RMSpacing.sm) {
                        if workspace.recording {
                            RMButton(title: "结束并保存", icon: "stop.fill") {
                                workspace.finish(archive: archive); model.isSpeakerRecording = false
                                Task { await process() }
                            }.accessibilityIdentifier("speaker.finish")
                        } else if workspace.local == nil {
                            RMButton(title: "开始多人录音", icon: "mic.fill", isLoading: workspace.busy) {
                                guard let pairing = model.pairing, model.prepareRealtimeCapture() else { return }
                                model.stopPlayback(); model.isSpeakerRecording = true
                                Task {
                                    await workspace.start(pairing: pairing, archive: archive, consented: true)
                                    model.isSpeakerRecording = workspace.captureActive
                                }
                            }.disabled(model.pairing == nil || workspace.busy || !currentOwner)
                                .accessibilityIdentifier("speaker.start")
                        } else if workspace.reply?.status != "ready", !["revoked", "deleted"].contains(workspace.reply?.status ?? "") {
                            RMButton(title: workspace.busy ? "正在识别说话人…" : "识别说话人", icon: "person.2.wave.2", isLoading: workspace.busy) {
                                Task { await process() }
                            }.disabled(workspace.busy || workspace.capabilities?.available != true || !currentOwner)
                                .accessibilityIdentifier("speaker.process")
                        }
                    }.padding(RMSpacing.md).background(Ink.paper)
                }
        }
        .interactiveDismissDisabled(workspace.recording || workspace.busy || workspace.archiveSavePending)
        .task(id: scopeID) { await load() }
        .task(id: workspace.reply?.id) {
            for _ in 0..<30 {
                guard !Task.isCancelled, let reply = workspace.reply, ["uploaded", "analyzing"].contains(reply.status) else { return }
                do { try await Task.sleep(for: .seconds(4)) } catch { return }
                await refresh()
            }
        }
        .onChange(of: phase) { _, phase in
            if phase == .background { workspace.cancelPendingStart(); workspace.finish(archive: archive); workspace.stopPlayback(); model.isSpeakerRecording = false }
            else if phase != .active { workspace.stopPlayback() }
        }
        .onChange(of: workspace.captureActive) { _, active in model.isSpeakerRecording = active }
        .onDisappear { workspace.cancelPendingStart(); workspace.finish(archive: archive); workspace.stopPlayback(); model.isSpeakerRecording = false }
        .alert("删除这段多人录音？", isPresented: $deleteRequested) {
            Button("删除", role: .destructive) { Task { await remove(revoke: false) } }
            Button("取消", role: .cancel) { }
        } message: { Text("这台手机和已提交的服务端原音、说话人结果都会删除。") }
        .alert("撤销本段声音识别？", isPresented: $revokeRequested) {
            Button("撤销并删除", role: .destructive) { Task { await remove(revoke: true) } }
            Button("取消", role: .cancel) { }
        } message: { Text("停止本段识别，并删除手机和服务端的这段多人录音。") }
    }
    private var status: String {
        switch workspace.reply?.status {
        case "uploaded", "analyzing": "正在按声音区分说话人，可以稍后回来查看。"
        case "failed": "识别暂未完成，原音仍然保留。"
        case "revoked", "deleted": "本段识别已停止。"
        default: "原音已保存，识别后会按说话人显示。"
        }
    }
    private func timestamp(_ ms: Int) -> String { String(format: "%02d:%02d", ms / 60000, ms / 1000 % 60) }
    private func client(_ pairing: Pairing) throws -> APIClient {
        try APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token)
    }
    private func stillCurrent(_ pairing: Pairing) -> Bool {
        model.pairing?.token == pairing.token && model.pairing.map(RecordingOwner.init) == RecordingOwner(pairing)
    }
    private func load() async {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-speaker-recording") {
            workspace.showIsolatedPreview(); return
        }
        #endif
        guard let pairing = model.pairing, currentOwner else { workspace.reply = nil; return }
        do {
            if let local = workspace.local, local.durationMS == 0,
               let duration = SpeakerRecordingWorkspace.savedDuration(archive.file(local.id)) {
                workspace.local?.durationMS = duration
                if let recovered = workspace.local { try archive.save(recovered) }
            }
            let caps = try await client(pairing).speakerCapabilities(subject: pairing.subjectID)
            guard stillCurrent(pairing) else { return }
            workspace.capabilities = caps
            await refresh()
        } catch { if stillCurrent(pairing) { workspace.error = "多人识别服务暂未连接，原音可以先保留在手机。" } }
    }
    private func refresh() async {
        guard let pairing = model.pairing, currentOwner, let id = workspace.local?.remoteID else { return }
        do {
            let reply = try await client(pairing).speakerRecording(subject: pairing.subjectID, id: id)
            guard stillCurrent(pairing), reply.id == id else { return }
            workspace.reply = reply
        } catch { if stillCurrent(pairing) { workspace.error = "结果暂未读出，可重新打开这段录音查看。" } }
    }
    private func process() async {
        guard !workspace.busy, !workspace.recording, currentOwner, let pairing = model.pairing,
              var local = workspace.local, let caps = workspace.capabilities, caps.available else { return }
        guard local.durationMS >= 5000 else { workspace.error = "请录制至少 5 秒，原音仍然保留。"; return }
        if local.policy != caps.policy { local.policy = caps.policy; workspace.local = local; try? archive.save(local) }
        workspace.busy = true; workspace.error = nil; defer { workspace.busy = false }
        do {
            let api = try client(pairing)
            if local.consentID == nil {
                let consent = try await api.grantConsent(subjectID: pairing.subjectID, scope: "SPEAKER_IDENTIFICATION", evidenceRef: "ios-start-recording:" + local.id)
                guard stillCurrent(pairing) else { return }
                local.consentID = consent.id; workspace.local = local; try archive.save(local)
            }
            if local.remoteID == nil, let consent = local.consentID {
                let reply = try await api.uploadSpeakerRecording(local, file: archive.file(local.id), subject: pairing.subjectID, consent: consent, policy: caps.policy)
                guard stillCurrent(pairing) else { return }
                local.remoteID = reply.id; workspace.local = local; workspace.reply = reply; try archive.save(local)
            }
            if let id = local.remoteID {
                let reply = try await api.identifySpeakers(subject: pairing.subjectID, id: id, policy: caps.policy)
                guard stillCurrent(pairing), reply.id == id else { return }
                workspace.reply = reply
            }
        } catch { if stillCurrent(pairing) { workspace.error = "识别未完成，原音仍在手机：\(error.localizedDescription)" } }
    }
    private func remove(revoke: Bool) async {
        guard let pairing = model.pairing, currentOwner, let local = workspace.local, !workspace.busy else { return }
        workspace.busy = true; defer { workspace.busy = false }
        do {
            let api = try client(pairing)
            if let id = local.remoteID { try await api.deleteSpeakerRecording(subject: pairing.subjectID, id: id) }
            if revoke, let consent = local.consentID { try await api.revokeConsent(consent) }
            guard stillCurrent(pairing) else { return }
            try archive.remove(local.id); dismiss()
        } catch { workspace.error = "删除未完成，请稍后重试。" }
    }
}

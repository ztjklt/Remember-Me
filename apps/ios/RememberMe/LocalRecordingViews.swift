import SwiftUI

struct LocalRecordingRow: View {
    @EnvironmentObject private var model: AppModel
    let record: LocalRecording
    var body: some View {
        RMRecordingCard(title: String((record.reviewedTranscript ?? record.machineTranscript ?? model.episodes.first(where: { $0.id == record.episodeID })?.transcript ?? (record.draft.captureSource == "WORK_3200" ? "一段录音豆录音" : "一段本机录音")).prefix(48)),
                        date: record.draft.recordedAt.formatted(date: .abbreviated, time: .omitted),
                        status: "\(record.draft.durationMS / 1000) 秒 · \(record.episodeID == nil ? "仅保存在手机" : statusLabel(record.status))")
    }
}

struct LocalRecordingDetailView: View {
    @EnvironmentObject private var model: AppModel
    let recordingID: String
    var simplified = false
    @State private var text = ""
    @State private var showRecorder = false
    private var record: LocalRecording? { model.visibleLocalRecordings.first { $0.id == recordingID } }
    private var blocked: Bool { model.isBusy || model.isPollingEpisode || model.isRecording || model.isLocalTranscribing }
    var body: some View {
        ScrollView {
            if let record {
                VStack(alignment: .leading, spacing: 20) {
                    Text(simplified ? "这段录音" : "原音留在手机").font(.title2.weight(.semibold))
                    if simplified {
                        Text(record.episodeID == nil ? "原音已保存，还没有转写" : statusLabel(record.status))
                            .foregroundStyle(Ink.coral)
                    }
                    Text(record.draft.recordedAt.formatted(date: .abbreviated, time: .shortened))
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    RMAudioPlayer(playing: model.playbackID == recordingID && model.isPlaying,
                                  loading: model.playbackLoading, position: model.playbackPosition,
                                  duration: model.playbackID == recordingID ? model.playbackDuration : 0,
                                  showsProgress: model.playbackID == recordingID,
                                  play: { model.playLocalRecording(recordingID) }, seek: model.seekPlayback)
                        .disabled(model.isRecording)
                    if !simplified {
                    Text("中文本机转写只在设备支持且你允许语音识别时进行；不可用时原音仍保留。上传到记忆服务转写是另一个由你选择的操作。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    if record.machineTranscript == nil {
                        ActionButton(title: model.isLocalTranscribing ? "正在本机转写…" : "在 iPhone 上转成文字", icon: "text.bubble") {
                            Task { await model.transcribeLocalRecording(recordingID) }
                        }.disabled(blocked).accessibilityIdentifier("local.transcribe")
                    } else {
                        DisclosureGroup("本机机器原始转写") { Text(record.machineTranscript ?? "") }
                        Text("核对文字").font(.headline)
                        TextEditor(text: $text).frame(minHeight: 180).padding(10)
                            .background(Ink.cream, in: RoundedRectangle(cornerRadius: 12))
                            .accessibilityLabel("本机核对文字").disabled(blocked || record.episodeID != nil)
                            .onChange(of: text) { _, value in model.saveLocalReviewDraft(recordingID, text: value) }
                        if record.episodeID == nil {
                          Button("保存核对文字") { _ = model.saveLocalReview(recordingID, text: text) }
                            .buttonStyle(.bordered).disabled(blocked || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        } else {
                            Text("已提交录音的文字请到处理页核对；已生成的记忆请在记忆详情中纠正。")
                                .font(.caption).foregroundStyle(Ink.muted)
                        }
                        if record.reviewedAt != nil && record.reviewedTranscript == text.trimmingCharacters(in: .whitespacesAndNewlines) {
                            Label("核对文字已保存在手机", systemImage: "checkmark.circle").foregroundStyle(Ink.coral)
                        } else if record.episodeID == nil {
                            Text("修改草稿会保留在手机；核对完成后请保存。")
                                .font(.caption).foregroundStyle(Ink.muted)
                        }
                        Text("这一步只保存在手机，不会生成记忆或发送给 AI。")
                            .font(.caption).foregroundStyle(Ink.muted)
                    }
                    }
                    Divider()
                    if record.status == "ready" {
                        Text("这段录音已整理好，原音仍可离线回听。")
                        if let id = record.episodeID {
                            NavigationLink("查看这段录音的记忆") { EpisodeMemoriesView(episodeID: id) }
                        }
                    } else {
                        ActionButton(title: record.episodeID == nil ? "转成文字" : record.status == "reviewing" ? "核对文字" : "查看进度", icon: "arrow.right") {
                            if model.selectLocalRecording(recordingID) { showRecorder = true }
                        }.disabled(blocked).accessibilityIdentifier("local.continue")
                    }
                }.padding(20)
            } else {
                ContentUnavailableView("录音暂不可见", systemImage: "mic.slash",
                                       description: Text("请确认当前使用者与录音所属空间一致。"))
            }
        }
        .rmDismissibleKeyboard()
        .background(Ink.paper.ignoresSafeArea()).navigationTitle(simplified ? "录音详情" : "本机录音")
        .fullScreenCover(isPresented: $showRecorder) { RecorderView(question: nil, calibration: nil, simplified: simplified) }
        .onAppear { text = record?.reviewDraft ?? record?.reviewedTranscript ?? record?.machineTranscript ?? "" }
        .task { await model.refresh() }
        .refreshable { await model.refresh() }
        .onChange(of: record?.machineTranscript) { _, value in
            if text.isEmpty { text = value ?? "" }
        }
    }
}

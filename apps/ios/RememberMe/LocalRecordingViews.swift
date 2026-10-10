import SwiftUI

struct LocalRecordingRow: View {
    let record: LocalRecording
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "mic").foregroundStyle(Ink.coral)
            VStack(alignment: .leading, spacing: 5) {
                Text(String((record.reviewedTranscript ?? record.machineTranscript ?? "一段本机录音").prefix(48)))
                    .foregroundStyle(Ink.text)
                Text(record.draft.recordedAt, style: .date).font(.caption).foregroundStyle(Ink.muted)
                Text("\(record.draft.durationMS / 1000) 秒 · \(record.episodeID == nil ? "仅保存在手机" : "本机原音已保留 · " + statusLabel(record.status))")
                    .font(.caption).foregroundStyle(Ink.muted)
            }
            Spacer()
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(Ink.muted)
        }.padding(.vertical, 14).frame(minHeight: 48)
    }
}

struct LocalRecordingDetailView: View {
    @EnvironmentObject private var model: AppModel
    let recordingID: String
    @State private var text = ""
    @State private var showRecorder = false
    private var record: LocalRecording? { model.visibleLocalRecordings.first { $0.id == recordingID } }
    private var blocked: Bool { model.isBusy || model.isPollingEpisode || model.isRecording || model.isLocalTranscribing }
    var body: some View {
        ScrollView {
            if let record {
                VStack(alignment: .leading, spacing: 20) {
                    Text("原音留在手机").font(.title2.weight(.semibold))
                    Text(record.draft.recordedAt.formatted(date: .abbreviated, time: .shortened))
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    Button {
                        model.playLocalRecording(recordingID)
                    } label: {
                        Label(model.playbackID == recordingID && model.isPlaying ? "暂停原音" : "播放原音",
                              systemImage: model.playbackID == recordingID && model.isPlaying ? "pause.fill" : "play.fill")
                            .frame(minHeight: 48)
                    }.buttonStyle(.bordered).disabled(model.isRecording)
                    if model.playbackID == recordingID && model.playbackDuration > 0 {
                        Slider(value: Binding(get: { model.playbackPosition }, set: model.seekPlayback),
                               in: 0...max(1, model.playbackDuration)).accessibilityLabel("原音播放位置")
                    }
                    Text("中文本机转写只在设备支持且你允许语音识别时进行；不可用时原音仍保留。连接 Mac 转写是另一个由你选择的操作。")
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
                    Divider()
                    if record.status == "ready" {
                        Text("这一段已在配对服务中完成整理。原音仍可在这里离线回听。")
                        NavigationLink("查看记忆档案") { ArchiveView() }
                    } else {
                        ActionButton(title: record.episodeID == nil ? "继续转写与整理" : "继续查看处理结果", icon: "arrow.right") {
                            if model.selectLocalRecording(recordingID) { showRecorder = true }
                        }.disabled(blocked).accessibilityIdentifier("local.continue")
                    }
                }.padding(20)
            } else {
                ContentUnavailableView("录音暂不可见", systemImage: "mic.slash",
                                       description: Text("请确认当前使用者与录音所属空间一致。"))
            }
        }
        .background(Ink.paper.ignoresSafeArea()).navigationTitle("本机录音")
        .fullScreenCover(isPresented: $showRecorder) { RecorderView(question: nil, calibration: nil) }
        .onAppear { text = record?.reviewDraft ?? record?.reviewedTranscript ?? record?.machineTranscript ?? "" }
        .onChange(of: record?.machineTranscript) { _, value in
            if text.isEmpty { text = value ?? "" }
        }
    }
}

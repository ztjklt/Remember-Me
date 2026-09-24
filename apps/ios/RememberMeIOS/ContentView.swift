import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            CaptureView()
                .tabItem { Label("录音", systemImage: "mic") }
            MemoriesView()
                .tabItem { Label("记忆", systemImage: "books.vertical") }
            ConnectionView()
                .tabItem { Label("连接", systemImage: "server.rack") }
        }
    }
}

private struct CaptureView: View {
    @EnvironmentObject private var capture: AudioCapture
    @EnvironmentObject private var flow: EpisodeFlow

    var body: some View {
        NavigationStack {
            Form {
                Section("本机录音") {
                    Text("先征得录音对象同意。录音文件保存在本机；上传后由 Backend 异步处理。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    HStack {
                        Image(systemName: capture.isRecording ? "record.circle.fill" : "waveform")
                            .foregroundStyle(capture.isRecording ? .red : .primary)
                        Text(duration(capture.elapsed))
                            .monospacedDigit()
                            .font(.title2)
                        Spacer()
                        if capture.isPaused { Text("已暂停").foregroundStyle(.orange) }
                    }
                    if capture.isRecording {
                        HStack {
                            Button(capture.isPaused ? "继续" : "暂停") { capture.pauseOrResume() }
                            Spacer()
                            Button("保存录音") { capture.stop() }
                                .tint(.red)
                        }
                    } else {
                        Button("开始录音") { Task { await capture.start() } }
                            .buttonStyle(.borderedProminent)
                    }
                    if let file = capture.fileURL, !capture.isRecording {
                        Text(file.lastPathComponent)
                            .font(.caption)
                            .textSelection(.enabled)
                        Button(capture.isPlaying ? "停止播放" : "完整播放录音") {
                            capture.playOrStop()
                        }
                    }
                    if let message = capture.message {
                        Text(message).font(.footnote).foregroundStyle(.secondary)
                    }
                }

                Section("上传与处理") {
                    Button("上传这段录音") {
                        Task { await flow.uploadAndProcess(fileURL: capture.fileURL, recordedAt: capture.recordedAt) }
                    }
                    .disabled(capture.fileURL == nil || capture.isRecording || flow.isBusy)
                    if flow.isBusy { ProgressView("正在上传或等待处理") }
                    LabeledContent("状态", value: stageTitle(flow.stage))
                    if let id = flow.lastEpisodeID {
                        LabeledContent("Episode ID", value: id)
                            .font(.caption)
                            .textSelection(.enabled)
                        Button("刷新这条 Episode") {
                            Task { await flow.refreshLastEpisode() }
                        }
                        .disabled(flow.isBusy)
                    }
                    if let message = flow.message {
                        Text(message).font(.footnote)
                            .foregroundStyle(flow.stage == "failed" ? .red : .secondary)
                    }
                }
            }
            .navigationTitle("记录生活")
        }
    }

    private func duration(_ seconds: TimeInterval) -> String {
        let whole = max(0, Int(seconds))
        return String(format: "%02d:%02d", whole / 60, whole % 60)
    }

    private func stageTitle(_ stage: String) -> String {
        switch stage {
        case "idle": return "尚未上传"
        case "uploading": return "上传中"
        case "uploaded": return "已上传"
        case "transcribing": return "转录中"
        case "extracting": return "提取记忆中"
        case "modeling": return "整理结果中"
        case "ready": return "已完成"
        case "failed": return "失败"
        default: return stage
        }
    }
}

private struct MemoriesView: View {
    @EnvironmentObject private var flow: EpisodeFlow

    var body: some View {
        NavigationStack {
            List {
                if let id = flow.lastEpisodeID {
                    Section("来源") {
                        LabeledContent("Episode", value: id)
                            .textSelection(.enabled)
                        if let version = flow.modelVersion {
                            LabeledContent("模型版本", value: version)
                        }
                    }
                }
                if flow.memories.isEmpty {
                    ContentUnavailableView(
                        "暂无记忆", systemImage: "books.vertical",
                        description: Text("录音上传并完成处理后，这里显示 Backend 返回的真实 Memory。")
                    )
                } else {
                    Section("提取结果") {
                        ForEach(flow.memories) { item in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item.content)
                                    .font(.body)
                                Text("\(item.memoryType) · \(item.sourceType) · 置信度 \(Int(item.confidence * 100))%")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("证据：\(item.evidenceIds.joined(separator: ", "))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
            .navigationTitle("我的记忆")
            .toolbar {
                if flow.lastEpisodeID != nil {
                    Button("刷新") { Task { await flow.refreshLastEpisode() } }
                        .disabled(flow.isBusy)
                }
            }
        }
    }
}

private struct ConnectionView: View {
    @EnvironmentObject private var flow: EpisodeFlow

    var body: some View {
        NavigationStack {
            Form {
                Section("本地开发连接") {
                    TextField("Backend 根地址", text: $flow.settings.baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    SecureField("Actor 令牌", text: $flow.settings.token)
                        .textInputAutocapitalization(.never)
                    TextField("Subject ID", text: $flow.settings.subjectID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("录音同意 ID", text: $flow.settings.recordingConsentID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("保存连接设置") { flow.saveSettings() }
                        .disabled(flow.isBusy)
                    Text("令牌保存在 iOS 钥匙串。模拟器可用 127.0.0.1；真机需要能访问 Mac 的私有网络地址或 HTTPS 服务。")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("明确同意") {
                    Text("确认你有权为此 Subject 录音。录音同意只允许 Capture，不授权 Voice Clone。")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("我确认并登记录音同意") {
                        Task { await flow.grantRecordingConsent() }
                    }
                    .disabled(flow.isBusy || flow.settings.token.isEmpty || flow.settings.subjectID.isEmpty)
                }
                if let message = flow.message {
                    Section { Text(message).font(.footnote) }
                }
            }
            .navigationTitle("连接 Backend")
        }
    }
}

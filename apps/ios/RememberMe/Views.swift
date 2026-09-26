import SwiftUI
import AVFoundation
import UIKit

private enum Ink {
    static let paper = Color(red: 0.98, green: 0.965, blue: 0.937)
    static let cream = Color(red: 1, green: 0.992, blue: 0.975)
    static let text = Color(red: 0.25, green: 0.20, blue: 0.17)
    static let muted = Color(red: 0.52, green: 0.46, blue: 0.42)
    static let coral = Color(red: 0.71, green: 0.32, blue: 0.25)
    static let peach = Color(red: 0.94, green: 0.85, blue: 0.79)
    static let olive = Color(red: 0.43, green: 0.49, blue: 0.35)
}

private extension View {
    func journalCard() -> some View {
        self.padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Ink.cream, in: RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(Ink.peach.opacity(0.55), lineWidth: 1))
    }
}

private struct Eyebrow: View {
    let text: String
    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .tracking(2)
            .foregroundStyle(Ink.coral)
    }
}

private struct ActionButton: View {
    let title: String
    let icon: String
    var fill: Color = Ink.coral
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(.system(size: 16, weight: .semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 17)
        }
        .buttonStyle(.plain)
        .foregroundStyle(.white)
        .background(fill, in: RoundedRectangle(cornerRadius: 18))
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        Group {
            if model.pairing == nil { PairingView() }
            else { MainTabs() }
        }
        .tint(Ink.coral)
        .preferredColorScheme(.light)
        .alert("需要留意", isPresented: Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
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

private struct PairingView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 23) {
                Spacer(minLength: 45)
                Image(systemName: "sparkle")
                    .font(.system(size: 35, weight: .light))
                    .foregroundStyle(Ink.coral)
                    .frame(width: 72, height: 72)
                    .background(Ink.peach.opacity(0.55), in: RoundedRectangle(cornerRadius: 22))
                Eyebrow(text: "REMEMBER ME · 私人手记")
                Text("把说过的话，\n慢慢变成懂你的记忆。")
                    .font(.system(size: 36, weight: .regular, design: .serif))
                    .foregroundStyle(Ink.text)
                    .fixedSize(horizontal: false, vertical: true)
                Text("录音只在你的手机与本机 Mac 之间传送。先用一次性配对码连接，再由你决定什么时候开始录。")
                    .font(.system(size: 15))
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
                    .font(.footnote)
                    .foregroundStyle(Ink.muted)
                ActionButton(title: model.isBusy ? "正在连接…" : "安全连接", icon: "lock.shield") {
                    Task { await model.connect() }
                }
                .disabled(model.isBusy)
            }
            .padding(24)
        }
        .background(Ink.paper.ignoresSafeArea())
    }
}

private struct MainTabs: View {
    var body: some View {
        TabView {
            NavigationStack { HomeView() }
                .tabItem { Label("今天", systemImage: "sun.max") }
            NavigationStack { EpisodesView() }
                .tabItem { Label("录音", systemImage: "waveform") }
            NavigationStack { MemoriesView() }
                .tabItem { Label("记忆", systemImage: "book.closed") }
            NavigationStack { ModelView() }
                .tabItem { Label("关于我", systemImage: "person.crop.circle") }
        }
        .background(Ink.paper)
    }
}

private struct EpisodesView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                Eyebrow(text: "每一段原音都在")
                Text("声音档案")
                    .font(.system(size: 31, design: .serif))
                    .foregroundStyle(Ink.text)
                if model.episodes.isEmpty {
                    Text("这里会保存你录下的原音和转写。即使没有抽出记忆，录音仍然在。")
                        .foregroundStyle(Ink.muted)
                        .journalCard()
                }
                ForEach(model.episodes) { episode in
                    NavigationLink { EpisodeDetailView(initial: episode) } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            Eyebrow(text: episode.recorded_at.prefix(10).description)
                            Text(episode.transcript?.isEmpty == false ? (episode.transcript ?? "") : "一段正在等待处理的录音")
                                .font(.system(size: 19, design: .serif))
                                .foregroundStyle(Ink.text)
                                .lineLimit(3)
                                .multilineTextAlignment(.leading)
                            Text(episode.status == "ready" ? "已完成 · 点击播放原音" : "状态：\(episode.status)")
                                .font(.footnote)
                                .foregroundStyle(episode.status == "failed" ? Ink.coral : Ink.muted)
                        }
                        .journalCard()
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(20)
        }
        .background(Ink.paper.ignoresSafeArea())
        .navigationTitle("录音")
        .refreshable { await model.refresh() }
    }
}

private struct EpisodeDetailView: View {
    @EnvironmentObject private var model: AppModel
    let initial: EpisodeRecord
    private var episode: EpisodeRecord { model.episodes.first(where: { $0.id == initial.id }) ?? initial }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Eyebrow(text: "原始 Episode · \(episode.status)")
                Text("这一段，\n完整地留着。")
                    .font(.system(size: 31, design: .serif))
                    .foregroundStyle(Ink.text)
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "原音")
                    ActionButton(title: "播放原始录音", icon: "play.circle") {
                        Task { await model.playOriginal(episodeID: episode.id) }
                    }
                    Text("录入时间：\(episode.recorded_at)")
                        .font(.footnote).foregroundStyle(Ink.muted)
                }
                .journalCard()
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "原始转写")
                    Text(episode.transcript ?? "还没有转写。原音已保存，可以稍后再看。")
                        .font(.system(size: 19, design: .serif))
                        .foregroundStyle(Ink.text)
                    Text("STT：\(episode.stt_model_version ?? "等待中") · AI：\(episode.model_version ?? "等待中")")
                        .font(.caption)
                        .foregroundStyle(Ink.muted)
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
        .background(Ink.paper.ignoresSafeArea())
        .navigationTitle("录音详情")
        .refreshable { await model.refresh() }
    }
}

private struct HomeView: View {
    @EnvironmentObject private var model: AppModel
    @State private var showRecorder = false
    @State private var selectedQuestion: QuestionRecord?
    private let speaker = AVSpeechSynthesizer()
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 23) {
                HStack {
                    VStack(alignment: .leading, spacing: 5) {
                        Eyebrow(text: Date().formatted(.dateTime.month(.wide).day()))
                        Text("慢慢说，我在听。")
                            .font(.system(size: 31, design: .serif))
                            .foregroundStyle(Ink.text)
                    }
                    Spacer()
                    Image(systemName: "circle.hexagongrid.fill")
                        .font(.system(size: 28, weight: .ultraLight))
                        .foregroundStyle(Ink.coral)
                }
                .padding(.top, 12)

                VStack(alignment: .leading, spacing: 15) {
                    Eyebrow(text: "你的声音，属于你")
                    Text("今天想留下什么？")
                        .font(.system(size: 26, design: .serif))
                        .foregroundStyle(Ink.text)
                    Text("一个念头、一段经历，或只是此刻的心情，都可以从这里开始。")
                        .font(.subheadline)
                        .foregroundStyle(Ink.muted)
                    ActionButton(title: "开始自由录音", icon: "waveform") {
                        selectedQuestion = nil
                        showRecorder = true
                    }
                }
                .journalCard()

                if let question = model.questions.first {
                    VStack(alignment: .leading, spacing: 16) {
                        Eyebrow(text: "给你的一个小问题")
                        Text(question.text)
                            .font(.system(size: 23, design: .serif))
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
                    .journalCard()
                }

                if model.draft != nil || model.episodeID != nil {
                    VStack(alignment: .leading, spacing: 12) {
                        Eyebrow(text: "未完成的记录")
                        Text(model.processingStatus.isEmpty ? "录音保存在手机里，随时可以继续。" : "正在处理：\(model.processingStatus)")
                            .font(.subheadline)
                            .foregroundStyle(Ink.text)
                        Button("继续查看或重试") { showRecorder = true }
                            .font(.subheadline.weight(.semibold))
                    }
                    .journalCard()
                }

                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 5) {
                        Eyebrow(text: "正在认识你")
                        Text("\(model.memories.count) 条记忆")
                            .font(.system(size: 23, design: .serif))
                            .foregroundStyle(Ink.text)
                    }
                    Spacer()
                    Text("模型 v\(model.modelVersion)")
                        .font(.footnote)
                        .foregroundStyle(Ink.muted)
                }
                .journalCard()
            }
            .padding(20)
        }
        .background(Ink.paper.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .sheet(isPresented: $showRecorder) { RecorderView(question: selectedQuestion) }
        .refreshable { await model.refresh() }
    }
}

private struct RecorderView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let question: QuestionRecord?
    @State private var showConsent = false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Eyebrow(text: question == nil ? "自由录音" : "回答这个问题")
                    Text(question?.text ?? "把此刻，\n留在这里。")
                        .font(.system(size: 32, design: .serif))
                        .foregroundStyle(Ink.text)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 7) {
                        ForEach(0..<27, id: \.self) { index in
                            Capsule()
                                .fill(index.isMultiple(of: 4) ? Ink.coral : Ink.peach)
                                .frame(width: 5, height: CGFloat(20 + (index * 17) % 56))
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 100)
                    .journalCard()
                    Text(String(format: "%02d:%02d", model.recordedSeconds / 60, model.recordedSeconds % 60))
                        .font(.system(size: 45, weight: .light, design: .monospaced))
                        .foregroundStyle(Ink.text)
                        .frame(maxWidth: .infinity)
                    if model.isRecording {
                        HStack(spacing: 12) {
                            Button(model.isPaused ? "继续" : "暂停") { model.pauseOrResume() }
                                .buttonStyle(.bordered)
                            ActionButton(title: "完成录音", icon: "stop.fill") { model.finishRecording() }
                        }
                    } else if model.draft != nil {
                        VStack(spacing: 12) {
                            Button { model.togglePlayback() } label: {
                                Label(model.isPlaying ? "停止播放" : "播放手机里的原音", systemImage: model.isPlaying ? "stop.circle" : "play.circle")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            ActionButton(title: model.isBusy ? "正在提交…" : "保存并生成记忆", icon: "arrow.up.heart") {
                                Task { await model.sendRecording() }
                            }
                            .disabled(model.isBusy)
                        }
                    } else {
                        ActionButton(title: "开始录音", icon: "mic.fill") {
                            showConsent = true
                        }
                    }
                    if !model.processingStatus.isEmpty {
                        Text("处理进度：\(model.processingStatus)")
                            .font(.subheadline)
                            .foregroundStyle(Ink.olive)
                    }
                    Text("原音先保存在这台 iPhone。网络中断时可以重试，同一段录音不会重复创建记录。")
                        .font(.footnote)
                        .foregroundStyle(Ink.muted)
                }
                .padding(24)
            }
            .background(Ink.paper.ignoresSafeArea())
            .navigationTitle("留下一段声音")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) {
                Button("完成") {
                    if model.isRecording { model.finishRecording() }
                    dismiss()
                }
            } }
            .confirmationDialog("开始录下这段声音？", isPresented: $showConsent) {
                Button("同意并开始录音") {
                    Task { await model.startRecording(questionID: question?.id) }
                }
                Button("取消", role: .cancel) { }
            } message: {
                Text("原音会先留在这台 iPhone，提交后只传给你配对的本机 Mac。你可以暂停或结束录音。")
            }
        }
    }
}

private struct MemoriesView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                Eyebrow(text: "有据可循的记忆")
                Text("说过的话，留下痕迹。")
                    .font(.system(size: 30, design: .serif))
                    .foregroundStyle(Ink.text)
                if model.memories.isEmpty {
                    Text("还没有记忆。试着录下第一段真实的故事。")
                        .foregroundStyle(Ink.muted)
                        .journalCard()
                }
                ForEach(model.memories) { memory in
                    NavigationLink { MemoryDetailView(memory: memory) } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            Eyebrow(text: memory.domain ?? memory.memory_type)
                            Text(memory.content)
                                .font(.system(size: 20, design: .serif))
                                .foregroundStyle(Ink.text)
                                .multilineTextAlignment(.leading)
                            Text(memory.evidence.first?.excerpt ?? "查看来源")
                                .font(.footnote)
                                .foregroundStyle(Ink.muted)
                                .lineLimit(2)
                        }
                        .journalCard()
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(20)
        }
        .background(Ink.paper.ignoresSafeArea())
        .navigationTitle("记忆")
        .refreshable { await model.refresh() }
    }
}

private struct MemoryDetailView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let memory: MemoryRecord
    @State private var correction = ""
    @State private var showDelete = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Eyebrow(text: "记忆 · \(memory.domain ?? memory.memory_type)")
                Text(memory.content)
                    .font(.system(size: 29, design: .serif))
                    .foregroundStyle(Ink.text)
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "当时你说")
                    Button { Task { await model.playOriginal(memory) } } label: {
                        Label("播放原始录音", systemImage: "play.circle")
                    }
                    .buttonStyle(.bordered)
                    ForEach(memory.evidence) { evidence in
                        Text("“\(evidence.excerpt ?? "")”")
                            .font(.system(size: 19, design: .serif))
                            .foregroundStyle(Ink.text)
                    }
                    Text("原始转写：\(memory.transcript ?? "暂无")")
                        .font(.footnote)
                        .foregroundStyle(Ink.muted)
                    Text("录入：\(memory.recorded_at) · STT \(memory.stt_model_version ?? "未知") · AI \(memory.model_version)")
                        .font(.caption2)
                        .foregroundStyle(Ink.muted)
                }
                .journalCard()
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "如果我理解错了")
                    TextField("写下正确的说法", text: $correction, axis: .vertical)
                        .lineLimit(3...6)
                        .textFieldStyle(.roundedBorder)
                    ActionButton(title: "保存纠正", icon: "checkmark") {
                        Task { await model.correct(memory, to: correction); dismiss() }
                    }
                    .disabled(correction.trimmingCharacters(in: .whitespaces).isEmpty)
                    Button("删除这条记忆", role: .destructive) { showDelete = true }
                        .font(.footnote)
                }
                .journalCard()
            }
            .padding(20)
        }
        .background(Ink.paper.ignoresSafeArea())
        .navigationTitle("记忆详情")
        .confirmationDialog("删除这条记忆？原始录音和纠错记录仍会保留。", isPresented: $showDelete) {
            Button("删除记忆", role: .destructive) {
                Task { await model.delete(memory); dismiss() }
            }
        }
    }
}

private struct ModelView: View {
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
                    .font(.system(size: 31, design: .serif))
                    .foregroundStyle(Ink.text)
                Text("七个维度会随着你的叙述慢慢丰富。矛盾的记忆会一起保留，等你确认。")
                    .font(.subheadline)
                    .foregroundStyle(Ink.muted)
                ForEach(model.domains) { domain in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text(names[domain.domain] ?? domain.domain)
                                .font(.system(size: 22, design: .serif))
                                .foregroundStyle(Ink.text)
                            Spacer()
                            Text("\(domain.traits.count)")
                                .foregroundStyle(Ink.coral)
                        }
                        if domain.traits.isEmpty {
                            Text("还没有足够的记录，留待以后慢慢补上。")
                                .font(.footnote)
                                .foregroundStyle(Ink.muted)
                        }
                        ForEach(domain.traits) { trait in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(trait.statement)
                                    .font(.subheadline)
                                    .foregroundStyle(Ink.text)
                                if trait.status == "unresolved" {
                                    Label("有不同说法，等待确认", systemImage: "questionmark.circle")
                                        .font(.footnote)
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
        .background(Ink.paper.ignoresSafeArea())
        .navigationTitle("关于我")
        .refreshable { await model.refresh() }
    }
}

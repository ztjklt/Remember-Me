import SwiftUI
import AVFoundation
import UIKit

enum Ink {
    static let paper = Color("RmBackground")
    static let cream = Color("RmSurface")
    static let text = Color("RmText")
    static let muted = Color("RmMuted")
    static let coral = Color("RmPrimary")
    static let peach = Color("RmSoft")
    static let olive = Color("RmPrimary")
    static let onPrimary = Color("RmOnPrimary")
}

private struct PressFeedbackStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isEnabled) private var enabled
    let fill: Color
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(Ink.onPrimary)
            .background(fill, in: RoundedRectangle(cornerRadius: 16))
            .background {
                RoundedRectangle(cornerRadius: 16)
                    .shadow(color: Ink.coral.opacity(enabled ? 0.20 : 0), radius: configuration.isPressed ? 2 : 5, y: configuration.isPressed ? 1 : 3)
            }
            .overlay {
                RoundedRectangle(cornerRadius: 16)
                    .fill(LinearGradient(colors: [Color.white.opacity(configuration.isPressed ? 0 : 0.10), Color.black.opacity(configuration.isPressed ? 0.12 : 0.03)], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .allowsHitTesting(false)
            }
            .opacity(enabled ? 1 : 0.5)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.985 : 1)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.10), value: configuration.isPressed)
    }
}

private struct AtmosphereBackground: View {
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    private var dark: Bool { scheme == .dark }
    private func color(_ light: UInt32, _ night: UInt32) -> Color {
        let value = dark ? night : light
        return Color(red: Double((value >> 16) & 255)/255, green: Double((value >> 8) & 255)/255, blue: Double(value & 255)/255)
    }
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Ink.paper
                if !reduceTransparency && contrast != .increased {
                    LinearGradient(colors: [color(0xD7E3F3,0x22324B), color(0xEEE5DE,0x202C34)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    RadialGradient(colors: [color(0xE6DFF0,0x302B43),color(0xE6DFF0,0x302B43).opacity(0)], center: UnitPoint(x: 1,y: 0.15), startRadius: 0, endRadius: max(geometry.size.width,geometry.size.height)*0.5)
                    LinearGradient(stops: [.init(color: Ink.paper.opacity(0),location: 0),.init(color: Ink.paper.opacity(0.3),location: 0.28),.init(color: Ink.paper,location: 0.68),.init(color: Ink.paper,location: 1)], startPoint: .top, endPoint: .bottom)
                }
            }
        }.allowsHitTesting(false).accessibilityHidden(true)
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

private func sourceLabel(_ source: String) -> String {
    switch source {
    case "SUBJECT": return "本人叙述"
    case "THIRD_PARTY": return "他人提供"
    case "AI_INFERENCE": return "AI 推测"
    default: return "来源待核对"
    }
}

private extension View {
    func journalCard() -> some View {
        self.padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
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
    @Environment(\.colorScheme) private var colorScheme
    private var darkBackground: Bool { colorScheme == .dark }
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
                    let blue = darkBackground ? Color(red: 174/255, green: 196/255, blue: 1) : Color(red: 50/255, green: 92/255, blue: 203/255)
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
                    context.fill(heart, with: .color(mono ? monochromeColor : Color(red: 233/255, green: 184/255, blue: 91/255)))
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
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(.system(.body, design: .default).weight(.medium))
                .frame(maxWidth: .infinity)
                .padding(16)
                .frame(minHeight: 56)
        }
        .buttonStyle(PressFeedbackStyle(fill: fill))
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        Group {
            AndroidParityTabs()
        }
        .tint(Ink.coral)
        .sheet(isPresented: $model.showConnection) {
            NavigationStack {
                PairingView().toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("关闭") { model.showConnection = false }
                    }
                }
            }
        }
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
            NavigationStack { TwinView() }.tabItem { Label("对话", systemImage: "bubble.left.and.bubble.right") }
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
                NavigationLink("个人声音与独立授权") { ScrollView { VoiceSetupView().padding(20) }.navigationTitle("个人声音") }
                if model.cloudConsentID != nil {
                    Button("撤销云端对话授权", role: .destructive) { Task { await model.revokeCloudTwin() } }
                }
                Button("管理系统麦克风权限") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                }
            }
            Section("外观") { LabeledContent("颜色与字号", value: "跟随系统") }
            Section("连接") { Text(model.pairing == nil ? "尚未配对" : "已配对本机服务") }
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
                    Text(statusLabel(episode.status)).font(.subheadline)
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
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Eyebrow(text: "原始录音 · \(statusLabel(episode.status))")
                Text("这一段，\n完整地留着。")
                    .font(.system(.title, design: .default).weight(.semibold))
                    .foregroundStyle(Ink.text)
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "原音")
                    OriginalPlayer(episodeID: episode.id)
                    Text("录入时间：\(episode.recorded_at)")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                }
                .journalCard()
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow(text: "原始转写")
                    Text(episode.transcript ?? "还没有转写。原音已保存，可以稍后再看。")
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
        .navigationTitle("录音详情")
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
    @State private var showConsent = false
    @State private var showClose = false
    @State private var showOrganizeConsent = false
    @State private var showPairing = false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Eyebrow(text: calibration != nil ? "本人校准回答" : question == nil ? "自由录音" : "回答这个问题")
                    Text(calibration?.question ?? question?.text ?? "把此刻，留在这里。")
                        .font(.title2.weight(.medium)).foregroundStyle(Ink.text)
                    Text(model.isRecording ? (model.isPaused ? "已暂停" : "正在录音") : model.draft != nil ? "录音已保存在手机" : "由你决定什么时候开始")
                        .foregroundStyle(Ink.muted).accessibilityAddTraits(.updatesFrequently)
                    Text(String(format: "%02d:%02d", model.recordedSeconds / 60, model.recordedSeconds % 60))
                        .font(.system(.largeTitle, design: .monospaced)).monospacedDigit()
                        .frame(maxWidth: .infinity)
                    GeometryReader { geometry in
                        HStack(spacing: 4) {
                            ForEach(Array(model.meterLevels.enumerated()), id: \.offset) { _, level in
                                Capsule().fill(Ink.coral)
                                    .frame(width: max(1, (geometry.size.width - CGFloat(max(0, model.meterLevels.count - 1)) * 4) / CGFloat(max(1, model.meterLevels.count))), height: 8 + 72 * level)
                            }
                        }.frame(height: 100)
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 130)
                    .frame(maxWidth: .infinity)
                    .accessibilityHidden(true)
                    .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: model.meterLevels)
                    if model.draft != nil && !model.isRecording { OriginalPlayer(episodeID: nil) }
                    if let draft = model.draft, !model.isRecording, model.episodeID == nil {
                        NavigationLink("查看本机录音与离线转写") { LocalRecordingDetailView(recordingID: draft.id) }
                            .accessibilityIdentifier("recorder.localDetail")
                    }
                    if model.isTranscriptReviewReady {
                        Text("先核对，再整理记忆").font(.title3.weight(.semibold))
                        Text("修改识别不准确的地方。确认后才会把文字发送给 DeepSeek 提取记忆。").foregroundStyle(Ink.muted)
                        TextEditor(text: $model.transcriptDraft)
                            .onChange(of: model.transcriptDraft) { _, _ in model.saveTranscriptDraft() }
                            .frame(minHeight: 220).padding(12)
                            .background(Ink.cream, in: RoundedRectangle(cornerRadius: 16))
                            .accessibilityLabel("核对并修改转写文字")
                    }
                    if !model.processingStatus.isEmpty {
                        Text(statusLabel(model.processingStatus)).foregroundStyle(Ink.coral)
                    }
                    if let error = model.errorMessage {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("操作未完成", systemImage: "exclamationmark.circle").font(.headline)
                            Text(error).font(.body)
                        }.padding(16).background(Ink.cream, in: RoundedRectangle(cornerRadius: 16))
                    }
                    Text("原音先留在手机。提交后传给配对的 Mac 转写；网络中断时可以重试，无需重录。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                }.padding(20)
            }
            .background(AtmosphereBackground().ignoresSafeArea())
            .navigationTitle("留下一段声音").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) {
                Button("关闭") { if model.isRecording { showClose = true } else { dismiss() } }
            } }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 10) {
                    if model.isRecording {
                        Button(model.isPaused ? "继续录音" : "暂停录音") { model.pauseOrResume() }
                            .frame(minHeight: 44).buttonStyle(.bordered)
                        ActionButton(title: "完成并保存", icon: "stop.fill") { model.finishRecording() }
                    } else if model.isTranscriptReviewReady {
                        ActionButton(title: model.isBusy ? "正在提交…" : "确认文字并整理记忆", icon: "checkmark.circle") {
                            showOrganizeConsent = true
                        }.disabled(model.isBusy || model.transcriptDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    } else if model.draft != nil {
                        ActionButton(title: model.isBusy || model.isPollingEpisode ? "正在处理…" : model.pairing == nil ? "连接服务后转写" : "提交并转成文字", icon: "text.bubble") {
                            if model.pairing == nil { showPairing = true }
                            else { Task { await model.sendRecording() } }
                        }.disabled(model.isBusy || model.isPollingEpisode || model.isLocalTranscribing)
                        Button("保留这段，再录一段") {
                            if model.prepareNewRecording() { showConsent = true }
                        }.buttonStyle(.bordered).disabled(model.isBusy || model.isPollingEpisode || model.isLocalTranscribing)
                    } else {
                        ActionButton(title: "开始录音", icon: "mic.fill") { showConsent = true }
                    }
                }.padding(16).background(Ink.cream)
            }
            .sheet(isPresented: $showPairing) {
                NavigationStack {
                    PairingView().toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("关闭") { showPairing = false }
                        }
                    }
                    .onChange(of: model.pairing?.baseURL) { _, url in
                        if url != nil { showPairing = false }
                    }
                }
            }
            .interactiveDismissDisabled(model.isRecording)
            .onChange(of: scenePhase) { _, phase in
                if phase == .background { model.finishRecording(); model.pausePlayback() }
            }
            .task { if model.episodeID != nil { await model.pollEpisode() } }
            .confirmationDialog("开始录下这段声音？", isPresented: $showConsent, titleVisibility: .visible) {
                Button("同意并开始录音") { Task { await model.startRecording(questionID: question?.id, calibrationID: calibration?.id) } }
                Button("取消", role: .cancel) { }
            } message: {
                Text("原音先留在手机。提交后传给配对的 Mac 转写，确认文字后才交给 DeepSeek 整理。")
            }
            .confirmationDialog("要结束这段录音吗？", isPresented: $showClose, titleVisibility: .visible) {
                Button("完成并保存") { model.finishRecording(); dismiss() }
                Button("继续录音", role: .cancel) { }
            }
            .confirmationDialog("确认文字并整理记忆？", isPresented: $showOrganizeConsent, titleVisibility: .visible) {
                Button("同意并整理") { Task { await model.submitTranscript() } }
                Button("暂不整理，只保留文字", role: .cancel) { model.saveTranscriptDraft() }
            } message: {
                Text("配对的 Mac 会把你核对后的文字发送给 DeepSeek 提取记忆。原始录音不随本次操作发送给该服务。")
            }
        }
    }
}

private struct OriginalPlayer: View {
    @EnvironmentObject private var model: AppModel
    let episodeID: String?
    private var identity: String { episodeID ?? model.draft?.id ?? "" }
    private var selected: Bool { model.playbackID == identity }
    private func clock(_ seconds: Double) -> String { String(format: "%02d:%02d",Int(seconds)/60,Int(seconds)%60) }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("原始录音").font(.body.weight(.medium))
                    Text(model.playbackLoading ? "正在打开原音…" : selected && model.isPlaying ? "正在播放" : selected && model.playbackDuration > 0 && model.playbackPosition >= model.playbackDuration ? "播放完毕" : selected && model.playbackPosition > 0 ? "已暂停" : "准备好回听")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                }.frame(maxWidth: .infinity,alignment: .leading)

                Button {
                    if selected { model.toggleCurrentPlayback() }
                    else if let episodeID { Task { await model.playOriginal(episodeID: episodeID) } }
                    else { model.togglePlayback() }
                } label: {
                    Group {
                        if model.playbackLoading { ProgressView().tint(Ink.paper) }
                        else { Image(systemName: selected && model.isPlaying ? "pause.fill" : "play.fill") }
                    }.frame(width: 48, height: 48)
                }
                .buttonStyle(.borderedProminent).tint(Ink.text).foregroundStyle(Ink.paper).clipShape(Circle())
                .disabled(model.playbackLoading)
                .accessibilityLabel(selected && model.isPlaying ? "暂停原音" : "播放原音")

            }
            if selected {
                Slider(value: Binding(get: { model.playbackPosition }, set: { model.seekPlayback($0) }), in: 0...max(1, model.playbackDuration))
                    .frame(minHeight: 44).accessibilityLabel("原音播放进度")
                HStack { Text(clock(model.playbackPosition)); Spacer(); Text(clock(model.playbackDuration)) }.font(.subheadline).foregroundStyle(Ink.muted).monospacedDigit()
            }
        }.padding(16).background(Ink.cream, in: RoundedRectangle(cornerRadius: 16))
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
    @State private var showCalibrationRecorder = false
    private let dimensionNames = ["DECISION": "做决定", "REASONING": "考虑理由",
                                  "VALUE_PRIORITY": "价值优先", "EMOTIONAL_REACTION": "情绪反应",
                                  "EXPRESSION": "表达方式"]
    private let alignmentNames = ["MATCH": "相近", "PARTIAL": "部分相近",
                                  "DIFFERENT": "有差异", "NOT_OBSERVED": "尚未提及"]
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Eyebrow(text: "EVIDENCE TWIN")
                Text("问一个关于自己的问题。")
                    .font(.system(.title, design: .default).weight(.semibold))
                    .foregroundStyle(Ink.text)
                Text("RM 会先找你真正说过的话；需要推测时会明确标出来，不知道时会说不知道。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
                if model.pairing == nil { ConnectionNotice() }
                else if model.cloudConsentID == nil {
                    VStack(alignment: .leading, spacing: 12) {
                        Eyebrow(text: "先决定资料如何使用")
                        Text("提问时，问题和少量相关记忆文字会发送给 DeepSeek；若你使用校准，核对后的本人回答文字和锁定的 Twin 回答也会发送去比较。原始录音和声音样本不会发送。")
                            .font(.subheadline).foregroundStyle(Ink.text)
                        ActionButton(title: "同意使用云端 Twin", icon: "checkmark.shield") {
                            Task { await model.enableCloudTwin() }
                        }
                    }
                    .journalCard()
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        Eyebrow(text: "你的问题")
                        TextEditor(text: $model.queryDraft)
                            .frame(minHeight: 100)
                            .padding(8)
                            .background(Ink.paper, in: RoundedRectangle(cornerRadius: 14))
                            .accessibilityLabel("核对或修改 Twin 问题")
                        Button {
                            Task {
                                if model.isQueryRecording { await model.finishAuxiliaryRecording() }
                                else { await model.startQueryRecording() }
                            }
                        } label: {
                            Label(model.isQueryRecording ? "结束并识别问题" : "说出问题",
                                  systemImage: model.isQueryRecording ? "stop.circle" : "mic")
                        }
                        .buttonStyle(.bordered)
                        ActionButton(title: model.isBusy ? "正在查找证据…" : "提问", icon: "sparkle.magnifyingglass") {
                            Task { await model.askTwin() }
                        }
                        .disabled(model.isBusy || model.queryDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    .journalCard()
                    Button("撤销云端 Twin 授权", role: .destructive) {
                        Task { await model.revokeCloudTwin() }
                    }
                    .font(.subheadline)
                }
                if let answer = model.twinAnswer {
                    VStack(alignment: .leading, spacing: 13) {
                        Eyebrow(text: answer.response_type == "ORIGINAL" ? "原话" :
                                answer.response_type == "SIMULATION" ? "根据记忆推测" : "目前无法确定")
                        Text(answer.answer)
                            .font(.system(.title3, design: .default).weight(.semibold))
                            .foregroundStyle(Ink.text)
                        if answer.stale {
                            Label("相关记忆已有变化，请重新提问。", systemImage: "arrow.clockwise")
                                .font(.subheadline).foregroundStyle(Ink.coral)
                        }
                        ForEach(answer.evidence) { source in
                            VStack(alignment: .leading, spacing: 6) {
                                Text("证据：“\(source.excerpt ?? "")”")
                                    .font(.subheadline).foregroundStyle(Ink.muted)
                                Button("听当时的原始录音") {
                                    Task { await model.playOriginal(episodeID: source.episode_id) }
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                        if answer.response_type != "UNKNOWN" && !answer.stale {
                            if model.voiceProfileReady {
                                ActionButton(title: model.isBusy ? "正在生成声音…" : "用我的声音朗读",
                                             icon: "speaker.wave.2", fill: Ink.olive) {
                                    Task { await model.playTwinVoice() }
                                }
                                .disabled(model.isBusy)
                            } else {
                                Text("下方单独授权并录制声音样本后，可以点播个人声音。")
                                    .font(.subheadline).foregroundStyle(Ink.muted)
                            }
                        }
                        Text("Person Model v\(answer.person_model_version) · \(answer.model_version)")
                            .font(.subheadline).foregroundStyle(Ink.muted)
                    }
                    .journalCard()
                    if answer.response_type != "UNKNOWN" && !answer.stale &&
                        model.calibrationRun?.twin_answer_id != answer.id {
                        Text("校准会先锁定这条回答，再录下你的真实回答并核对文字；比较只使用确认后的文字。")
                            .font(.subheadline).foregroundStyle(Ink.muted)
                        Button("用这条回答做一次校准") {
                            Task { await model.startCalibration() }
                        }
                        .buttonStyle(.bordered)
                    }
                }
                if let run = model.calibrationRun {
                    VStack(alignment: .leading, spacing: 12) {
                        Eyebrow(text: "TWIN 校准 · \(run.status)")
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
                                        showCalibrationRecorder = true
                                    }
                                } else if model.episodes.first(where: { $0.id == run.human_episode_id })?.status == "ready" {
                                    ActionButton(title: model.isBusy ? "正在比较…" : "比较 Twin 和我的回答",
                                                 icon: "arrow.left.arrow.right") {
                                        Task { await model.completeCalibration(run.id) }
                                    }
                                    .disabled(model.isBusy)
                                } else {
                                    Text("回答已保存。请核对转写并等待记忆处理完成；之后可重试比较。")
                                        .font(.subheadline).foregroundStyle(Ink.muted)
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
                                    Button("继续追问：\(next)") { model.queryDraft = next }
                                        .font(.subheadline)
                                }
                                Text("比较模型：\(run.comparison_model_version ?? "未知")")
                                    .font(.subheadline).foregroundStyle(Ink.muted)
                            }
                        }
                    }
                    .journalCard()
                }
                VoiceSetupView()
            }
            .padding(20)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .navigationTitle("对话")
        .refreshable { await model.refresh() }
        .sheet(isPresented: $showCalibrationRecorder) {
            if let run = model.calibrationRun {
                RecorderView(question: nil, calibration: run)
            }
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
            if model.voiceProfileReady {
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
    var body: some View {
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
                    OriginalPlayer(episodeID: memory.episode_id)
                    Text("原始转写：\(memory.transcript ?? "暂无")")
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
                    TextField("写下正确的说法", text: $correction, axis: .vertical)
                        .lineLimit(3...6)
                        .textFieldStyle(.roundedBorder)
                    ActionButton(title: "保存纠正", icon: "checkmark") {
                        Task { if await model.correct(memory, to: correction) { dismiss() } }
                    }
                    .disabled(correction.trimmingCharacters(in: .whitespaces).isEmpty)
                    Button("删除这条记忆", role: .destructive) { showDelete = true }
                        .font(.subheadline)
                }
                .journalCard()
            }
            .padding(20)
        }
        .background(AtmosphereBackground().ignoresSafeArea())
        .navigationTitle("记忆详情")
        .confirmationDialog("删除这条记忆？原始录音和纠错记录仍会保留。", isPresented: $showDelete) {
            Button("删除记忆", role: .destructive) {
                Task { if await model.delete(memory) { dismiss() } }
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
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    private func color(_ day: UInt32,_ night: UInt32) -> Color {
        let v=scheme == .dark ? night : day
        return Color(red:Double((v>>16)&255)/255,green:Double((v>>8)&255)/255,blue:Double(v&255)/255)
    }
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
            let ink=color(0x385590,0xD0DFFA),paper=color(0xEDF2FB,0x536C99),end=color(0xCBD7EE,0x334565)
            for (role,path) in shapes where !(flat && role == "back") {
                if flat || role == "line" || role == "lightline" {
                    context.stroke(path,with:.color(flat || role == "line" ? ink : color(0xF6F8FC,0x253956)),style:StrokeStyle(lineWidth:flat ? 6 : 3,lineCap:.round,lineJoin:.round))
                } else {
                    var layer=context
                    if material && (role == "paper" || role == "blue") { layer.addFilter(.shadow(color:color(0x28426E,0x071326).opacity(0.2),radius:2.2,x:0,y:2.5)) }
                    if role == "paper" && material {
                        layer.fill(path,with:.linearGradient(Gradient(colors:[paper,end]),startPoint:.zero,endPoint:CGPoint(x:77,y:96)))
                    } else {
                        layer.fill(path,with:.color(role == "back" ? color(0xA4B9DF,0x354866).opacity(0.8) : role == "blue" ? color(0x567AC3,0xA3BCEB) : role == "gold" ? color(0xC39A4B,0xD4B06F) : paper))
                    }
                    if material && role == "paper" { var rim=context;rim.clip(to:path);rim.stroke(path,with:.color(color(0xF6F8FC,0x253956).opacity(0.55)),lineWidth:1.5) }
                }
            }
        }.frame(width:dimension,height:dimension).accessibilityLabel(Text(label ?? "")).accessibilityHidden(label == nil)
    }
}
// END GENERATED MEMORY GLYPHS

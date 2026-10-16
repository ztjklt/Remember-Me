import SwiftUI
import AVFoundation

struct GuestSource: Decodable, Identifiable {
    let episode_id: String
    let recorded_at: String
    let duration_ms: Int?
    let transcript: String
    let supplement: String?
    let memories: [String]
    var has_audio: Bool? = nil
    var hasAudio: Bool { has_audio ?? (duration_ms != nil) }
    var id: String { episode_id }
}
struct GuestScope: Decodable {
    let subject_id: String
    let subject_label: String
    let enabled: Bool
    let revision: Int
    let episode_ids: [String]
    let personal_voice_enabled: Bool
}
struct GuestPreview: Decodable {
    let source_version: String
    let episode_ids: [String]
    let includes_full_audio: Bool
    let notice: String
    let items: [GuestSource]
}
struct GuestDevice: Decodable {
    let entry_token: String
    let subject_id: String
    let subject_label: String
}
struct GuestSession: Decodable {
    let session_token: String?
    let session_id: String
    let subject_id: String
    let subject_label: String
    let expires_at: String
    let revision: Int
    let personal_voice_available: Bool
    let cloud_asr_policy: String?
    let speech_notice: String
    let default_voice_available: Bool
    let spoken_question_available: Bool
    var scope_version: String? = nil
    var entrustment: GuestEntrustmentAccess? = nil
}
struct GuestEntrustmentAccess: Decodable {
    let recipient_label: String
    let expires_at: String
}
private struct GuestGardenReply: Decodable { let revision: Int; let items: [GuestSource]; var scope_version: String? = nil }
private struct GuestSpokenReply: Decodable { let text: String; let answer: TwinAnswerRecord }

protocol GuestQuestionRecording {
    func start() throws
    func finish() -> Data
    func discard()
}
protocol GuestAudioPlaying { func stop() }
extension AVAudioPlayer: GuestAudioPlaying {}

/// Guest microphone samples exist only in RAM, including while recording.
private final class GuestQuestionMicrophone: GuestQuestionRecording, @unchecked Sendable {
    private let engine = AVAudioEngine()
    private let lock = NSLock()
    private var samples = Data()
    private var running = false
    private var converter: AVAudioConverter?
    private let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)!
    private static let maxBytes = 60 * 16000 * 2

    func start() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker])
        try session.setActive(true)
        let input = engine.inputNode
        let source = input.outputFormat(forBus: 0)
        guard source.sampleRate > 0, source.channelCount > 0,
              let conversion = AVAudioConverter(from: source, to: format) else { throw APIError.invalidResponse }
        converter = conversion
        lock.lock(); samples.removeAll(); running = true; lock.unlock()
        input.installTap(onBus: 0, bufferSize: 2048, format: source) { [weak self] buffer, _ in
            self?.append(buffer)
        }
        engine.prepare()
        do { try engine.start() }
        catch { discard(); throw error }
    }
    private func append(_ input: AVAudioPCMBuffer) {
        guard let converter else { return }
        let count = AVAudioFrameCount(ceil(Double(input.frameLength) * 16000 / input.format.sampleRate)) + 1
        guard let output = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: count) else { return }
        var supplied = false
        var failure: NSError?
        converter.convert(to: output, error: &failure) { _, status in
            if supplied { status.pointee = .noDataNow; return nil }
            supplied = true; status.pointee = .haveData; return input
        }
        guard failure == nil, let data = output.int16ChannelData?.pointee, output.frameLength > 0 else { return }
        lock.lock(); defer { lock.unlock() }
        guard running, samples.count < Self.maxBytes else { return }
        let bytes = min(Int(output.frameLength) * 2, Self.maxBytes - samples.count)
        samples.append(Data(bytes: data, count: bytes))
    }
    func finish() -> Data {
        engine.stop(); engine.inputNode.removeTap(onBus: 0)
        lock.lock(); defer { lock.unlock() }
        running = false
        let result = samples
        samples.removeAll(keepingCapacity: false)
        return result
    }
    func discard() { _ = finish() }
}

/// Holds only a device entry or a short-lived guest bearer. Never retains owner credentials.
@MainActor
final class GuestAccessModel: ObservableObject {
    @Published private(set) var session: GuestSession?
    @Published private(set) var sources: [GuestSource] = []
    @Published private(set) var chat = TwinChatHistory()
    @Published private(set) var isBusy = false
    @Published private(set) var isLocking = false
    @Published private(set) var isStartingRecording = false
    @Published private(set) var isRecording = false
    @Published private(set) var isPlaying = false
    @Published var question = ""
    @Published var entrustmentAttempt = false
    @Published var notice: String?
    private var entry: Pairing?
    private let apiFactory: ((String, String, String?) throws -> APIClient)?
    private let recordPermission: @MainActor () async -> Bool
    private let microphoneFactory: () -> any GuestQuestionRecording
    private let playAudio: (Data) throws -> any GuestAudioPlaying

    init(apiFactory: ((String, String, String?) throws -> APIClient)? = nil,
         microphoneFactory: (() -> any GuestQuestionRecording)? = nil,
         playAudio: ((Data) throws -> any GuestAudioPlaying)? = nil,
         recordPermission: @escaping @MainActor () async -> Bool = {
             await withCheckedContinuation { continuation in
                 AVAudioApplication.requestRecordPermission { continuation.resume(returning: $0) }
             }
         }) {
        self.apiFactory = apiFactory
        self.recordPermission = recordPermission
        self.microphoneFactory = microphoneFactory ?? { GuestQuestionMicrophone() }
        self.playAudio = playAudio ?? { bytes in
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.playback, mode: .spokenAudio)
            try audio.setActive(true)
            let next = try AVAudioPlayer(data: bytes)
            guard next.prepareToPlay(), next.play() else { throw APIError.invalidResponse }
            return next
        }
        // Temporary microphone files are never restored as conversations after a crash.
        let directory = FileManager.default.temporaryDirectory
        for file in (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
            where file.lastPathComponent.hasPrefix("guest-question-") { try? FileManager.default.removeItem(at: file) }
    }
    private func makeAPI(_ entry: Pairing, token: String? = nil) throws -> APIClient {
        if let apiFactory { return try apiFactory(entry.baseURL, entry.fingerprint, token) }
        return try APIClient(baseURL: entry.baseURL, fingerprint: entry.fingerprint, token: token)
    }
    private var guestAPI: APIClient?
    private var generation = UUID()
    private var microphone: (any GuestQuestionRecording)?
    private var microphoneStart: UUID?
    private var player: (any GuestAudioPlaying)?
    private var audioGeneration = UUID()
    private var contentGeneration = UUID()
    private var authorityGeneration = UUID()
    private var expiryTask: Task<Void, Never>?
    var subjectLabel: String { session?.subject_label ?? entry?.spaceName ?? "本人空间" }
    var hasEntry: Bool { entry != nil }
    var entrustedRecipient: String? {
        guard !isLocking, let session, !entrustmentExpired(session) else { return nil }
        return session.entrustment?.recipient_label
    }
    private static func date(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: value)
    }
    private func entrustmentExpired(_ session: GuestSession) -> Bool {
        guard let access = session.entrustment else { return false }
        guard let expires = Self.date(access.expires_at) else { return true }
        return expires <= Date()
    }
    private func watchExpiry() {
        expiryTask?.cancel(); expiryTask = nil
        guard let session, let access = session.entrustment, let expires = Self.date(access.expires_at) else { return }
        let request = generation, version = session.scope_version
        let remaining = max(0, expires.timeIntervalSinceNow)
        guard remaining > 0 else { return }
        expiryTask = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(remaining)) } catch { return }
            guard let self, self.generation == request, self.session?.scope_version == version else { return }
            self.clearContent()
            self.notice = "专属记忆已到期并锁上，内容和临时对话已清除。"
            await self.validate()
        }
    }

    #if DEBUG
    func showIsolatedUITestPreview() {
        guard ProcessInfo.processInfo.arguments.contains("--uitest-guest") else { return }
        session = try! JSONDecoder().decode(GuestSession.self, from: Data(#"{"session_id":"ui-only","subject_id":"ui-subject","subject_label":"爷爷","expires_at":"2099-01-01T00:00:00Z","revision":1,"personal_voice_available":false,"cloud_asr_policy":null,"speech_notice":"隔离界面样例","default_voice_available":false,"spoken_question_available":false}"#.utf8))
        sources = [try! JSONDecoder().decode(GuestSource.self, from: Data(#"{"episode_id":"ui-episode","recorded_at":"2026-10-16T08:00:00Z","duration_ms":12000,"transcript":"小时候，每到周末，我们一家人都会一起去河边散步。父亲总会提前带好水和吃的，牵着我的手慢慢往前走。","supplement":null,"memories":["周末和家人在河边散步"]}"#.utf8))]
        let answer = try! JSONDecoder().decode(TwinAnswerRecord.self, from: Data(#"{"answer_id":"ui-guest-answer","question":"以前周末会做什么？","answer":"小时候，每到周末，我们一家人都会一起去河边散步。父亲总会提前带好水和吃的。","response_type":"ORIGINAL","evidence":[],"model_version":"ui-fixture","person_model_version":0,"stale":false}"#.utf8))
        chat.receive(answer)
    }
    #endif

    func configure(entry: Pairing?) {
        clearSession(); self.entry = entry
    }
    func createDevice(owner: Pairing, client: APIClient) async throws -> Pairing {
        let data = try await client.request("/api/v1/subjects/\(owner.subjectID)/guest-access/device", method: "POST",
                                            body: Data("{}".utf8), contentType: "application/json")
        let reply = try JSONDecoder().decode(GuestDevice.self, from: data)
        guard reply.subject_id == owner.subjectID else { throw APIError.invalidResponse }
        return Pairing(baseURL: owner.baseURL, fingerprint: owner.fingerprint, token: reply.entry_token,
                       actorID: "guest-entry", subjectID: reply.subject_id, consentID: "",
                       connectionKind: "guest", spaceName: reply.subject_label)
    }
    func begin() async {
        guard !isBusy, session == nil, let entry else { return }
        clearSession(); isBusy = true; let request = generation
        defer { if generation == request { isBusy = false } }
        do {
            let unauthenticated = try makeAPI(entry)
            let body = try JSONSerialization.data(withJSONObject: ["entry_token": entry.token])
            let reply = try JSONDecoder().decode(GuestSession.self, from: await unauthenticated.request(
                "/api/v1/guest/sessions", method: "POST", body: body, contentType: "application/json"))
            guard generation == request, reply.subject_id == entry.subjectID, let token = reply.session_token else { return }
            guestAPI = try makeAPI(entry, token: token)
            session = reply; notice = nil; watchExpiry()
            await loadGarden()
        } catch { if generation == request { notice = "访问未开始：\(error.localizedDescription)" } }
    }
    /// A network failure hides cached answers and stops playback until authority is checked again.
    func validate() async {
        guard !isLocking, let api = guestAPI, let previous = session else { return }
        // Local expiry hides content even while a network request is delayed or offline.
        if entrustmentExpired(previous) { clearContent(); notice = "专属记忆已到期并锁上。" }
        let request = generation
        let authority = UUID(); authorityGeneration = authority
        do {
            let current = try JSONDecoder().decode(GuestSession.self, from: await api.request("/api/v1/guest/session", timeout: 10))
            guard generation == request, authorityGeneration == authority else { return }
            guard current.session_id == previous.session_id, current.subject_id == previous.subject_id else { throw APIError.invalidResponse }
            let changed = current.revision != previous.revision || current.scope_version != previous.scope_version
            if changed { clearContent(); notice = current.entrustment.map { "给\($0.recipient_label)的专属记忆已打开。" } ?? "开放范围已更新，旧对话已清除。" }
            if !current.personal_voice_available && previous.personal_voice_available { stopPlayback() }
            session = current
            watchExpiry()
            guard !entrustmentExpired(current) else { clearContent(); notice = "专属记忆已到期并锁上。"; return }
            if changed || sources.isEmpty { await loadGarden() }
        } catch {
            guard generation == request, authorityGeneration == authority else { return }
            clearContent()
            if case APIError.server(let code, _) = error, [401, 403, 404, 410].contains(code) {
                clearSession(); notice = "本次访问已失效，请重新开始访问或请主用户检查开放范围。"
            } else { notice = "暂时无法核验开放范围，内容已隐藏。连接恢复后可重试。" }
        }
    }
    func loadGarden() async {
        guard !isLocking, let api = guestAPI, let session else { return }
        let request = generation, content = contentGeneration
        do {
            let reply = try JSONDecoder().decode(GuestGardenReply.self, from: await api.request("/api/v1/guest/memories"))
            guard generation == request, contentGeneration == content else { return }
            if reply.revision != session.revision || reply.scope_version != session.scope_version { clearContent(); await validate(); return }
            guard !entrustmentExpired(session) else { clearContent(); return }
            sources = reply.items
        } catch { if generation == request, contentGeneration == content { clearContent(); notice = error.localizedDescription } }
    }
    func ask() async {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isLocking, !isBusy, !isRecording, !isStartingRecording, let api = guestAPI else { return }
        isBusy = true; let request = generation, scopeVersion = session?.scope_version
        defer { if request == generation { isBusy = false } }
        await validate()
        guard request == generation, session != nil, session?.scope_version == scopeVersion else { return }
        let content = contentGeneration
        let secretAttempt = entrustmentAttempt
        var body: [String: Any] = ["question": text, "request_id": UUID().uuidString]
        if secretAttempt { body["entrustment_attempt"] = true }
        if let parent = chat.turns.last?.answer?.id { body["previous_answer_id"] = parent }
        // A natural message may be an entrustment secret. Never show it before server redaction.
        question = ""
        do {
            let answer = try JSONDecoder().decode(TwinAnswerRecord.self, from: await api.request("/api/v1/guest/questions",
                method: "POST", body: JSONSerialization.data(withJSONObject: body), contentType: "application/json",
                headers: scopeVersion.map { ["X-Guest-Scope-Version": $0] } ?? [:]))
            guard generation == request else { return }
            guard contentGeneration == content else { return }
            guard !secretAttempt || answer.model_version == "guest-entrustment-control" else {
                notice = "当前服务未能安全核验暗号，内容未加入聊天。请稍后重试。"; return
            }
            await receive(answer)
        } catch { if generation == request { notice = secretAttempt ? "暗号未核验，请私下核对后重试。" : "本次提问未完成，请重试。" } }
    }
    func playSource(_ id: String) async {
        guard canPlayAudio else { return }
        await validate()
        guard canPlayAudio, sources.contains(where: { $0.id == id }), let api = guestAPI else { return }
        await play { try await api.request("/api/v1/guest/episodes/\(id)/audio") }
    }
    func playAnswer(_ id: String, personal: Bool) async {
        guard canPlayAudio else { return }
        await validate()
        guard canPlayAudio, let api = guestAPI, chat.turns.contains(where: { $0.answer?.id == id }),
              personal ? session?.personal_voice_available == true : session?.default_voice_available == true else { return }
        await play { try await api.request("/api/v1/guest/speech/\(id)?voice_mode=\(personal ? "personal" : "default")") }
    }
    private func play(_ download: () async throws -> Data) async {
        guard canPlayAudio else { return }
        stopPlayback(); let request = generation, audio = audioGeneration
        do {
            let bytes = try await download()
            guard generation == request, audioGeneration == audio, session != nil, canPlayAudio else { return }
            await validate()
            guard generation == request, audioGeneration == audio, session != nil, canPlayAudio else { return }
            let next = try playAudio(bytes)
            player = next; isPlaying = true
        } catch { if generation == request { notice = "暂时无法播放：\(error.localizedDescription)" } }
    }
    private var canPlayAudio: Bool { !isLocking && !isRecording && !isStartingRecording }
    func stopPlayback() { audioGeneration = UUID(); player?.stop(); player = nil; isPlaying = false }
    func startQuestionRecording() async {
        guard !isLocking, !isBusy, !isRecording, !isStartingRecording, session?.spoken_question_available == true else { return }
        stopPlayback()
        let request = generation, start = UUID()
        microphoneStart = start; isStartingRecording = true
        defer { if microphoneStart == start { microphoneStart = nil; isStartingRecording = false } }
        let allowed = await recordPermission()
        guard request == generation, microphoneStart == start, !isLocking, !isBusy,
              !isRecording, session?.spoken_question_available == true else { return }
        guard allowed else { notice = "请在系统设置中允许麦克风访问。"; return }
        do {
            let next = microphoneFactory()
            try next.start()
            microphone = next; isRecording = true
        } catch { notice = error.localizedDescription; stopTransientAudio() }
    }
    func finishQuestionRecording() async {
        guard !isLocking, isRecording, let microphone, let api = guestAPI, let session else { return }
        let pcm = microphone.finish(); self.microphone = nil; isRecording = false
        isBusy = true; let request = generation, content = contentGeneration
        let secretAttempt = entrustmentAttempt
        defer { if generation == request { isBusy = false } }
        do {
            guard !pcm.isEmpty else { throw APIError.invalidResponse }
            let boundary = "Guest-\(UUID().uuidString)"
            var data = Data()
            func field(_ name: String, _ value: String) {
                data.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
            }
            field("request_id", UUID().uuidString)
            if secretAttempt { field("entrustment_attempt", "true") }
            if let previous = chat.turns.last?.answer?.id { field("previous_answer_id", previous) }
            data.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"question.wav\"\r\nContent-Type: audio/wav\r\n\r\n".utf8))
            data.append(DomesticMicrophoneBuffer.wave(pcm)); data.append(Data("\r\n--\(boundary)--\r\n".utf8))
            var headers = session.cloud_asr_policy.map { ["X-Cloud-ASR-Policy": $0] } ?? [:]
            if let version = session.scope_version { headers["X-Guest-Scope-Version"] = version }
            let reply = try JSONDecoder().decode(GuestSpokenReply.self, from: await api.request("/api/v1/guest/spoken-question",
                method: "POST", body: data, contentType: "multipart/form-data; boundary=\(boundary)", headers: headers))
            guard generation == request else { return }
            guard contentGeneration == content else { return }
            guard !secretAttempt || reply.answer.model_version == "guest-entrustment-control" else {
                notice = "当前服务未能安全核验暗号，内容未加入聊天。请稍后重试。"; return
            }
            // Use only the server's sanitized question, never raw ASR text.
            await receive(reply.answer)
        } catch { if generation == request { notice = secretAttempt ? "暗号未核验，请私下核对后重试。临时声音已清除。" : "语音提问未完成，请重试。临时声音已清除。" } }
    }
    private func receive(_ answer: TwinAnswerRecord) async {
        guard !isLocking else { return }
        if answer.model_version == "guest-entrustment-control" {
            guard ["[暗号已核验]", "[暗号未核验]"].contains(answer.question) else {
                notice = "暗号核验结果不可用，内容未加入聊天。"; return
            }
            let request = generation
            clearContent(); entrustmentAttempt = false
            await validate()
            guard generation == request, let current = session, !entrustmentExpired(current) else { return }
            notice = session?.entrustment.map { "给\($0.recipient_label)的专属记忆已打开。" } ?? "暗号未核验，仍在当前开放范围。"
        } else {
            guard let session, !entrustmentExpired(session) else { clearContent(); return }
            let turn = chat.begin(answer.question, conversationMode: true)
            chat.receive(answer, for: turn)
        }
    }
    func lockEntrustment() async {
        guard !isLocking, let api = guestAPI, let previous = session else { return }
        // Invalidate every operation started before the local lock, including authority checks.
        generation = UUID(); authorityGeneration = UUID()
        expiryTask?.cancel(); expiryTask = nil
        let request = generation
        isLocking = true; isBusy = true
        clearContent(); notice = "专属记忆已在本机锁上。"
        do {
            _ = try await api.request("/api/v1/guest/entrustment", method: "DELETE", timeout: 15,
                headers: previous.scope_version.map { ["X-Guest-Scope-Version": $0] } ?? [:])
            guard generation == request else { return }
            let current = try JSONDecoder().decode(GuestSession.self, from: await api.request("/api/v1/guest/session", timeout: 10))
            guard generation == request else { return }
            guard current.session_id == previous.session_id, current.subject_id == previous.subject_id,
                  current.entrustment == nil else { throw APIError.invalidResponse }
            session = current; isLocking = false; isBusy = false
            notice = "专属记忆已锁上，旧对话已清除。"
            await loadGarden()
        } catch {
            guard generation == request else { return }
            // Do not restore a possibly still-open server scope after an unconfirmed lock.
            clearSession(); notice = "本机已锁上；暂未确认服务端锁定，请重新开始访问。"
        }
    }
    func stopTransientAudio() {
        microphoneStart = nil; isStartingRecording = false
        microphone?.discard(); microphone = nil; isRecording = false; stopPlayback()
    }
    private func clearContent() { contentGeneration = UUID(); stopTransientAudio(); chat = TwinChatHistory(); sources = []; question = "" }
    private func clearSession() { expiryTask?.cancel(); expiryTask = nil; authorityGeneration = UUID(); generation = UUID(); clearContent(); session = nil; guestAPI = nil; isBusy = false; isLocking = false; entrustmentAttempt = false }
    func end() async {
        let api = guestAPI
        clearSession(); notice = "本次访问已结束。聊天和临时语音已清除。"
        do { _ = try await api?.request("/api/v1/guest/session", method: "DELETE", timeout: 15) }
        catch {
            if case APIError.server(401, _) = error { return }
            notice = "本机访问已结束。服务端暂未确认结束，会话将在到期后失效。"
        }
    }
}

struct GuestAccessTabs: View {
    @EnvironmentObject private var model: AppModel
    @ObservedObject var guest: GuestAccessModel
    @State private var selection = 0
    @State private var showOwner = false
    @State private var password = ""
    @State private var username = ""
    @State private var expiredLogin = false
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading) {
                    Text("亲友／游客模式").font(.caption).foregroundStyle(Ink.muted)
                    Text("正在访问 · \(guest.subjectLabel)").font(.headline)
                }
                Spacer()
                Menu {
                    Button("返回主用户") { password = ""; model.errorMessage = nil; showOwner = true }
                    Button("结束本次访问", role: .destructive) { Task { await guest.end() } }
                        .disabled(guest.isBusy || guest.isRecording)
                } label: { Label("访问", systemImage: "person.crop.circle") }
            }.padding().background(RMColors.surface)
            if let notice = guest.notice { Text(notice).font(.footnote).padding(.horizontal).accessibilityIdentifier("guest.notice") }
            if guest.session == nil {
                Spacer()
                ForgetMeNotSprig().frame(width: 120, height: 120)
                Text("亲友免密码浏览与交流").font(.title3)
                Text("仅能访问主用户已确认开放的资料。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
                Button("开始本次访问") { Task { await guest.begin() } }
                    .buttonStyle(.borderedProminent).disabled(guest.isBusy || !guest.hasEntry)
                    .accessibilityIdentifier("guest.begin")
                Button("返回主用户") { password = ""; model.errorMessage = nil; showOwner = true }
                Spacer()
            } else {
                TabView(selection: $selection) {
                    NavigationStack { GuestGardenView(guest: guest) }
                        .tabItem { Label("记忆花园", systemImage: "leaf") }.tag(0)
                    NavigationStack { GuestTwinView(guest: guest) }
                        .tabItem { Label("TwinAgent", systemImage: "bubble.left.and.bubble.right") }.tag(1)
                }.disabled(guest.isLocking).accessibilityIdentifier("guest.tabs")
            }
        }
        .background(RMColors.background)
        .sheet(isPresented: $showOwner) {
            NavigationStack {
                Form {
                    Text("验证当前空间主用户的账号密码后，恢复管理权限。")
                    DisclosureGroup("登录已失效？重新登录原账号", isExpanded: $expiredLogin) {
                        TextField("原主用户账号", text: $username).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Text("只能恢复原账号的同一个本人空间。")
                            .font(.footnote).foregroundStyle(Ink.muted)
                    }
                    SecureField("主用户账号密码", text: $password).textContentType(.password)
                        .accessibilityIdentifier("guest.ownerPassword")
                    if let error = model.errorMessage { Text(error).font(.footnote).foregroundStyle(.red).accessibilityIdentifier("guest.ownerError") }
                    Button("验证并返回主用户") {
                        let entered = password; password = ""
                        Task { await model.returnToOwner(password: entered, username: expiredLogin ? username : nil); if !model.isGuestMode { showOwner = false } }
                    }.disabled(password.isEmpty || expiredLogin && username.isEmpty || model.isBusy || guest.isBusy || guest.isRecording)
                        .accessibilityIdentifier("guest.returnOwner")
                }.navigationTitle("返回主用户")
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { password = ""; showOwner = false } } }
            }
        }
        .task {
            while !Task.isCancelled {
                await guest.validate()
                do { try await Task.sleep(for: .seconds(2)) } catch { return }
            }
        }
    }
}

private struct GuestGardenView: View {
    @ObservedObject var guest: GuestAccessModel
    var body: some View {
        List {
            Section {
                Text("已由主用户确认开放，包含对应的整段原音与核对文字。")
                    .font(.footnote).foregroundStyle(Ink.muted)
            }
            if guest.sources.isEmpty { ContentUnavailableView("花园暂未开放内容", systemImage: "leaf", description: Text("请主用户选择并确认开放的录音来源。")) }
            ForEach(guest.sources) { source in
                NavigationLink {
                    GuestSourceDetail(guest: guest, sourceID: source.id)
                } label: {
                    HStack {
                        GardenArtworkImage(artwork: .sprig).frame(width: 56, height: 64)
                        VStack(alignment: .leading) {
                            Text(source.memories.first ?? String(source.transcript.prefix(60))).lineLimit(3)
                            Text(MemoryGardenProjection.recordingDate(source.recorded_at)).font(.caption).foregroundStyle(Ink.muted)
                        }
                    }
                }
            }
        }.navigationTitle("记忆花园").refreshable { await guest.validate(); await guest.loadGarden() }
    }
}

private struct GuestSourceDetail: View {
    @ObservedObject var guest: GuestAccessModel
    let sourceID: String
    var body: some View {
        ScrollView {
            if let source = guest.sources.first(where: { $0.id == sourceID }) {
                VStack(alignment: .leading, spacing: 20) {
                    GardenArtworkImage(artwork: .sprig).frame(height: 140).frame(maxWidth: .infinity)
                    Text(MemoryGardenProjection.recordingDate(source.recorded_at)).font(.caption).foregroundStyle(Ink.muted)
                    ForEach(Array(source.memories.enumerated()), id: \.offset) { _, memory in Text(memory).font(.headline) }
                    Text("完整核对文字").font(.headline)
                    Text(source.transcript)
                    if let supplement = source.supplement, !supplement.isEmpty { Text(supplement) }
                    if source.hasAudio {
                        Button("播放整段原音") { Task { await guest.playSource(source.id) } }.buttonStyle(.borderedProminent)
                            .disabled(guest.isRecording || guest.isStartingRecording)
                    } else { Text("文字来源，无原音").font(.footnote).foregroundStyle(Ink.muted) }
                    if guest.isPlaying { Button("停止播放") { guest.stopPlayback() } }
                }.padding()
            } else { ContentUnavailableView("此内容已不可访问", systemImage: "lock", description: Text("开放范围已变化或暂时无法核验。")) }
        }.navigationTitle("开放的记忆")
            .onDisappear { guest.stopPlayback() }
    }
}

private struct GuestTwinView: View {
    @ObservedObject var guest: GuestAccessModel
    @State private var showSpeechConsent = false
    @State private var personalVoice = false
    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 20) {
                    Text("本次对话不保存。Twin 只参考已开放资料，资料不足时会说明无法确定；退出后清除文字和临时语音，也不会写入主用户记忆或训练。")
                        .font(.footnote).foregroundStyle(Ink.muted)
                    if let recipient = guest.entrustedRecipient {
                        Label("给\(recipient)的专属记忆已打开", systemImage: "lock.open").font(.headline)
                        Button("锁上专属记忆", role: .destructive) { Task { await guest.lockEntrustment() } }
                            .disabled(guest.isBusy || guest.isRecording).accessibilityIdentifier("guest.lockEntrustment")
                    } else {
                        Text("如果有人为你留下专属记忆，可以私下说出彼此的暗号。") .font(.footnote).foregroundStyle(Ink.muted)
                    }
                    ForEach(guest.chat.turns) { turn in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(turn.question).font(.headline).frame(maxWidth: .infinity, alignment: .trailing)
                            if let answer = turn.answer {
                                Text(answer.response_type == "ORIGINAL" ? "本人原话" : answer.response_type == "SIMULATION" ? "根据开放资料推测" : answer.response_type == "CONVERSATION" ? "对话回应" : "资料不足")
                                    .font(.caption).foregroundStyle(Ink.muted)
                                Text(answer.displayText).textSelection(.enabled)
                                ForEach(answer.evidence.filter { evidence in guest.sources.contains(where: { $0.id == evidence.episode_id }) }) { evidence in
                                    NavigationLink {
                                        GuestSourceDetail(guest: guest, sourceID: evidence.episode_id)
                                    } label: {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text("查看开放来源").font(.caption)
                                            if let excerpt = evidence.excerpt { Text(excerpt).font(.footnote).lineLimit(4) }
                                        }
                                    }
                                }
                                if guest.session?.default_voice_available == true || personalVoice {
                                    Button("播放回答") { Task { await guest.playAnswer(answer.id, personal: personalVoice) } }
                                        .disabled(guest.isRecording || guest.isStartingRecording)
                                }
                            } else if let failure = turn.failure { Text(failure).foregroundStyle(.red) }
                            else { ProgressView("正在回答…") }
                        }.padding().rmCardSurface()
                    }
                }.padding()
            }
            if guest.isPlaying { Button("停止播放") { guest.stopPlayback() } }
            if guest.session?.personal_voice_available == true {
                Toggle("使用已开放的本人音色", isOn: $personalVoice).padding(.horizontal).font(.footnote)
            }
            Toggle("本次是在说暗号", isOn: $guest.entrustmentAttempt).padding(.horizontal).font(.footnote)
                .disabled(guest.isBusy || guest.isRecording || guest.isStartingRecording).accessibilityIdentifier("guest.secretAttempt")
            HStack(alignment: .bottom) {
                TextField(guest.entrustmentAttempt ? "私下输入暗号" : "问问 TwinAgent", text: $guest.question,
                          prompt: Text(guest.entrustmentAttempt ? "私下输入暗号" : "问问 TwinAgent").foregroundStyle(Ink.muted), axis: .vertical)
                    .lineLimit(1...4).foregroundStyle(Ink.text)
                    .padding(.horizontal, 12).padding(.vertical, 10)
                    .background(RMColors.surface, in: RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Ink.muted.opacity(0.3), lineWidth: 1))
                    .disabled(guest.isRecording)
                    .privacySensitive(guest.entrustmentAttempt)
                    .accessibilityIdentifier("guest.question")
                Button { Task { await guest.ask() } } label: { Image(systemName: "arrow.up.circle.fill").font(.title) }
                    .accessibilityLabel("发送").disabled(guest.isBusy || guest.isRecording || guest.isStartingRecording || guest.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if guest.session?.spoken_question_available == true {
                    Button {
                        if guest.isRecording { Task { await guest.finishQuestionRecording() } }
                        else { showSpeechConsent = true }
                    } label: { Image(systemName: guest.isRecording ? "stop.circle.fill" : "mic.circle").font(.title) }
                        .accessibilityLabel(guest.isRecording ? "结束录音并提问" : "语音提问").disabled(guest.isBusy || guest.isStartingRecording)
                }
            }.padding()
            if guest.isBusy { ProgressView("正在核对和回应…").font(.footnote).padding(.bottom, 8) }
        }.background(RMColors.background).navigationTitle("TwinAgent")
            .alert("本次语音提问", isPresented: $showSpeechConsent) {
                Button("取消", role: .cancel) { }
                Button("同意并录制") { Task { await guest.startQuestionRecording() } }
            } message: { Text((guest.session?.speech_notice ?? "录音仅用于本次提问转写。") + " 临时声音在提问完成或退出时清除，不用于记忆、训练或声音复刻。最长录制 60 秒。") }
            .onChange(of: guest.session?.personal_voice_available) { _, value in if value != true { personalVoice = false } }
    }
}

struct GuestSharingView: View {
    @EnvironmentObject private var model: AppModel
    @State private var selected = Set<String>()
    @State private var enabled = false
    @State private var personalVoice = false
    @State private var preview: GuestPreview?
    @State private var showPreview = false
    @State private var busy = false
    @State private var notice: String?
    @State private var scope: ReviewScope?
    private var candidates: [EpisodeRecord] { model.episodes.filter { $0.status == "ready" && !($0.transcript ?? "").isEmpty } }
    var body: some View {
        List {
            Section {
                Toggle("允许本机亲友访问", isOn: $enabled)
                Toggle("开放本人音色（需有效声音许可）", isOn: $personalVoice)
                Text("新来源默认不开放。每次保存都需核对整段原音、全文及连带开放的故事；修改来源后需要重新确认。")
                    .font(.footnote).foregroundStyle(Ink.muted)
            }
            Section("选择已核对录音") {
                if candidates.isEmpty { Text("暂无可选择的已核对录音。") }
                ForEach(candidates) { episode in
                    Button {
                        if selected.contains(episode.id) { selected.remove(episode.id) } else { selected.insert(episode.id) }
                        preview = nil
                    } label: {
                        HStack {
                            Text(String((episode.transcript ?? "").prefix(80))).foregroundStyle(Ink.text)
                            Spacer()
                            Image(systemName: selected.contains(episode.id) ? "checkmark.circle.fill" : "circle")
                        }
                    }
                }
            }
            if let notice { Section { Text(notice).font(.footnote) } }
            Section {
                Button("预览完整开放范围") { Task { await loadPreview() } }.disabled(busy)
                    .accessibilityIdentifier("guest.sharing.preview")
            }
        }.disabled(busy || model.isGuestMode).navigationTitle("亲友开放范围")
            .task { await load() }
            .sheet(isPresented: $showPreview) {
                NavigationStack {
                    List {
                        if let preview {
                            Section { Text(preview.notice); Text("开放包括以下每段完整原音和全文，不能只开放某张记忆卡片。") }
                            ForEach(preview.items) { source in
                                Section("整段来源 · \(source.recorded_at)") {
                                    Text(source.transcript)
                                    if let supplement = source.supplement { Text(supplement) }
                                    if source.hasAudio { Button("回听完整原音") { Task { await model.playOriginal(episodeID: source.id) } } }
                                    else { Text("文字来源，无原音").font(.footnote).foregroundStyle(Ink.muted) }
                                    Text("连带开放的记忆").font(.headline)
                                    ForEach(Array(source.memories.enumerated()), id: \.offset) { _, memory in Text(memory) }
                                }
                            }
                            Section { Button(enabled ? "确认以上全部内容并开放" : "确认关闭亲友访问") { Task { await save(preview) } }.disabled(busy) }
                        }
                    }.navigationTitle("游客可见范围预览")
                        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { showPreview = false; model.stopPlayback() } } }
                }.interactiveDismissDisabled(busy)
            }
            .onDisappear { model.stopPlayback() }
    }
    private func load() async {
        guard let owner = model.pairing, let api = model.dialogueClient(), !model.isGuestMode else { return }
        let current = ReviewScope(owner); scope = current; busy = true; model.isBusy = true; defer { busy = false; model.isBusy = false }
        do {
            let reply = try JSONDecoder().decode(GuestScope.self, from: await api.request("/api/v1/subjects/\(owner.subjectID)/guest-access"))
            guard model.pairing.map(ReviewScope.init) == current else { return }
            selected = Set(reply.episode_ids); enabled = reply.enabled; personalVoice = reply.personal_voice_enabled
        } catch { notice = error.localizedDescription }
    }
    private func loadPreview() async {
        guard let owner = model.pairing, model.pairing.map(ReviewScope.init) == scope,
              let api = model.dialogueClient(), !model.connectionChangeBlocked else { return }
        busy = true; model.isBusy = true; defer { busy = false; model.isBusy = false }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["episode_ids": selected.sorted()])
            let reply = try JSONDecoder().decode(GuestPreview.self, from: await api.request(
                "/api/v1/subjects/\(owner.subjectID)/guest-access/preview", method: "POST", body: body, contentType: "application/json"))
            guard model.pairing.map(ReviewScope.init) == scope else { return }
            preview = reply; showPreview = true; notice = nil
        } catch { notice = error.localizedDescription }
    }
    private func save(_ preview: GuestPreview) async {
        guard let owner = model.pairing, model.pairing.map(ReviewScope.init) == scope,
              let api = model.dialogueClient(), !model.connectionChangeBlocked else { return }
        busy = true; model.isBusy = true; defer { busy = false; model.isBusy = false }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["episode_ids": preview.episode_ids,
                "source_version": preview.source_version, "enabled": enabled, "personal_voice_enabled": personalVoice])
            _ = try await api.request("/api/v1/subjects/\(owner.subjectID)/guest-access", method: "PUT", body: body, contentType: "application/json")
            guard model.pairing.map(ReviewScope.init) == scope else { return }
            showPreview = false; model.stopPlayback(); notice = "开放范围已保存。撤销或删除的来源不再供游客访问。"
        } catch { showPreview = false; notice = "未保存，请重新预览：\(error.localizedDescription)" }
    }
}

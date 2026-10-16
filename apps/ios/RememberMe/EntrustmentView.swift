import SwiftUI
import AVFoundation

// Existing account-bound grants stay separate. They are never converted into guest secrets.
struct EntrustmentPlan: Decodable, Identifiable {
    let plan_id: String
    let subject_id: String
    let recipient_actor_id: String
    let recipient_label: String
    let condition: String
    let status: String
    let episode_count: Int
    let voice_allowed: Bool
    var id: String { plan_id }
}
private struct EntrustmentPlans: Decodable { let items: [EntrustmentPlan] }
private struct LegacyReview: Decodable, Identifiable {
    let subject_id: String
    let subject_label: String
    let status: String
    var id: String { subject_id }
}
private struct LegacyReviews: Decodable { let items: [LegacyReview] }
struct GuestEntrustmentPlan: Decodable, Identifiable {
    let plan_id: String
    let subject_id: String
    let recipient_label: String
    let condition: String
    let status: String
    let episode_count: Int
    let voice_allowed: Bool
    let revision: Int
    let secret_confirmation_required: Bool
    var id: String { plan_id }
    private enum CodingKeys: String, CodingKey {
        case plan_id, subject_id, recipient_label, condition, status, episode_count, voice_allowed, revision, secret_confirmation_required
    }
    init(from decoder: Decoder) throws {
        let fields = try decoder.container(keyedBy: CodingKeys.self)
        plan_id = try fields.decode(String.self, forKey: .plan_id)
        subject_id = try fields.decode(String.self, forKey: .subject_id)
        recipient_label = try fields.decode(String.self, forKey: .recipient_label)
        condition = try fields.decode(String.self, forKey: .condition)
        status = try fields.decode(String.self, forKey: .status)
        episode_count = try fields.decode(Int.self, forKey: .episode_count)
        voice_allowed = try fields.decode(Bool.self, forKey: .voice_allowed)
        revision = try fields.decode(Int.self, forKey: .revision)
        secret_confirmation_required = try fields.decodeIfPresent(Bool.self, forKey: .secret_confirmation_required) ?? false
    }
}
private struct GuestEntrustmentPlans: Decodable { let items: [GuestEntrustmentPlan] }
struct GuestEntrustmentDraft: Encodable {
    let recipient_label: String
    let secret: String
    let private_detail_confirmed: Bool
    let episode_ids: [String]
    let source_version: String
    let handover_consent_id: String
    let voice_consent_id: String?
    let condition: String
}
extension APIClient {
    func ownEntrustments(subject: String) async throws -> [EntrustmentPlan] {
        try JSONDecoder().decode(EntrustmentPlans.self, from: await request("/api/v1/subjects/\(subject)/entrustments")).items
    }
    func receivedEntrustments() async throws -> [EntrustmentPlan] {
        try JSONDecoder().decode(EntrustmentPlans.self, from: await request("/api/v1/entrustments")).items
    }
    func revokeEntrustment(_ id: String) async throws { _ = try await request("/api/v1/entrustments/\(id)/revoke", method: "POST") }
    func guestEntrustments(subject: String) async throws -> [GuestEntrustmentPlan] {
        try JSONDecoder().decode(GuestEntrustmentPlans.self, from: await request("/api/v1/subjects/\(subject)/guest-entrustments")).items
    }
    func previewGuestEntrustment(subject: String, episodes: [String]) async throws -> GuestPreview {
        try JSONDecoder().decode(GuestPreview.self, from: await request("/api/v1/subjects/\(subject)/guest-entrustments/preview", method: "POST",
            body: JSONSerialization.data(withJSONObject: ["episode_ids": episodes]), contentType: "application/json"))
    }
    func createGuestEntrustment(subject: String, draft: GuestEntrustmentDraft) async throws {
        _ = try await request("/api/v1/subjects/\(subject)/guest-entrustments", method: "POST", body: JSONEncoder().encode(draft), contentType: "application/json")
    }
    func revokeGuestEntrustment(_ id: String) async throws { _ = try await request("/api/v1/guest-entrustments/\(id)/revoke", method: "POST") }
    func confirmGuestEntrustmentSecret(_ id: String, secret: String) async throws -> GuestEntrustmentPlan {
        try JSONDecoder().decode(GuestEntrustmentPlan.self, from: await request("/api/v1/guest-entrustments/\(id)/secret-index",
            method: "POST", body: JSONSerialization.data(withJSONObject: ["secret": secret]), contentType: "application/json"))
    }
}

@MainActor
protocol EntrustmentSecretRecording {
    func start(isAllowed: @escaping @MainActor () -> Bool) async throws
    func finish() throws -> URL
    func cancel()
}

/// This recorder is not connected to the normal recording store, Episodes or chat.
@MainActor
final class PrivateEntrustmentRecorder: EntrustmentSecretRecording {
    private var recorder: AVAudioRecorder?
    private var file: URL?
    private var generation = UUID()
    private var ownsAudioSession = false
    func start(isAllowed: @escaping @MainActor () -> Bool) async throws {
        let epoch = generation
        guard await AVAudioApplication.requestRecordPermission() else { throw APIError.server(403, "请允许麦克风权限，或直接输入暗号。") }
        guard generation == epoch, isAllowed() else { throw CancellationError() }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker])
        try session.setActive(true)
        ownsAudioSession = true
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("entrust-secret-\(UUID().uuidString).m4a")
        file = url
        do {
            let next = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: kAudioFormatMPEG4AAC,
                AVSampleRateKey: 24000, AVNumberOfChannelsKey: 1, AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue])
            guard next.record(forDuration: 45) else { throw APIError.invalidResponse }
            recorder = next
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: url.path)
        } catch { cancel(); throw error }
    }
    func finish() throws -> URL {
        recorder?.stop(); recorder = nil
        guard let url = file else { throw APIError.invalidResponse }
        file = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        ownsAudioSession = false
        return url
    }
    func cancel() {
        generation = UUID(); recorder?.stop(); recorder = nil
        if let file { try? FileManager.default.removeItem(at: file) }; file = nil
        if ownsAudioSession { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
        ownsAudioSession = false
    }
}

struct EntrustmentCaptureState {
    var recording = false
    var startingRecording = false
    var queryRecording = false
    var voiceRecording = false
    var speakerRecording = false
    var realtimeCall = false
    var deviceRecording = false
    var blocked: Bool { recording || startingRecording || queryRecording || voiceRecording || speakerRecording || realtimeCall || deviceRecording }
}
extension AppModel {
    var entrustmentCaptureState: EntrustmentCaptureState {
        EntrustmentCaptureState(recording: isRecording, startingRecording: isStartingRecording,
            queryRecording: isQueryRecording, voiceRecording: isVoiceRecording, speakerRecording: isSpeakerRecording,
            realtimeCall: realtimeVoice.isActive, deviceRecording: devices.recording)
    }
}

/// A local guided draft. The secret goes only to the dedicated save endpoint after confirmation.
@MainActor
final class EntrustmentSetupModel: ObservableObject {
    enum Stage: Int, CaseIterable { case recipient, secret, sources, conditions, confirmation }
    @Published var stage: Stage = .recipient
    @Published var recipientLabel = "" { didSet { privateDetailConfirmed = false; scopeConfirmed = false } }
    @Published var secret = "" { didSet { secretReviewed = false; privateDetailConfirmed = false } }
    @Published var secretReviewed = false
    @Published var privateDetailConfirmed = false
    @Published var scopeConfirmed = false
    @Published var selectedEpisodeIDs = Set<String>() { didSet { preview = nil; sourceReviewed = false; scopeConfirmed = false } }
    @Published private(set) var preview: GuestPreview?
    @Published var sourceReviewed = false
    @Published var future = false { didSet { scopeConfirmed = false } }
    @Published var steward = ""
    @Published var allowVoice = false { didSet { scopeConfirmed = false } }
    @Published private(set) var isRecording = false
    @Published private(set) var isTranscribing = false
    @Published var notice: String?
    private let recorder: any EntrustmentSecretRecording
    private let speech: any LocalSpeechTranscriber
    private var recognitionTask: Task<String, Error>?
    private var pendingFile: URL?
    private var generation = UUID()
    init(recorder: any EntrustmentSecretRecording = PrivateEntrustmentRecorder(),
         speech: any LocalSpeechTranscriber = OnDeviceSpeechTranscriber()) {
        self.recorder = recorder; self.speech = speech
        // Recover only abandoned files from this private workflow.
        for url in (try? FileManager.default.contentsOfDirectory(at: FileManager.default.temporaryDirectory, includingPropertiesForKeys: nil)) ?? []
            where url.lastPathComponent.hasPrefix("entrust-secret-") { try? FileManager.default.removeItem(at: url) }
    }
    static func effectiveCharacters(_ secret: String) -> String {
        String(secret.precomposedStringWithCompatibilityMapping.lowercased().unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) })
    }
    var secretMeetsMinimum: Bool {
        let effective = Self.effectiveCharacters(secret)
        return effective.count >= 12 && Set(effective).count >= 6
    }
    var canContinue: Bool {
        switch stage {
        case .recipient: !recipientLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .secret: secretMeetsMinimum && secretReviewed && !isRecording && !isTranscribing
        case .sources: preview != nil && sourceReviewed && !selectedEpisodeIDs.isEmpty
        case .conditions: !future || !steward.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .confirmation: secretMeetsMinimum && secretReviewed && privateDetailConfirmed && scopeConfirmed && preview != nil
        }
    }
    func acceptPreview(_ value: GuestPreview) throws {
        guard Set(value.episode_ids) == selectedEpisodeIDs, !selectedEpisodeIDs.isEmpty,
              Set(value.items.map(\.id)) == selectedEpisodeIDs, !value.source_version.isEmpty else { throw APIError.invalidResponse }
        preview = value; sourceReviewed = false; scopeConfirmed = false
    }
    func advance() {
        guard canContinue, let next = Stage(rawValue: stage.rawValue + 1) else { return }
        stage = next
    }
    func makeDraft(handoverConsentID: String, voiceConsentID: String?) throws -> GuestEntrustmentDraft {
        guard stage == .confirmation, canContinue, let preview, sourceReviewed,
              Set(preview.episode_ids) == selectedEpisodeIDs,
              !recipientLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !future || !steward.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !handoverConsentID.isEmpty, !allowVoice || voiceConsentID != nil else { throw APIError.invalidResponse }
        return GuestEntrustmentDraft(recipient_label: recipientLabel.trimmingCharacters(in: .whitespacesAndNewlines),
            secret: secret, private_detail_confirmed: true, episode_ids: preview.episode_ids, source_version: preview.source_version,
            handover_consent_id: handoverConsentID, voice_consent_id: allowVoice ? voiceConsentID : nil,
            condition: future ? "after_verified_transition" : "immediate")
    }
    func startRecording(captureAllowed: @escaping @MainActor () -> Bool = { true }) async {
        guard !isRecording, !isTranscribing else { return }
        guard captureAllowed() else { clearSecret(); notice = "请先结束正在进行的录音或通话，再私下设置暗号。"; return }
        let epoch = generation; notice = nil
        do {
            try await recorder.start(isAllowed: captureAllowed)
            guard generation == epoch, captureAllowed() else { recorder.cancel(); return }
            isRecording = true
        } catch { if generation == epoch { notice = "本机录音未开始，可以直接输入暗号。" } }
    }
    func finishRecording() async {
        guard isRecording else { return }
        let epoch = generation
        do {
            let url = try recorder.finish(); pendingFile = url; isRecording = false; isTranscribing = true
            defer { try? FileManager.default.removeItem(at: url); if pendingFile == url { pendingFile = nil }; if generation == epoch { isTranscribing = false; recognitionTask = nil } }
            let task = Task { try await speech.transcribe(url) }; recognitionTask = task
            let text = try await task.value
            guard generation == epoch else { return }
            secret = text; notice = "已仅在本机转写。请展开核对每个字，再确认暗号。临时原音已清除。"
        } catch {
            if generation == epoch { isRecording = false; isTranscribing = false; notice = "本机离线识别未完成，临时原音已清除。请直接输入暗号；不会转交云端识别。" }
        }
    }
    func clearSecret() {
        generation = UUID(); recognitionTask?.cancel(); recognitionTask = nil; recorder.cancel()
        if let pendingFile { try? FileManager.default.removeItem(at: pendingFile) }; pendingFile = nil
        secret = ""; secretReviewed = false; privateDetailConfirmed = false; scopeConfirmed = false
        isRecording = false; isTranscribing = false; notice = nil
    }
}

/// Restores secret matching for one existing plan without changing its grant.
@MainActor
final class EntrustmentSecretIndexModel: ObservableObject {
    @Published private(set) var isBusy = false
    @Published private(set) var notice: String?
    private var generation = UUID()
    func clear(draft: EntrustmentSetupModel) {
        generation = UUID(); isBusy = false; notice = nil; draft.clearSecret()
    }
    func confirm(plan: GuestEntrustmentPlan, draft: EntrustmentSetupModel,
                 isCurrent: () -> Bool, submit: (String) async throws -> GuestEntrustmentPlan) async -> GuestEntrustmentPlan? {
        guard !isBusy, plan.status == "confirmed", plan.secret_confirmation_required,
              draft.secretMeetsMinimum, draft.secretReviewed, !draft.isRecording, !draft.isTranscribing, isCurrent() else { return nil }
        let request = generation, secret = draft.secret
        draft.clearSecret(); isBusy = true; notice = nil
        defer { if generation == request { isBusy = false } }
        do {
            let result = try await submit(secret)
            guard generation == request, isCurrent() else { return nil }
            guard result.plan_id == plan.plan_id, result.subject_id == plan.subject_id, result.revision == plan.revision,
                  result.status == "confirmed", !result.secret_confirmation_required,
                  result.condition == plan.condition, result.recipient_label == plan.recipient_label,
                  result.episode_count == plan.episode_count, result.voice_allowed == plan.voice_allowed else { throw APIError.invalidResponse }
            return result
        } catch {
            if generation == request, isCurrent() { notice = "原暗号未核验成功。请私下核对后重试；若已撤销，请关闭并刷新托付列表。" }
            return nil
        }
    }
}

struct EntrustmentView: View {
    @EnvironmentObject private var model: AppModel
    @State private var plans: [GuestEntrustmentPlan] = []
    @State private var oldPlans: [EntrustmentPlan] = []
    @State private var received: [EntrustmentPlan] = []
    @State private var reviews: [LegacyReview] = []
    @State private var scope: ReviewScope?
    @State private var notice: String?
    @State private var creating = false
    @State private var confirmingSecret: GuestEntrustmentPlan?
    @State private var revokingPlanIDs = Set<String>()
    @State private var deviceCaptureActive = false
    private var captureBlocked: Bool { model.entrustmentCaptureState.blocked || deviceCaptureActive }
    var body: some View {
        List {
            Section("留给亲友的专属记忆") {
                Text("亲友以游客身份进入，不需要账号。彼此私下知晓的暗号，只打开你选定的完整来源；不会开放全部人物资料。")
                    .font(.footnote).foregroundStyle(Ink.muted)
                Button("留下数字托付", systemImage: "plus") { creating = true }.disabled(model.pairing == nil || model.isGuestMode || captureBlocked)
                if captureBlocked { Text("请先结束录音、录音豆采集或通话，再私下设置暗号。") .font(.footnote).foregroundStyle(Ink.muted) }
                if scope == model.pairing.map(ReviewScope.init) {
                    ForEach(plans) { plan in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("给\(plan.recipient_label)").font(.headline)
                            Text("\(plan.episode_count) 份完整来源 · \(plan.condition == "immediate" ? "现在开放" : "照护人核验后开放") · \(plan.status == "confirmed" ? "有效" : "已撤销")").font(.caption).foregroundStyle(Ink.muted)
                            if plan.status == "confirmed" {
                                if plan.secret_confirmation_required {
                                    Text("需要本人重新私下核验原暗号，亲友才能继续打开这份记忆。原有来源和开放条件保持原样。")
                                        .font(.footnote).foregroundStyle(Ink.muted)
                                    Button("重新核验原暗号") { confirmingSecret = plan }
                                        .disabled(captureBlocked || revokingPlanIDs.contains(plan.id))
                                }
                                Button("撤销这份托付", role: .destructive) { Task { await revoke(plan.id, legacy: false) } }
                                    .disabled(revokingPlanIDs.contains(plan.id))
                            }
                        }.padding(.vertical, 5)
                    }
                }
            }
            if scope == model.pairing.map(ReviewScope.init), !oldPlans.isEmpty || !received.isEmpty {
                Section("原有账号托付") {
                    Text("旧计划保留原账号限制，不会自动改成游客暗号。需要新方式时，请重新预览范围并创建托付。")
                        .font(.footnote).foregroundStyle(Ink.muted)
                    ForEach(oldPlans) { plan in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("给\(plan.recipient_label) · \(plan.episode_count) 份来源")
                            if plan.status == "confirmed" { Button("撤销旧计划", role: .destructive) { Task { await revoke(plan.id, legacy: true) } } }
                            else { Text("已撤销").font(.caption).foregroundStyle(Ink.muted) }
                        }
                    }
                    ForEach(received) { plan in Text("原账号收到的托付 · \(plan.recipient_label)").foregroundStyle(Ink.muted) }
                }
            }
            if scope == model.pairing.map(ReviewScope.init), !reviews.isEmpty {
                Section("我受托照护的空间") { ForEach(reviews) { review in
                    NavigationLink { LegacyVerificationView(review: review) } label: { Label(review.subject_label, systemImage: "person.badge.shield.checkmark") }
                } }
            }
            if let notice { Text(notice).font(.footnote).foregroundStyle(Ink.muted) }
        }.navigationTitle("数字托付").navigationBarTitleDisplayMode(.inline)
            .task(id: model.pairing.map(ReviewScope.init)) { await load() }.refreshable { await load() }
            .onReceive(model.devices.$recording) { deviceCaptureActive = $0 }
            .sheet(isPresented: $creating) { NavigationStack { EntrustmentSetupView(onSaved: { creating = false; Task { await load() } }) } }
            .sheet(item: $confirmingSecret) { plan in
                NavigationStack {
                    EntrustmentSecretIndexView(plan: plan, isCurrent: {
                        scope == model.pairing.map(ReviewScope.init) && !model.isGuestMode && confirmingSecret?.id == plan.id &&
                        !revokingPlanIDs.contains(plan.id) && plans.contains { $0.id == plan.id && $0.revision == plan.revision && $0.status == "confirmed" }
                    }, onConfirmed: { result in
                        guard scope == model.pairing.map(ReviewScope.init), confirmingSecret?.id == result.id,
                              !revokingPlanIDs.contains(result.id),
                              let index = plans.firstIndex(where: { $0.id == result.id && $0.revision == result.revision && $0.status == "confirmed" }) else { return }
                        plans[index] = result; confirmingSecret = nil; notice = "原暗号已重新核验，托付来源和开放条件保持原样。"
                    })
                }
            }
            .onChange(of: model.pairing.map(ReviewScope.init)) { _, _ in confirmingSecret = nil }
    }
    private func load() async {
        plans = []; oldPlans = []; received = []; reviews = []; scope = nil; notice = nil
        guard let pairing = model.pairing, let client = model.dialogueClient(), !model.isGuestMode else { return }
        let current = ReviewScope(pairing)
        async let new = try? client.guestEntrustments(subject: pairing.subjectID)
        async let old = try? client.ownEntrustments(subject: pairing.subjectID)
        async let incoming = try? client.receivedEntrustments()
        async let reviewData = try? client.request("/api/v1/legacy/reviews")
        let (n, o, r, data) = await (new, old, incoming, reviewData)
        guard !Task.isCancelled, model.pairing.map(ReviewScope.init) == current else { return }
        plans = n ?? []; oldPlans = o ?? []; received = r ?? []
        if let data { reviews = (try? JSONDecoder().decode(LegacyReviews.self, from: data).items) ?? [] }
        scope = current
        if n == nil { notice = "新托付资料暂未读取到，可以下拉重试。" }
    }
    private func revoke(_ id: String, legacy: Bool) async {
        guard let pairing = model.pairing, scope == ReviewScope(pairing), let client = model.dialogueClient(), !revokingPlanIDs.contains(id) else { return }
        let current = ReviewScope(pairing)
        revokingPlanIDs.insert(id); if confirmingSecret?.id == id { confirmingSecret = nil }
        defer { revokingPlanIDs.remove(id) }
        do {
            if legacy { try await client.revokeEntrustment(id) } else { try await client.revokeGuestEntrustment(id) }
            guard model.pairing.map(ReviewScope.init) == current else { return }
            await load()
        } catch { if model.pairing.map(ReviewScope.init) == current { notice = "暂未撤销成功，请重试。" } }
    }
}

private struct EntrustmentSecretIndexView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var draft = EntrustmentSetupModel()
    @StateObject private var confirmation = EntrustmentSecretIndexModel()
    @State private var scope: ReviewScope?
    @State private var showSecret = false
    @State private var deviceCaptureActive = false
    let plan: GuestEntrustmentPlan
    let isCurrent: () -> Bool
    let onConfirmed: (GuestEntrustmentPlan) -> Void
    private var captureBlocked: Bool { model.entrustmentCaptureState.blocked || deviceCaptureActive }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("给\(plan.recipient_label)的托付").font(.headline)
                Text("请本人重新输入或在本机录下原先留下的完整暗号。这只恢复暗号核验，不更换暗号、来源、许可或开放条件。")
                    .font(.footnote).foregroundStyle(Ink.muted)
                if captureBlocked {
                    Text("请先结束录音、录音豆采集或通话。暗号输入已清除。")
                        .font(.footnote).foregroundStyle(Ink.muted)
                } else {
                    Group {
                        if showSecret { TextField("原来的完整暗号", text: $draft.secret,
                            prompt: Text("原来的完整暗号").foregroundStyle(Ink.muted), axis: .vertical).lineLimit(2...5) }
                        else { SecureField("原来的完整暗号", text: $draft.secret,
                            prompt: Text("原来的完整暗号").foregroundStyle(Ink.muted)) }
                    }.foregroundStyle(Ink.text).textFieldStyle(.roundedBorder).textInputAutocapitalization(.never)
                        .autocorrectionDisabled().privacySensitive().disabled(draft.isRecording || draft.isTranscribing)
                    Toggle("展开逐字核对", isOn: $showSecret)
                    Button(draft.isRecording ? "说完了，仅在本机转写" : draft.isTranscribing ? "本机离线转写中…" : "用本机离线语音录入") {
                        Task {
                            if draft.isRecording { await draft.finishRecording(); showSecret = true }
                            else { await draft.startRecording(captureAllowed: { !captureBlocked && isCurrent() }) }
                        }
                    }.disabled(draft.isTranscribing)
                    Text("录音仅在本机离线转写，临时原音随后清除；不可用时请输入。核验内容只发送到这份托付的专用接口。")
                        .font(.footnote).foregroundStyle(Ink.muted)
                    Toggle("我已逐字核对，这是原来的暗号", isOn: $draft.secretReviewed)
                        .disabled(!draft.secretMeetsMinimum || draft.isRecording || draft.isTranscribing)
                    Button(confirmation.isBusy ? "正在核验…" : "确认原暗号") { Task { await confirm() } }
                        .buttonStyle(.borderedProminent)
                        .disabled(!draft.secretMeetsMinimum || !draft.secretReviewed || draft.isRecording || draft.isTranscribing)
                }
                if let notice = confirmation.notice ?? draft.notice { Text(notice).font(.footnote).foregroundStyle(Ink.muted) }
            }.padding(RMSpacing.page).disabled(confirmation.isBusy)
        }.background(Ink.paper).navigationTitle("重新核验原暗号").navigationBarTitleDisplayMode(.inline).rmDismissibleKeyboard()
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { clear(); dismiss() } } }
            .task { scope = model.pairing.map(ReviewScope.init) }
            .onReceive(model.devices.$recording) { deviceCaptureActive = $0 }
            .onChange(of: captureBlocked) { _, blocked in if blocked { clear() } }
            .onChange(of: model.pairing.map(ReviewScope.init)) { _, _ in clear(); dismiss() }
            .onChange(of: scenePhase) { _, phase in if phase == .background { clear() } }
            .onDisappear { clear() }
            .interactiveDismissDisabled(draft.isRecording || draft.isTranscribing)
    }
    private func clear() { showSecret = false; confirmation.clear(draft: draft) }
    private func confirm() async {
        guard let owner = model.pairing, scope == ReviewScope(owner), owner.subjectID == plan.subject_id,
              !model.isGuestMode, !captureBlocked, isCurrent(), let api = model.dialogueClient() else { clear(); return }
        guard let result = await confirmation.confirm(plan: plan, draft: draft, isCurrent: {
            model.pairing.map(ReviewScope.init) == scope && !model.isGuestMode && !captureBlocked && isCurrent()
        }, submit: { secret in try await api.confirmGuestEntrustmentSecret(plan.id, secret: secret) }) else { return }
        onConfirmed(result); dismiss()
    }
}

struct EntrustmentSetupView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var draft = EntrustmentSetupModel()
    @State private var showSecret = false
    @State private var busy = false
    @State private var error: String?
    @State private var scope: ReviewScope?
    @State private var deviceCaptureActive = false
    private var captureBlocked: Bool { model.entrustmentCaptureState.blocked || deviceCaptureActive }
    var onSaved: () -> Void = {}
    private var prompt: String {
        switch draft.stage {
        case .recipient: "这份记忆，你想留给谁？可以写称呼、名字，或你们之间的关系。"
        case .secret: "有什么只有你们才知道的小细节？把它留作打开这份记忆的暗号。"
        case .sources: "你希望对方打开哪些记忆？我们一起核对每一段完整内容。"
        case .conditions: "你希望对方现在就能打开，还是等照护人核验交接后？"
        case .confirmation: "最后核对一次。这份托付只属于下面这个人和你选定的记忆。"
        }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Text("Twin · 数字托付 \(draft.stage.rawValue + 1)/5").font(.caption).foregroundStyle(Ink.muted)
                Text(prompt).font(.title3).rmCardSurface()
                if captureBlocked { Text("正在录音或通话。请先结束手机与录音豆的采集，再私下设置暗号；当前暗号输入已清除。") .font(.footnote).foregroundStyle(Ink.muted) }
                else { stageContent }
                if let notice = draft.notice { Text(notice).font(.footnote).foregroundStyle(Ink.muted) }
                if let error { Text(error).font(.footnote).foregroundStyle(.red) }
                HStack {
                    if draft.stage != .recipient { Button("上一步") { model.stopPlayback(); draft.stage = .init(rawValue: draft.stage.rawValue - 1) ?? .recipient } }
                    Spacer()
                    if draft.stage == .confirmation {
                        Button(busy ? "正在保存…" : "确认并留下这份托付") { Task { await save() } }.buttonStyle(.borderedProminent).disabled(!draft.canContinue || busy)
                    } else { Button("继续") { model.stopPlayback(); draft.advance() }.buttonStyle(.borderedProminent).disabled(!draft.canContinue || busy) }
                }.disabled(draft.isRecording || draft.isTranscribing || captureBlocked)
            }.padding(RMSpacing.page).disabled(busy)
        }.background(Ink.paper).navigationTitle("留下数字托付").navigationBarTitleDisplayMode(.inline).rmDismissibleKeyboard()
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { draft.clearSecret(); dismiss() }.disabled(busy) } }
            .task { scope = model.pairing.map(ReviewScope.init) }
            .onReceive(model.devices.$recording) { deviceCaptureActive = $0 }
            .onChange(of: captureBlocked) { _, blocked in if blocked { draft.clearSecret(); showSecret = false; if draft.stage != .recipient { draft.stage = .secret } } }
            .onChange(of: model.pairing.map(ReviewScope.init)) { _, _ in draft.clearSecret(); dismiss() }
            .onChange(of: scenePhase) { _, phase in if phase == .background { model.stopPlayback(); draft.clearSecret(); showSecret = false; if draft.stage != .recipient { draft.stage = .secret } } }
            .onDisappear { model.stopPlayback(); draft.clearSecret() }
            .interactiveDismissDisabled(busy || draft.isRecording || draft.isTranscribing)
    }
    @ViewBuilder private var stageContent: some View {
        switch draft.stage {
        case .recipient:
            TextField("例如：女儿小雨、一起长大的阿明", text: $draft.recipientLabel,
                      prompt: Text("例如：女儿小雨、一起长大的阿明").foregroundStyle(Ink.muted))
                .foregroundStyle(Ink.text).textFieldStyle(.roundedBorder)
            Text("亲友无需注册或登录。他们进入游客 Twin，私下说出暗号，才会打开对应的记忆。请私下告诉对方暗号。")
                .font(.footnote).foregroundStyle(Ink.muted)
        case .secret:
            Text("想想一件共同经历中的细微点：当时一句特别的话、只有你们懂的称呼和小插曲。避免姓名、生日、公开故事或容易猜的短句。")
                .font(.footnote).foregroundStyle(Ink.muted)
            Group {
                if showSecret { TextField("私下的暗号", text: $draft.secret,
                    prompt: Text("私下的暗号").foregroundStyle(Ink.muted), axis: .vertical).lineLimit(2...5) }
                else { SecureField("私下的暗号", text: $draft.secret,
                    prompt: Text("私下的暗号").foregroundStyle(Ink.muted)) }
            }.foregroundStyle(Ink.text).textFieldStyle(.roundedBorder).textInputAutocapitalization(.never).autocorrectionDisabled().privacySensitive()
                .disabled(draft.isRecording || draft.isTranscribing).accessibilityIdentifier("entrustment.secret")
            Toggle("展开核对暗号文字", isOn: $showSecret)
            Button(draft.isRecording ? "说完了，仅在本机转写" : draft.isTranscribing ? "本机离线转写中…" : "用本机离线语音录入") {
                Task {
                    if draft.isRecording { await draft.finishRecording(); showSecret = true }
                    else { await draft.startRecording(captureAllowed: { !model.entrustmentCaptureState.blocked }) }
                }
            }.disabled(draft.isTranscribing)
            Text("这里的暗号不会进入普通聊天、记忆或云端 AI。录音最多45秒，仅用于本机离线识别，随后清除；不支持时请直接输入。保存时只交给专门的托付接口。")
                .font(.footnote).foregroundStyle(Ink.muted)
            Text(draft.secretMeetsMinimum ? "已满足基础长度和多样性检查，仍需确保不易猜到。" : "至少12个有效文字或字母数字，包含足够不同的内容。关键是私密细节，不是重复凑字数。")
                .font(.footnote).foregroundStyle(Ink.muted)
            Toggle("我已逐字核对，记得这句暗号", isOn: $draft.secretReviewed).disabled(!draft.secretMeetsMinimum || draft.isRecording || draft.isTranscribing)
        case .sources:
            Text("选择一段来源会同时开放全文、整段原音及其中整理出的记忆，不是只开放一张故事卡片。")
                .font(.footnote).foregroundStyle(Ink.muted)
            if !model.episodes.contains(where: { $0.status == "ready" }) { Text("暂无已核对的来源。请先录音或录入文字并核对，再来选择。") .font(.footnote).foregroundStyle(Ink.muted) }
            ForEach(model.episodes.filter { $0.status == "ready" }) { episode in
                Button {
                    if draft.selectedEpisodeIDs.contains(episode.id) { draft.selectedEpisodeIDs.remove(episode.id) }
                    else { draft.selectedEpisodeIDs.insert(episode.id) }
                } label: { HStack { Image(systemName: draft.selectedEpisodeIDs.contains(episode.id) ? "checkmark.circle.fill" : "circle"); Text(episode.transcript ?? episode.recorded_at).lineLimit(3).foregroundStyle(Ink.text) } }
            }
            Button("预览所选完整来源") { Task { await preview() } }.disabled(busy || draft.selectedEpisodeIDs.isEmpty)
            if let preview = draft.preview {
                Text(preview.notice).font(.footnote)
                ForEach(preview.items) { source in
                    VStack(alignment: .leading, spacing: 12) {
                        Text("完整来源 · \(source.recorded_at)").font(.headline)
                        Text(source.transcript)
                        if let supplement = source.supplement, !supplement.isEmpty { Text(supplement) }
                        if source.hasAudio { Button("回听整段原音") { Task { await model.playOriginal(episodeID: source.id) } } }
                        else { Text("文字来源，无原音").font(.footnote).foregroundStyle(Ink.muted) }
                        if !source.memories.isEmpty { Text("连带开放的记忆").font(.subheadline); ForEach(Array(source.memories.enumerated()), id: \.offset) { _, text in Text(text) } }
                    }.rmCardSurface()
                }
                Toggle("我已核对以上全文、原音和连带记忆", isOn: $draft.sourceReviewed)
            }
        case .conditions:
            Toggle("照护人核验交接后开放", isOn: $draft.future)
            if draft.future {
                TextField("事先指定的照护人登录账号", text: $draft.steward,
                          prompt: Text("事先指定的照护人登录账号").foregroundStyle(Ink.muted))
                    .foregroundStyle(Ink.text).textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(.roundedBorder)
                Text("照护人是独立负责记录核验的人，需要账号；接收这份记忆的亲友无需账号。声音、暗号和 Twin 都不能自动判断交接。交接核验后历史人物模型冻结。")
                    .font(.footnote).foregroundStyle(Ink.muted)
            } else { Text("保存后，亲友即可在游客 Twin 私下说出暗号。其他人仍只看到通常开放的资料。") .font(.footnote).foregroundStyle(Ink.muted) }
            Toggle("允许用我的已授权音色回答", isOn: $draft.allowVoice)
            Text("对方的提问不会写入你的记忆、训练资料或人物模型。你可以随时撤销托付。") .font(.footnote).foregroundStyle(Ink.muted)
        case .confirmation:
            Text("留给：\(draft.recipientLabel)").font(.headline)
            Text("范围：\(draft.preview?.episode_ids.count ?? 0) 份完整来源与其中的记忆")
            Text(draft.future ? "开放时间：照护人核验交接后" : "开放时间：现在")
            Text(draft.allowVoice ? "回答声音：允许已授权本人音色" : "回答声音：不开放本人音色")
            Text("暗号已在本机核对，此处不再次显示。亲友说对暗号后可短时访问；离开、到期或撤销后锁上。") .font(.footnote).foregroundStyle(Ink.muted)
            Toggle("我确认暗号包含仅彼此知晓、无法从公开资料猜到的细节", isOn: $draft.privateDetailConfirmed)
            Toggle("我确认将这些完整来源只托付给上述亲友", isOn: $draft.scopeConfirmed)
        }
    }
    private func preview() async {
        guard let owner = model.pairing, ReviewScope(owner) == scope, let api = model.dialogueClient(), !model.isGuestMode else { return }
        busy = true; error = nil; defer { busy = false }
        let selected = draft.selectedEpisodeIDs
        do {
            let reply = try await api.previewGuestEntrustment(subject: owner.subjectID, episodes: selected.sorted())
            guard model.pairing.map(ReviewScope.init) == scope, selected == draft.selectedEpisodeIDs else { return }
            try draft.acceptPreview(reply)
        } catch { self.error = "范围预览未完成：\(error.localizedDescription)" }
    }
    private func save() async {
        guard let owner = model.pairing, ReviewScope(owner) == scope, let api = model.dialogueClient(), draft.canContinue, !model.isGuestMode else { return }
        busy = true; error = nil; defer { busy = false }
        do {
            if draft.future {
                _ = try await api.request("/api/v1/subjects/\(owner.subjectID)/legacy/steward", method: "PUT",
                    body: JSONSerialization.data(withJSONObject: ["steward_username": draft.steward.trimmingCharacters(in: .whitespacesAndNewlines)]), contentType: "application/json")
            }
            guard model.pairing.map(ReviewScope.init) == scope else { return }
            let consent = try await api.grantConsent(subjectID: owner.subjectID, scope: "DIGITAL_HANDOVER", evidenceRef: "ios-confirm-guest-entrustment").id
            var voice: String?
            if draft.allowVoice {
                let profile = try await api.realtimeProfile(subjectID: owner.subjectID)
                guard profile.ready, let id = profile.voice_consent_id else { throw APIError.server(409, "请先准备并确认本人音色，再开放给亲友。") }
                voice = id
            }
            guard model.pairing.map(ReviewScope.init) == scope else { return }
            let payload = try draft.makeDraft(handoverConsentID: consent, voiceConsentID: voice)
            try await api.createGuestEntrustment(subject: owner.subjectID, draft: payload)
            draft.clearSecret(); guard model.pairing.map(ReviewScope.init) == scope else { return }; onSaved(); dismiss()
        } catch { self.error = "未保存：\(error.localizedDescription)" }
    }
}

private struct LegacyVerificationView: View {
    @EnvironmentObject private var model: AppModel
    let review: LegacyReview
    @State private var reference = ""
    @State private var busy = false
    @State private var notice: String?
    var body: some View {
        Form {
            Section("交接核验") {
                Text("你是事先指定的照护人。核实交接条件后，在这里记录核验依据。声音、暗号和 Twin 的回答都不能自行激活交接。").font(.footnote)
                TextField("核验说明或记录编号", text: $reference, axis: .vertical)
                Button("记录已核验的交接并开放托付") { Task { await save(true) } }.disabled(busy || reference.isEmpty)
                Button("有争议，暂停交接后开放", role: .destructive) { Task { await save(false) } }.disabled(busy || reference.isEmpty)
            }
            if let notice { Text(notice).font(.footnote) }
        }.navigationTitle(review.subject_label).rmDismissibleKeyboard()
    }
    private func save(_ verified: Bool) async {
        guard let pairing = model.pairing else { return }; let scope = ReviewScope(pairing); busy = true; defer { busy = false }
        do {
            let api = try APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token)
            _ = try await api.request("/api/v1/subjects/\(review.subject_id)/legacy/verify", method: "POST",
                body: JSONSerialization.data(withJSONObject: ["verification_ref": reference, "verified": verified]), contentType: "application/json")
            guard model.pairing.map(ReviewScope.init) == scope else { return }
            notice = verified ? "交接已记录，历史人物模型已冻结；指定亲友可在游客模式私下说出暗号。" : "交接后开放已暂停。"
        } catch { guard model.pairing.map(ReviewScope.init) == scope else { return }; notice = error.localizedDescription }
    }
}

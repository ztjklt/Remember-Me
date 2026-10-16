import Foundation
import AVFoundation
import SwiftUI
import CryptoKit
import Combine
import UIKit

struct RecordingDraft: Codable, Identifiable, Sendable {
    let id: String
    let fileURL: URL
    let recordedAt: Date
    let durationMS: Int
    let questionID: String?
    let calibrationID: String?
    let consentConfirmedAt: Date
    var captureSource: String? = nil
    var captureMetadata: [String: String]? = nil
    func withDuration(_ milliseconds: Int) -> RecordingDraft {
        var next = RecordingDraft(id: id, fileURL: fileURL, recordedAt: recordedAt, durationMS: milliseconds,
                                  questionID: questionID, calibrationID: calibrationID, consentConfirmedAt: consentConfirmedAt)
        next.captureSource = captureSource; next.captureMetadata = captureMetadata
        return next
    }
}

// The protected local index stores questions and opaque answer IDs, never
// answer text or evidence. Answers are revalidated by the backend on restore.
struct TwinChatStoredTurn: Codable {
    let id: UUID
    let question: String
    let answerID: String?
    var previousAnswerID: String? = nil
    var conversationMode: Bool? = nil
    var requestID: String? = nil
}

struct TwinChatStore {
    let root: URL
    func file(_ pairing: Pairing) throws -> URL {
        let scope = try JSONEncoder().encode([pairing.baseURL, pairing.fingerprint, pairing.actorID, pairing.subjectID])
        let name = SHA256.hash(data: scope).map { String(format: "%02x", $0) }.joined()
        return root.appendingPathComponent(name + ".json")
    }
    func load(_ pairing: Pairing) throws -> [TwinChatStoredTurn] {
        let url = try file(pairing)
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        let data = try Data(contentsOf: url)
        guard data.count <= 1_000_000 else { throw APIError.invalidResponse }
        let items = try JSONDecoder().decode([TwinChatStoredTurn].self, from: data)
        guard items.count <= 20, Set(items.map(\.id)).count == items.count else { throw APIError.invalidResponse }
        return items
    }
    func save(_ history: TwinChatHistory, pairing: Pairing) throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        var excludedRoot = root
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try excludedRoot.setResourceValues(values)
        let items = history.turns.suffix(20).map { TwinChatStoredTurn(id: $0.id, question: $0.question,
            answerID: $0.answer?.id ?? $0.savedAnswerID, previousAnswerID: $0.previousAnswerID,
            conversationMode: $0.conversationMode, requestID: $0.requestID) }
        try JSONEncoder().encode(items).write(to: file(pairing), options: [.atomic, .completeFileProtection])
    }
    func remove(_ pairing: Pairing) throws {
        let url = try file(pairing)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }
}

struct TwinChatTurn: Identifiable {
    let id: UUID
    let question: String
    var answer: TwinAnswerRecord?
    var failure: String?
    var invalidated = false
    var savedAnswerID: String?
    var previousAnswerID: String?
    var conversationMode: Bool?
    var requestID: String?
}

struct TwinChatHistory {
    private(set) var turns: [TwinChatTurn] = []
    init(stored: [TwinChatStoredTurn] = []) {
        turns = stored.map { TwinChatTurn(id: $0.id, question: $0.question,
                                         failure: $0.answerID == nil ? "上次请求未完成，可以重试。" : nil,
                                         savedAnswerID: $0.answerID, previousAnswerID: $0.previousAnswerID,
                                         conversationMode: $0.conversationMode, requestID: $0.requestID) }
    }
    mutating func begin(_ question: String, conversationMode: Bool = false) -> UUID {
        let id = UUID()
        let parent = turns.reversed().compactMap { $0.answer?.id ?? $0.savedAnswerID }.first
        turns.append(TwinChatTurn(id: id, question: question, previousAnswerID: conversationMode ? parent : nil,
                                  conversationMode: conversationMode))
        return id
    }
    mutating func receive(_ answer: TwinAnswerRecord, for turnID: UUID? = nil) {
        if let index = turns.firstIndex(where: { $0.id == turnID || $0.answer?.id == answer.id }) {
            turns[index].answer = answer; turns[index].failure = nil; turns[index].savedAnswerID = answer.id
            turns[index].invalidated = answer.stale
        } else if turnID == nil && turns.isEmpty {
            turns.append(TwinChatTurn(id: UUID(), question: answer.question, answer: answer,
                                      invalidated: answer.stale))
        }
        if answer.stale { invalidateAnswers() }
    }
    mutating func fail(_ id: UUID, message: String) {
        guard let index = turns.firstIndex(where: { $0.id == id }) else { return }
        turns[index].failure = message
    }
    mutating func renewRequest(_ id: UUID) {
        guard let index = turns.firstIndex(where: { $0.id == id }), turns[index].savedAnswerID == nil else { return }
        turns[index].requestID = UUID().uuidString
    }
    mutating func retry(_ id: UUID) -> Bool {
        guard let index = turns.firstIndex(where: { $0.id == id }), turns[index].failure != nil,
              turns[index].savedAnswerID == nil else { return false }
        turns[index].failure = nil; return true
    }
    mutating func unavailable(_ id: UUID, message: String) {
        guard let index = turns.firstIndex(where: { $0.id == id }) else { return }
        turns[index].answer = nil; turns[index].failure = message
    }
    mutating func invalidateAnswers() {
        for index in turns.indices {
            if turns[index].answer != nil { turns[index].invalidated = true }
            else if turns[index].savedAnswerID == nil && turns[index].failure == nil {
                turns[index].failure = "资料已更新，请重新发送这条消息。"
                turns[index].requestID = UUID().uuidString
            }
        }
    }
    mutating func removeAnswer(_ answerID: String) {
        turns.removeAll { ($0.answer?.id ?? $0.savedAnswerID) == answerID }
        for index in turns.indices where turns[index].previousAnswerID == answerID {
            turns[index].previousAnswerID = nil
        }
        invalidateAnswers()
    }
}

@MainActor
final class AppModel: ObservableObject {
    let personReview: PersonReviewModel
    @Published var showConnection = false
    @Published var pairing: Pairing?
    @Published private(set) var isGuestMode = false
    let guestAccess = GuestAccessModel()
    private var guestObservation: AnyCancellable?
    @Published var pairingServer = ""
    @Published var pairingCode = ""
    @Published var pairingFingerprint = ""
    @Published var cloudSpaces: [CloudSpace] = []
    @Published var cloudCapabilities: BackendCapabilities?
    @Published var connectionStatus = "尚未检查连接"
    private var pendingCloudLogin: CloudLoginReply?
    private var auxiliaryCloudPolicy: String?
    private var auxiliaryReadingPrompt: String?
    private var auxiliaryRecordingOwner: RecordingOwner?
    private var auxiliaryStartGeneration = UUID()
    private var captureResetObservation: AnyCancellable?
    var recordingStartBlocked: Bool { isGuestMode || realtimeVoice.isActive || isSpeakerRecording || isBusy || personReview.isMutating || isPollingEpisode || isRecording || isStartingRecording || isPreparingAutomaticTranscription || isLocalTranscribing || isQueryRecording || isVoiceRecording }
    // Local utility imports write separate files and never use the audio session.
    // Keep their owner stable without making the foreground microphone wait.
    var connectionChangeBlocked: Bool { recordingStartBlocked || isImportingDeviceRecording || isSyncingDeviceRecordings }
    var hasSavedMacConnection: Bool { PairingStore.load(account: "last-mac-pairing") != nil }
    var otherServiceRecordingCount: Int { localRecordings.count - visibleLocalRecordings.count }
    var recordingTransferNotice: String {
        guard let pairing else { return "原音先留在手机。录完后尝试在 iPhone 上转成文字；设备不支持时保留原音，连接服务后可继续。" }
        return pairing.isCloud ? "原音先留在手机。录完自动转写；服务支持时由模型辅助校对机器文字。修改或补充后保存到记忆，原音与机器稿保留。可在「我的」关闭自动转写。" : "原音先留在手机。录完后发到配对的 Mac 转写；网络中断时保留原音，可重试。"
    }
    var organizeNotice: String {
        let base = pairing?.isCloud == true ? "保存后将核对文字和补充说明交给模型整理记忆，原音不随本次文字整理发送给语言模型。" : "配对的 Mac 会把你核对后的文字发送给 DeepSeek 提取记忆。原始录音不随本次操作发送给该服务。"
        return base + ((cloudCapabilities?.automatic_capture_version ?? 0) >= 1 && cloudCapabilities?.automatic_profile_analysis == true && cloudConsentID != nil
            ? "同时按现有云端问答授权，在后台累计整理人物资料；AI 观察仍待你核对。" : "")
    }
    @Published var memories: [MemoryRecord] = []
    @Published var episodes: [EpisodeRecord] = []
    @Published var domains: [DomainRecord] = []
    @Published var graphFacts: [GraphFactRecord] = []
    @Published var questions: [QuestionRecord] = []
    @Published var chatHistoryMemory: ChatHistoryMemory?
    @Published var isLoadingChatMemory = false
    @Published var modelVersion = 0
    @Published var draft: RecordingDraft?
    @Published var localRecordings: [LocalRecording] = []
    @Published var isLocalTranscribing = false
    @Published private(set) var isStartingRecording = false
    @Published var isRecorderPresented = false
    @Published private(set) var isPreparingAutomaticTranscription = false
    var automaticTranscriptionEnabled: Bool {
        get { defaults.object(forKey: "automatic-transcription-enabled") == nil || defaults.bool(forKey: "automatic-transcription-enabled") }
        set { objectWillChange.send(); defaults.set(newValue, forKey: "automatic-transcription-enabled") }
    }
    @Published var isPollingEpisode = false
    @Published var episodeID: String?
    @Published var processingStatus = ""
    @Published var transcriptDraft = ""
    @Published var transcriptSupplement = ""
    @Published var currentTranscriptReview: TranscriptReview?
    @Published private(set) var savingCaptureID: String?
    @Published private(set) var lastSavedCaptureID: String?
    private var isRefreshingCaptureDrafts = false
    @Published var isTranscriptReviewReady = false
    @Published var errorMessage: String?
    @Published var isBusy = false
    @Published var dialogueMaterials: [DialogueMaterial] = []
    var dialogueMaterialOwner: RecordingOwner?
    @Published var twinArchive: [HistoricalChatTurn] = []
    @Published var twinArchiveCursor: String?
    @Published var twinArchiveError: String?
    @Published private(set) var isLoadingTwinArchive = false
    var twinArchiveOwner: RecordingOwner?
    private var twinArchiveRequest = UUID()
    var visibleTwinArchive: [HistoricalChatTurn] {
        !isGuestMode && cloudConsentID != nil && pairing.map(RecordingOwner.init) == twinArchiveOwner ? twinArchive : []
    }
    func dialogueClient() -> APIClient? { isGuestMode ? nil : client }
    @Published var isSpeakerRecording = false
    @Published var isRecording = false
    @Published var isPaused = false
    @Published var recordedSeconds = 0
    @Published var meterLevels: [CGFloat] = Array(repeating: 0.16, count: 27)
    @Published var isPlaying = false
    @Published var playbackID: String?
    @Published var playbackPosition: TimeInterval = 0
    @Published var playbackDuration: TimeInterval = 0
    @Published var playbackLoading = false
    @Published private(set) var playbackAudioLevel: Double?
    private var playbackTimer: Timer?
    private var playbackMeterGeneration = UUID()
    private var playbackPositionTick = 0
    private var playbackRequestID: UUID?
    @Published var queryDraft = ""
    @Published var twinAnswer: TwinAnswerRecord? {
        didSet { if twinAnswer == nil { twinChat = TwinChatHistory() } }
    }
    @Published var twinChat = TwinChatHistory()
    @Published private(set) var isAskingTwin = false
    @Published private(set) var isRestoringChat = false
    @Published var chatNotice: String?
    private var restoredChatScope: ReviewScope?
    private var chatRestoreRequestID: UUID?
    @Published var cloudConsentID: String?
    let devices = DeviceConnectionsModel()
    @Published private(set) var isSyncingDeviceRecordings = false
    @Published private(set) var deviceUploadingRecordingID: String?
    @Published var deviceSyncNotice: String?
    private var deviceUploadTask: Task<Void, Never>?
    private var deviceUploadGeneration = UUID()
    let realtimeVoice = TwinVoiceCallModel()
    @Published var realtimeVoiceReview: RealtimeVoiceReview?
    var personalVoiceAccepted: Bool {
        realtimeVoice.profile?.ready == true && realtimeVoiceReview?.profile_id == realtimeVoice.profile?.profile_id && realtimeVoiceReview?.status == "accepted"
    }
    // Remember an explicit choice for this owner and this exact approved profile.
    // A newly ready profile still requires the owner's listening review.
    var useDefaultRealtimeVoice: Bool {
        get {
            guard personalVoiceAccepted, realtimeVoice.capabilities?.personal_voice_available != false else { return true }
            guard let key = realtimeVoiceChoiceKey else { return false }
            return defaults.object(forKey: key) as? Bool ?? false
        }
        set {
            guard let key = realtimeVoiceChoiceKey else { return }
            objectWillChange.send()
            defaults.set(newValue, forKey: key)
        }
    }
    private var realtimeVoiceChoiceKey: String? {
        guard let pairing, let profile = realtimeVoice.profile?.profile_id else { return nil }
        return "voice-default-choice-" + RecordingOwner(pairing).storageNamespace + "-" + profile
    }
    private var realtimeObservation: AnyCancellable?
    @Published var voiceConsentID: String?
    @Published var voiceProfileReady = false
    static let voiceReadingPrompt = "今天我想留下一段自己的声音。希望以后听见它时，还能想起现在的自己。"
    @Published var voiceSampleReadingPrompt: String?
    @Published var voiceSampleTranscript = ""
    @Published var voiceSampleURL: URL?
    @Published var isQueryRecording = false
    @Published var isVoiceRecording = false
    @Published var memorySearchQuery = "" {
        didSet { resetMemorySearch() }
    }
    @Published var memorySearchResults: [MemorySearchRecord] = []
    @Published var isSearchingMemories = false
    @Published var memorySearchCompleted = false
    @Published var memorySearchError: String?
    private var memorySearchRequestID: UUID?

    private func resetMemorySearch() {
        memorySearchRequestID = nil
        memorySearchResults = []; memorySearchCompleted = false
        memorySearchError = nil; isSearchingMemories = false
    }
    @Published var auxiliarySeconds = 0
    @Published var calibrationRun: CalibrationRecord?

    private var recorder: AVAudioRecorder?
    private let recordingActivity = RecordingActivityController()
    private let recordingEvents = RecordingAudioEvents()
    private var audioObservations: Set<AnyCancellable> = []
    private var resumeAfterAudioInterruption = false
    private var lastRecordingCheckpoint = Date.distantPast
    @Published var showActiveRecording = false
    #if DEBUG
    @Published var liveActivityPreviewStatus = "未开始"
    func startLiveActivityPreview() {
        guard liveActivityPreviewStatus == "未开始" else { return }
        liveActivityPreviewStatus = recordingActivity.previewForUITest() ? "系统实时活动已创建" : "系统实时活动不可用：" + recordingActivity.previewFailure
    }
    func endLiveActivityPreview() { recordingActivity.finish(); liveActivityPreviewStatus = "已结束" }
    #endif
    var recordingSourceLabel: String {
        AVAudioSession.sharedInstance().currentRoute.inputs.contains { [.bluetoothHFP, .headsetMic, .usbAudio].contains($0.portType) } ? "耳机麦克风" : "手机麦克风"
    }

    private var player: AVAudioPlayer?
    private var timer: Timer?
    private var startedAt: Date?
    private var accumulated: TimeInterval = 0
    private var auxiliaryRecorder: AVAudioRecorder?
    private var auxiliaryURL: URL?
    private var auxiliaryTimer: Timer?
    private var auxiliaryStartedAt: Date?
    private let recordingStore: LocalRecordingStore
    private var naturalCallStartID = UUID()
    private var pendingNaturalCallStartID: UUID?
    func cancelNaturalCallStart() {
        naturalCallStartID = UUID()
        guard pendingNaturalCallStartID != nil else { return }
        pendingNaturalCallStartID = nil
        isBusy = false
    }
    private let apiClientFactory: ((Pairing) -> APIClient?)?
    private var chatStore: TwinChatStore { TwinChatStore(root: recordingStore.root.appendingPathComponent("ChatIndex")) }
    private let localSpeech: any LocalSpeechTranscriber
    private let defaults: UserDefaults
    private let recordPermission: @MainActor () async -> Bool
    private let applicationIsActive: @MainActor () -> Bool
    private var twinContentRevision = UUID()

    var visibleLocalRecordings: [LocalRecording] { isGuestMode ? [] : localRecordings.filter { $0.isVisible(to: pairing) } }
    private var activeLocalRecording: LocalRecording? { localRecordings.first { $0.id == draft?.id } }

    var recordingActivitySummary: String {
        if episodes.contains(where: { $0.status == "reviewing" }) { return "有录音待核对文字" }
        if episodes.contains(where: { $0.status == "failed" }) { return "有录音未完成，可重试" }
        if episodes.contains(where: { ["uploaded", "transcribing", "extracting", "modeling"].contains($0.status) }) {
            return "正在转写或整理录音"
        }
        if isBusy && episodeID == nil { return "正在上传录音" }
        if episodes.isEmpty { return "还没有上传录音" }
        return "\(episodes.count) 段录音 · 已整理"
    }

    // A worker can finish while the recorder is closed or iOS suspends polling.
    // Reconcile every submitted local original, only within the current owner.
    func reconcileRecordingStatuses(_ loadedEpisodes: [EpisodeRecord], pairing: Pairing) {
        guard self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
        let statuses = Dictionary(loadedEpisodes.map { ($0.id, $0) }, uniquingKeysWith: { _, latest in latest })
        for var record in localRecordings where record.owner == RecordingOwner(pairing) {
            guard let id = record.episodeID, let remote = statuses[id] else { continue }
            let status = remote.waiting_for_review == true || record.status == "reviewing" && remote.status == "transcribing"
                ? "reviewing" : remote.status
            guard record.status != status || record.cumulativeAnalysis != remote.cumulative_analysis else { continue }
            record.status = status; record.cumulativeAnalysis = remote.cumulative_analysis
            _ = persistLocal(record)
        }
        if let episodeID, let status = statuses[episodeID], !isPollingEpisode {
            processingStatus = status.status
        }
    }

    init(recordingStore: LocalRecordingStore = LocalRecordingStore(),
         localSpeech: any LocalSpeechTranscriber = OnDeviceSpeechTranscriber(),
         defaults: UserDefaults = .standard, pairing: Pairing? = PairingStore.load(),
         personReview: PersonReviewModel = PersonReviewModel(),
         apiClientFactory: ((Pairing) -> APIClient?)? = nil,
         recordPermission: @escaping @MainActor () async -> Bool = {
             await withCheckedContinuation { continuation in
                 AVAudioApplication.requestRecordPermission { continuation.resume(returning: $0) }
             }
         },
         applicationIsActive: @escaping @MainActor () -> Bool = { UIApplication.shared.applicationState == .active }) {
        self.personReview = personReview
        self.recordingStore = recordingStore
        self.apiClientFactory = apiClientFactory
        self.localSpeech = localSpeech
        self.defaults = defaults
        self.recordPermission = recordPermission
        self.applicationIsActive = applicationIsActive
        let restoringGuest = defaults.bool(forKey: "guest-access-mode")
        self.isGuestMode = restoringGuest
        self.pairing = restoringGuest ? nil : pairing
        let pairing = self.pairing
        guestAccess.configure(entry: PairingStore.load(account: "guest-entry"))
        guestObservation = guestAccess.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }
        recordingActivity.clearOrphans()
        devices.onDownload = { [weak self] file, owner, purposes in
            guard let self else { return false }
            return await self.importDeviceRecording(file, owner: owner, authorization: purposes)
        }
        devices.onAuthorization = { [weak self] owner, purposes in
            guard let self, self.pairing.map(RecordingOwner.init) == owner else { return }
            for var record in self.visibleLocalRecordings where record.draft.captureSource == "WORK_3200" && record.episodeID == nil {
                record.draft.captureMetadata = (record.draft.captureMetadata ?? [:]).merging(purposes) { _, new in new }
                _ = self.persistLocal(record)
            }
            self.processDeviceRecordingQueue()
        }
        NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)
            .sink { [weak self] notification in
                let type = (notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? NSNumber)?.uintValue
                let options = (notification.userInfo?[AVAudioSessionInterruptionOptionKey] as? NSNumber)?.uintValue ?? 0
                Task { @MainActor in self?.handleRecordingInterruption(type: type, options: options) }
            }.store(in: &audioObservations)
        NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification)
            .sink { [weak self] notification in
                let reason = (notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? NSNumber)?.uintValue
                Task { @MainActor in
                    guard let self, reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue,
                          self.isRecording, !self.isPaused else { return }
                    self.pauseOrResume()
                    self.errorMessage = "音频设备已断开，录音已暂停。确认麦克风后可继续。"
                }
            }.store(in: &audioObservations)
        realtimeObservation = realtimeVoice.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }
        do {
            let loaded = try recordingStore.load()
            localRecordings = loaded.recordings
            if loaded.unreadableCount > 0 {
                errorMessage = "有 \(loaded.unreadableCount) 份录音信息无法读取，其余录音仍可查看。原音没有删除。"
            }
        }
        catch { errorMessage = "本机录音信息暂时无法读取，原音没有删除：\(error.localizedDescription)" }
        if !restoringGuest, let data = defaults.data(forKey: "pending-recording") {
            draft = try? JSONDecoder().decode(RecordingDraft.self, from: data)
            if let pending = draft { draft = recordingStore.resolved(pending) }
        }
        episodeID = restoringGuest ? nil : defaults.string(forKey: "pending-episode")
        if let draft, !localRecordings.contains(where: { $0.id == draft.id }) {
            // Import the previous single pending draft without discarding it.
            _ = persistLocal(LocalRecording(draft: draft, owner: pairing.map(RecordingOwner.init),
                                            episodeID: episodeID, status: episodeID == nil ? "saved" : "uploaded"))
        }
        if let record = activeLocalRecording, !record.isVisible(to: pairing) {
            draft = nil; episodeID = nil
            persistActiveDraft()
        }
        if let path = defaults.string(forKey: "pending-voice-sample"),
           pairing.map(RecordingOwner.init) == defaults.data(forKey: "pending-voice-owner").flatMap { try? JSONDecoder().decode(RecordingOwner.self, from: $0) },
           FileManager.default.fileExists(atPath: path) {
            voiceSampleURL = URL(fileURLWithPath: path)
            voiceSampleTranscript = defaults.string(forKey: "pending-voice-transcript") ?? ""
            voiceSampleReadingPrompt = defaults.string(forKey: "pending-voice-reading-prompt")
        }
        personReview.configure(pairing)
        personReview.onMutation = { [weak self] scope in
            guard let self, let current = self.pairing, ReviewScope(current) == scope else { return }
            if self.realtimeVoice.isActive { self.realtimeVoice.endCurrentCall(message: "记忆或人物理解已变化，请重新开始通话。") }
            let history = self.twinChat
            self.twinAnswer = nil; self.twinChat = history
            self.twinChat.invalidateAnswers(); self.calibrationRun = nil
            self.defaults.removeObject(forKey: self.answerStorageKey(current))
            self.twinContentRevision = UUID(); self.resetMemorySearch(); self.stopPlayback()
            self.persistChatIndex()
        }
    }

    private var client: APIClient? {
        guard !isGuestMode, let pairing else { return nil }
        if let apiClientFactory { return apiClientFactory(pairing) }
        return try? APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint,
                              token: pairing.token)
    }

    func importPairingLink(_ url: URL) {
        guard !isGuestMode, url.scheme == "rememberme", url.host == "pair",
              let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return }
        func value(_ name: String) -> String { parts.first(where: { $0.name == name })?.value ?? "" }
        showConnection = true
        pairingServer = value("server")
        pairingCode = value("code")
        pairingFingerprint = value("sha256")
    }

    func connect() async {
        guard !connectionChangeBlocked else {
            errorMessage = "还有待处理的录音，请先在当前服务完成该任务后再更换连接。原音仍在手机里。"
            return
        }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let server = pairingServer.trimmingCharacters(in: .whitespacesAndNewlines)
            let fingerprint = pairingFingerprint.trimmingCharacters(in: .whitespacesAndNewlines)
            let api = try APIClient(baseURL: server, fingerprint: fingerprint)
            let reply = try await api.claim(code: pairingCode.trimmingCharacters(in: .whitespacesAndNewlines))
            let connected = Pairing(baseURL: server, fingerprint: fingerprint,
                                    token: reply.actor_token, actorID: reply.actor_id,
                                    subjectID: reply.subject_id, consentID: reply.recording_consent_id)
            guard applyConnection(connected) else { return }
            pendingCloudLogin = nil; cloudSpaces = []
            showConnection = false
            await refresh()
        } catch { errorMessage = error.localizedDescription }
    }

    func refresh() async {
        guard !isGuestMode, !isRestoringChat, let pairing, let client else { return }
        var contentRevision = twinContentRevision
        let owner = RecordingOwner(pairing)
        do {
            if pairing.isCloud {
                let spaces = try await client.spaces()
                guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner else { return }
                guard spaces.actor_id == pairing.actorID,
                      spaces.items.contains(where: { $0.id == pairing.subjectID && $0.role == "owner" }) else {
                    clearRemoteData()
                    throw APIError.server(403, "当前账号已不能访问该本人空间，请重新登录或选择空间。")
                }
                cloudSpaces = spaces.items
                let caps = try await client.capabilities()
                guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner else { return }
                cloudCapabilities = caps
            }
            let grants = try await client.consents(subjectID: pairing.subjectID)
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner else { return }
            guard contentRevision == twinContentRevision else { return }
            let nextCloudConsent = grants.last(where: { $0.scope == "CLOUD_TWIN" && $0.status == "granted" })?.id
            let nextVoiceConsent = grants.last(where: { $0.scope == "VOICE" && $0.status == "granted" })?.id
            let hasRecording = grants.contains { $0.scope == "RECORDING" && $0.status == "granted" }
            let lostCloudAccess = nextCloudConsent == nil && (cloudConsentID != nil || twinAnswer != nil || !twinChat.turns.isEmpty)
            let lostVoiceAccess = nextVoiceConsent == nil && (voiceConsentID != nil || realtimeVoice.isActive || voiceProfileReady)
            let lostRecordingAccess = !hasRecording && (!memories.isEmpty || !episodes.isEmpty || modelVersion != 0)
            if lostCloudAccess || lostVoiceAccess || lostRecordingAccess {
                // Apply confirmed revocations before any later metadata read
                // can fail. Cached state is retained only for transport errors.
                clearRemoteData()
                contentRevision = twinContentRevision
            }
            cloudConsentID = nextCloudConsent
            voiceConsentID = nextVoiceConsent
            if !hasRecording { clearAutomaticTranscriptionApproval(pairing) }
            async let nextMemories: [MemoryRecord] = hasRecording ? client.memories(pairing.subjectID) : []
            async let nextEpisodes: [EpisodeRecord] = hasRecording ? client.episodes(pairing.subjectID) : []
            async let nextModel = hasRecording ? client.model(pairing.subjectID) : PersonModelReply(version: 0, domains: [])
            async let nextQuestions: [QuestionRecord] = hasRecording ? client.questions(pairing.subjectID) : []
            let loadedMemories = try await nextMemories
            let loadedEpisodes = try await nextEpisodes
            let snapshot = try await nextModel
            let loadedQuestions = try await nextQuestions
            // Voice service is optional and must not hide otherwise usable memories.
            let profile = pairing.isCloud || !hasRecording ? nil : try? await client.voiceProfile(subjectID: pairing.subjectID)
            let runs = hasRecording ? try? await client.calibrations(subjectID: pairing.subjectID) : nil
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner else { return }
            guard contentRevision == twinContentRevision else { return }
            if modelVersion != snapshot.version || Set(episodes.filter { $0.status == "ready" }.map(\.id)) != Set(loadedEpisodes.filter { $0.status == "ready" }.map(\.id)) {
                twinChat.invalidateAnswers()
            }
            memories = loadedMemories; episodes = loadedEpisodes
            reconcileRecordingStatuses(loadedEpisodes, pairing: pairing)
            domains = snapshot.domains; graphFacts = snapshot.graph_facts; modelVersion = snapshot.version; questions = loadedQuestions
            voiceProfileReady = profile?.ready ?? false
            if contentRevision == twinContentRevision { calibrationRun = runs?.first }
            if cloudConsentID != nil, contentRevision == twinContentRevision {
                try await restoreChat(pairing, client: client, revision: contentRevision)
                guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            }
            if !isAskingTwin, cloudConsentID != nil,
               let answerID = defaults.string(forKey: answerStorageKey(pairing)) {
                let answer = try? await client.twinAnswer(subjectID: pairing.subjectID, answerID: answerID)
                guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner else { return }
                if contentRevision == twinContentRevision {
                    if let answer { receiveTwinAnswer(answer) }
                    else if twinChat.turns.isEmpty { twinAnswer = nil }
                }
            } else if cloudConsentID == nil { twinAnswer = nil; calibrationRun = nil }
            errorMessage = nil
        } catch {
            // Leaving a page or changing scene phase cancels SwiftUI loading tasks.
            // This is not a service failure and must not clear content or show an alert.
            guard !Task.isCancelled, !(error is CancellationError),
                  (error as? URLError)?.code != .cancelled else { return }
            if self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner {
                if case let APIError.server(code, _) = error, [401, 403].contains(code) {
                    clearRemoteData()
                    errorMessage = error.localizedDescription
                } else {
                    guard contentRevision == twinContentRevision else { return }
                    // A failed refresh does not revoke the current identity or
                    // consent. In particular it must not tear down a live call.
                    errorMessage = "刷新未完成，当前内容已保留，可重试。\n\(error.localizedDescription)"
                }
            }
        }
    }

    private func answerStorageKey(_ pairing: Pairing) -> String {
        "last-twin-answer-\(pairing.baseURL)-\(pairing.actorID)-\(pairing.subjectID)"
    }
    private func persistChatIndex() {
        guard !isGuestMode, let pairing, cloudConsentID != nil, !isRestoringChat else { return }
        do { try chatStore.save(twinChat, pairing: pairing); chatNotice = nil }
        catch { chatNotice = "聊天暂未保存在手机，当前消息仍可查看。请检查存储空间。" }
    }
    private func discardChatIndex(_ pairing: Pairing) {
        do { try chatStore.remove(pairing) }
        catch { chatNotice = "本机聊天索引暂时无法清理。旧回答仍需服务器授权才能恢复。" }
    }
    private func restoreChat(_ pairing: Pairing, client: APIClient, revision: UUID) async throws {
        let scope = ReviewScope(pairing)
        guard restoredChatScope != scope, !isAskingTwin else { return }
        let items: [TwinChatStoredTurn]
        do { items = try chatStore.load(pairing) }
        catch {
            restoredChatScope = scope
            chatNotice = "本机聊天索引暂时无法读取，记忆和原始录音仍可查看。"
            return
        }
        restoredChatScope = scope
        guard !items.isEmpty else { return }
        let requestID = UUID(); chatRestoreRequestID = requestID; isRestoringChat = true
        twinAnswer = nil
        chatHistoryMemory = nil; twinChat = TwinChatHistory(stored: items)
        defer {
            if chatRestoreRequestID == requestID { isRestoringChat = false; chatRestoreRequestID = nil }
        }
        for item in items {
            guard let id = item.answerID else { continue }
            do {
                let answer = try await client.twinAnswer(subjectID: pairing.subjectID, answerID: id)
                guard self.pairing.map(ReviewScope.init) == scope, twinContentRevision == revision,
                      chatRestoreRequestID == requestID else { return }
                twinChat.receive(answer, for: item.id)
            } catch {
                guard self.pairing.map(ReviewScope.init) == scope, twinContentRevision == revision,
                      chatRestoreRequestID == requestID else { return }
                if case let APIError.server(code, _) = error, [401, 403].contains(code) { throw error }
                twinChat.unavailable(item.id, message: "历史回答暂时无法读取，可以重新加载。")
                if error is URLError || Task.isCancelled {
                    for pending in twinChat.turns where pending.answer == nil && pending.failure == nil {
                        twinChat.unavailable(pending.id, message: "连接中断，可以重新加载这条回答。")
                    }
                    break
                }
            }
        }
        if let answer = twinChat.turns.reversed().compactMap(\.answer).first { twinAnswer = answer }
    }
    func newTwinChat() {
        guard !isBusy, !isRestoringChat, !isQueryRecording else { return }
        if let pairing {
            discardChatIndex(pairing)
            defaults.removeObject(forKey: answerStorageKey(pairing))
        }
        twinContentRevision = UUID(); twinAnswer = nil; queryDraft = ""
    }

    func refreshChatAnswer(_ answerID: String) async {
        guard !isBusy, !isRestoringChat, !personReview.isMutating, let pairing, let client,
              cloudConsentID != nil,
              let turn = twinChat.turns.first(where: { $0.answer?.id == answerID || $0.savedAnswerID == answerID }) else { return }
        let revision = twinContentRevision
        isBusy = true; defer { isBusy = false }
        do {
            let answer = try await client.twinAnswer(subjectID: pairing.subjectID, answerID: answerID)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), twinContentRevision == revision else { return }
            twinChat.receive(answer, for: turn.id)
            if twinAnswer?.id == answer.id { twinAnswer = answer }
            persistChatIndex()
        } catch {
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), twinContentRevision == revision else { return }
            if case let APIError.server(code, _) = error, [401, 403].contains(code) {
                clearRemoteData(); errorMessage = "当前账号无法读取这条回答，请重新连接本人空间。"
            } else {
                twinChat.unavailable(turn.id, message: "这条回答暂时无法读取，可以重新加载。")
            }
        }
    }
    private func clearRemoteData() {
        deferDeviceUploads()
        savingCaptureID = nil; lastSavedCaptureID = nil; currentTranscriptReview = nil; transcriptSupplement = ""
        realtimeVoiceReview = nil
        realtimeVoice.endCurrentCall(message: "账号或授权已变化，通话已结束。", resetConnectionAfter: true)
        twinContentRevision = UUID()
        restoredChatScope = nil; chatRestoreRequestID = nil; isRestoringChat = false
        chatNotice = nil
        memories = []; episodes = []; domains = []; graphFacts = []; questions = []; modelVersion = 0
        twinAnswer = nil
        twinArchiveRequest = UUID(); isLoadingTwinArchive = false
        twinArchive = []; twinArchiveCursor = nil; twinArchiveOwner = nil; twinArchiveError = nil
        chatHistoryMemory = nil; calibrationRun = nil; cloudConsentID = nil
        voiceConsentID = nil; voiceProfileReady = false
        memorySearchResults = []; memorySearchQuery = ""; queryDraft = ""
        personReview.configure(pairing)
        stopPlayback()
    }
    @discardableResult
    func applyConnection(_ connected: Pairing?, persist: Bool = true) -> Bool {
        guard !isGuestMode, !realtimeVoice.isActive, !isSpeakerRecording, !personReview.isMutating, !isRecording, !isPollingEpisode, !isLocalTranscribing, !isQueryRecording, !isVoiceRecording else { return false }
        // Archive the active draft in its original scope before changing identity.
        guard prepareConnectionDraft() else { return false }
        do {
            if persist {
                if let old = pairing, !old.isCloud { try PairingStore.save(old, account: "last-mac-pairing") }
                if let connected { try PairingStore.save(connected) } else { PairingStore.clear() }
            }
            clearRemoteData()
            voiceSampleURL = nil; voiceSampleTranscript = ""; voiceSampleReadingPrompt = nil
            cloudCapabilities = nil
            pairing = connected
            personReview.configure(connected)
            return true
        } catch { errorMessage = "连接未保存，原录音仍在：\(error.localizedDescription)"; return false }
    }
    private func prepareConnectionDraft() -> Bool {
        if let draft {
            var record = activeLocalRecording ?? LocalRecording(draft: draft, owner: pairing.map(RecordingOwner.init))
            record.draft = draft; record.episodeID = episodeID
            guard persistLocal(record) else { return false }
        }
        draft = nil; episodeID = nil; transcriptDraft = ""; isTranscriptReviewReady = false
        transcriptSupplement = ""; currentTranscriptReview = nil
        processingStatus = ""; recordedSeconds = 0
        persistActiveDraft()
        return true
    }
    func checkECSConnection() async {
        guard !isGuestMode, !isBusy else { return }
        isBusy = true; defer { isBusy = false }
        connectionStatus = "正在检查连接…"
        do {
            let api = try APIClient(baseURL: ECSConfiguration.baseURL, fingerprint: ECSConfiguration.fingerprint)
            let info = try await api.serviceInfo()
            guard Self.supportsBackendVersion(info.api_version) else { throw APIError.server(409, "服务版本不匹配，请更新 App。") }
            connectionStatus = "云端服务可连接 · API \(info.api_version)"
        } catch { connectionStatus = "连接未完成：\(error.localizedDescription)" }
    }
    func loginECS(username: String, password: String) async {
        guard !connectionChangeBlocked else { return }
        isBusy = true; errorMessage = nil
        defer { isBusy = false }
        do {
            let api = try APIClient(baseURL: ECSConfiguration.baseURL, fingerprint: ECSConfiguration.fingerprint)
            let info = try await api.serviceInfo()
            guard Self.supportsBackendVersion(info.api_version) else { throw APIError.server(409, "服务版本不匹配，请更新 App。") }
            let login = try await api.login(username: username.trimmingCharacters(in: .whitespacesAndNewlines), password: password)
            let authenticated = try APIClient(baseURL: ECSConfiguration.baseURL, fingerprint: ECSConfiguration.fingerprint, token: login.actor_token)
            let spaces = try await authenticated.spaces()
            guard spaces.actor_id == login.actor_id else { throw APIError.invalidResponse }
            pendingCloudLogin = login; cloudSpaces = spaces.items
            connectionStatus = "已验证账号，请选择本人空间"
            let owned = spaces.items.filter { $0.role == "owner" }
            if owned.count == 1 { try await finishCloudSelection(owned[0], login: login) }
            else if owned.isEmpty { errorMessage = "这个账号没有本人空间。亲友空间的 iOS 接入稍后提供。" }
        } catch { errorMessage = "登录未完成：\(error.localizedDescription)" }
    }
    func selectCloudSpace(_ id: String) async {
        guard !connectionChangeBlocked, let space = cloudSpaces.first(where: { $0.id == id && $0.role == "owner" }) else { return }
        let login = pendingCloudLogin ?? pairing.flatMap { $0.isCloud ? CloudLoginReply(actor_token: $0.token, actor_id: $0.actorID, display_name: $0.displayName ?? "") : nil }
        guard let login else { return }
        isBusy = true; defer { isBusy = false }
        do { try await finishCloudSelection(space, login: login) }
        catch { errorMessage = "空间未能连接：\(error.localizedDescription)" }
    }
    private func finishCloudSelection(_ space: CloudSpace, login: CloudLoginReply) async throws {
        let api = try APIClient(baseURL: ECSConfiguration.baseURL, fingerprint: ECSConfiguration.fingerprint, token: login.actor_token)
        let current = try await api.spaces()
        guard current.actor_id == login.actor_id,
              current.items.contains(where: { $0.id == space.id && $0.role == "owner" }) else { throw APIError.invalidResponse }
        let grants = try await api.consents(subjectID: space.id)
        let consent = grants.last(where: { $0.scope == "RECORDING" && $0.status == "granted" })?.id ?? ""
        let connected = Pairing(baseURL: ECSConfiguration.baseURL, fingerprint: ECSConfiguration.fingerprint,
            token: login.actor_token, actorID: login.actor_id, subjectID: space.id, consentID: consent,
            connectionKind: "cloudbase", displayName: login.display_name, spaceName: space.display_name)
        guard applyConnection(connected) else { return }
        pendingCloudLogin = nil; connectionStatus = "已连接云端本人空间"
        showConnection = false
        await refresh()
    }
    func disconnectCloud() async {
        guard !connectionChangeBlocked, pairing?.isCloud == true else { return }
        let oldClient = client
        guard applyConnection(nil) else { return }
        cloudSpaces = []; pendingCloudLogin = nil; connectionStatus = "已退出云端账号"
        do { try await oldClient?.logout() }
        catch { errorMessage = "本机已退出；服务端会话撤销未完成，将按到期时间失效。" }
    }
    func restoreMacConnection() async {
        guard !connectionChangeBlocked, let old = PairingStore.load(account: "last-mac-pairing"), applyConnection(old) else { return }
        pendingCloudLogin = nil; cloudSpaces = []; showConnection = false
        await refresh()
    }
    static func supportsBackendVersion(_ version: String) -> Bool {
        let parts = version.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3, let major = Int(parts[0]), let minor = Int(parts[1]),
              let patch = Int(parts[2]), patch >= 0 else { return false }
        return major == 0 && minor >= 7
    }

    func enterGuestMode() async {
        guard !connectionChangeBlocked, let owner = pairing, let client else {
            errorMessage = "请先结束录音、通话或正在处理的任务，并连接本人的账号空间。"; return
        }
        isBusy = true
        defer { isBusy = false }
        do {
            let entry = try await guestAccess.createDevice(owner: owner, client: client)
            guard pairing?.token == owner.token, pairing.map(RecordingOwner.init) == RecordingOwner(owner),
                  prepareConnectionDraft() else { return }
            try PairingStore.save(owner, account: "guest-owner-recovery")
            try PairingStore.save(entry, account: "guest-entry")
            // Persist the restriction first: interruption must never restore owner access.
            defaults.set(true, forKey: "guest-access-mode")
            clearRemoteData(); twinChat = TwinChatHistory()
            pendingCloudLogin = nil; cloudSpaces = []; cloudCapabilities = nil
            voiceSampleURL = nil; voiceSampleTranscript = ""; voiceSampleReadingPrompt = nil
            pairing = nil; personReview.configure(nil); PairingStore.clear()
            isGuestMode = true; showConnection = false; showActiveRecording = false; errorMessage = nil
            devices.reconcile(owner: nil)
            guestAccess.configure(entry: entry)
            await guestAccess.begin()
        } catch { errorMessage = "无法进入亲友模式：\(error.localizedDescription)" }
    }

    func returnToOwner(password: String, username: String? = nil) async {
        guard isGuestMode, !isBusy, !guestAccess.isBusy, !guestAccess.isRecording,
              let owner = PairingStore.load(account: "guest-owner-recovery") else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let api = try apiClientFactory?(owner) ?? APIClient(baseURL: owner.baseURL, fingerprint: owner.fingerprint, token: owner.token)
            let login: CloudLoginReply
            if let username, !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                let unauthenticated = try apiClientFactory?(owner) ?? APIClient(baseURL: owner.baseURL, fingerprint: owner.fingerprint)
                login = try await unauthenticated.login(username: username.trimmingCharacters(in: .whitespacesAndNewlines), password: password)
            } else {
                let data = try JSONSerialization.data(withJSONObject: ["password": password])
                login = try JSONDecoder().decode(CloudLoginReply.self, from: await api.request(
                    "/api/v1/accounts/reauth", method: "POST", body: data, contentType: "application/json", timeout: 30))
            }
            guard login.actor_id == owner.actorID else { throw APIError.invalidResponse }
            var verificationPairing = owner
            verificationPairing = Pairing(baseURL: owner.baseURL, fingerprint: owner.fingerprint, token: login.actor_token,
                actorID: login.actor_id, subjectID: owner.subjectID, consentID: owner.consentID)
            let verified = try apiClientFactory?(verificationPairing) ?? APIClient(baseURL: owner.baseURL, fingerprint: owner.fingerprint, token: login.actor_token)
            let spaces = try await verified.spaces()
            guard spaces.actor_id == owner.actorID,
                  spaces.items.contains(where: { $0.id == owner.subjectID && $0.role == "owner" }) else { throw APIError.invalidResponse }
            let restored = Pairing(baseURL: owner.baseURL, fingerprint: owner.fingerprint,
                token: login.actor_token, actorID: owner.actorID, subjectID: owner.subjectID,
                consentID: owner.consentID, connectionKind: owner.connectionKind,
                displayName: login.display_name, spaceName: owner.spaceName)
            try PairingStore.save(restored)
            await guestAccess.end()
            isGuestMode = false; pairing = restored; personReview.configure(restored)
            defaults.set(false, forKey: "guest-access-mode")
            PairingStore.clear(account: "guest-owner-recovery")
            errorMessage = nil
            await refresh()
        } catch { errorMessage = "密码验证未完成，仍处于亲友模式：\(error.localizedDescription)" }
    }

    private func automaticTranscriptionKey(_ pairing: Pairing) -> String {
        let data = try! JSONEncoder().encode([pairing.baseURL, pairing.fingerprint, pairing.actorID, pairing.subjectID])
        return "automatic-asr-policy-" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    func clearAutomaticTranscriptionApproval(_ pairing: Pairing) {
        let prefix = automaticTranscriptionKey(pairing)
        defaults.removeObject(forKey: prefix)
        for key in defaults.dictionaryRepresentation().keys where key.hasPrefix(prefix + "-start-") { defaults.removeObject(forKey: key) }
    }
    func hasAutomaticTranscriptionApproval(_ policy: String, pairing: Pairing) -> Bool {
        defaults.string(forKey: automaticTranscriptionKey(pairing)) == policy
    }
    func approveAutomaticTranscription(_ policy: String, recordingID: String, scope: ReviewScope) async {
        guard let pairing, ReviewScope(pairing) == scope, draft?.id == recordingID,
              !isRecording, !isBusy, !isPollingEpisode, !isPreparingAutomaticTranscription else { return }
        defaults.set(policy, forKey: automaticTranscriptionKey(pairing))
        await sendRecording(cloudASRPolicy: policy)
    }
    /// Returns a policy only when the displayed purpose needs a fresh approval.
    /// This path is invoked after an explicit finish, never on app launch.
    func transcribeFinishedRecordingAutomatically(force: Bool = false) async -> String? {
        guard !isGuestMode else { return nil }
        guard automaticTranscriptionEnabled || force, !isRecording, !isStartingRecording, !isBusy,
              !isPollingEpisode, !isPreparingAutomaticTranscription, !isLocalTranscribing,
              let id = draft?.id else { return nil }
        isPreparingAutomaticTranscription = true
        defer { isPreparingAutomaticTranscription = false }
        let scope = pairing.map(ReviewScope.init)
        processingStatus = "正在转成文字"
        if pairing == nil {
            await transcribeLocalRecording(id)
            guard pairing == nil, draft?.id == id else { return nil }
            if let record = activeLocalRecording, let text = record.machineTranscript {
                transcriptDraft = record.reviewDraft ?? record.reviewedTranscript ?? text
                isTranscriptReviewReady = true; processingStatus = "请核对转写文字"
            } else { processingStatus = "原音已保存，待转写" }
            return nil
        }
        guard let pairing, let client else { return nil }
        if !pairing.isCloud { await sendRecording(); return nil }
        let preparedPolicy = await prepareCloudASR()
        guard self.pairing.map(ReviewScope.init) == scope, draft?.id == id, !Task.isCancelled else { return nil }
        guard let policy = preparedPolicy else {
            processingStatus = "原音已保存，待转写"; return nil
        }
        let startReceipt = defaults.bool(forKey: automaticTranscriptionKey(pairing) + "-start-" + id)
        guard hasAutomaticTranscriptionApproval(policy, pairing: pairing) || startReceipt else {
            processingStatus = "请确认这段既有录音的转写用途"; return policy
        }
        if startReceipt { defaults.set(policy, forKey: automaticTranscriptionKey(pairing)) }
        isBusy = true
        let grants: [ConsentRecord]
        do { grants = try await client.consents(subjectID: pairing.subjectID) }
        catch {
            isBusy = false
            guard self.pairing.map(ReviewScope.init) == scope, draft?.id == id else { return nil }
            processingStatus = "原音已保存，待转写"
            errorMessage = "连接未完成，原音仍在手机，可重试。\n\(error.localizedDescription)"
            return nil
        }
        isBusy = false
        guard self.pairing.map(ReviewScope.init) == scope, draft?.id == id, !Task.isCancelled else { return nil }
        guard startReceipt || grants.contains(where: { $0.scope == "RECORDING" && $0.status == "granted" }) else {
            clearAutomaticTranscriptionApproval(pairing)
            processingStatus = "本段转写已停止，原音仍保留"; return policy
        }
        await sendRecording(cloudASRPolicy: policy, requiresExistingConsent: !startReceipt)
        return nil
    }

    func prepareCloudASR() async -> String? {
        guard !isBusy, let pairing, let client, pairing.isCloud else { return nil }
        isBusy = true; defer { isBusy = false }
        do {
            let caps = try await client.capabilities()
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return nil }
            guard caps.stt_configured else { throw APIError.server(503, "转写服务尚未就绪，原音仍保留在手机。") }
            guard caps.stt_processing != "client" else { throw APIError.server(409, "当前服务要求客户端机器稿，此版暂不支持该上传方式。原音仍保留。") }
            cloudCapabilities = caps
            if caps.stt_processing == "cloud" {
                guard let policy = caps.cloud_asr_policy, !policy.isEmpty else { throw APIError.invalidResponse }
                return policy
            }
            return ""
        } catch { errorMessage = "转写配置未能读取：\(error.localizedDescription)"; return nil }
    }

    func startRecording(questionID: String? = nil, calibrationID: String? = nil) async {
        guard !recordingStartBlocked else { return }
        guard draft == nil else {
            errorMessage = "已有录音保存在手机。请先保留这段，再开始新录音。"
            return
        }
        deferDeviceUploads()
        stopPlayback()
        errorMessage = nil
        transcriptDraft = ""
        isTranscriptReviewReady = false
        let owner = pairing.map(ReviewScope.init)
        isStartingRecording = true
        defer {
            isStartingRecording = false
            if !isRecording { processDeviceRecordingQueue() }
        }
        let granted = await recordPermission()
        guard pairing.map(ReviewScope.init) == owner, !Task.isCancelled else { return }
        guard granted else {
            errorMessage = "麦克风权限已拒绝。请在系统设置中允许 Remember Me 使用麦克风，然后再试。"
            return
        }
        guard UIApplication.shared.applicationState == .active else { return }
        do {
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP])
            try audio.setActive(true)
            var root = recordingStore.root
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            var values = URLResourceValues()
            values.isExcludedFromBackup = true
            try root.setResourceValues(values)
            let id = UUID().uuidString
            let url = root.appendingPathComponent(id + ".m4a")
            let settings: [String: Any] = [AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                                           AVSampleRateKey: 44100,
                                           AVNumberOfChannelsKey: 1,
                                           AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.isMeteringEnabled = true
            guard recorder.prepareToRecord() else { throw APIError.invalidResponse }
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUnlessOpen], ofItemAtPath: url.path)
            guard recorder.record() else { throw APIError.invalidResponse }
            self.recorder = recorder
            recordingEvents.recorder = recorder
            recorder.delegate = recordingEvents
            recordingEvents.finished = { [weak self] succeeded in
                guard let self, self.draft?.id == id, self.isRecording else { return }
                self.finishRecording()
                if !succeeded { self.errorMessage = "录音被系统中断，已经保留当前原音。" }
            }
            recordingActivity.start(id: id, source: recordingSourceLabel)
            self.draft = RecordingDraft(id: id, fileURL: url, recordedAt: Date(),
                                        durationMS: 0, questionID: questionID,
                                        calibrationID: calibrationID,
                                        consentConfirmedAt: Date())
            if let draft {
                var record = LocalRecording(draft: draft, owner: pairing.map(RecordingOwner.init), status: "recording")
                record.automaticProcessing = pairing != nil && automaticTranscriptionEnabled && calibrationID == nil
                record.automaticASRPolicy = cloudCapabilities?.cloud_asr_policy
                _ = persistLocal(record)
                persistActiveDraft()
            }
            if let pairing, pairing.isCloud {
                defaults.set(true, forKey: automaticTranscriptionKey(pairing) + "-start-" + id)
                if let policy = cloudCapabilities?.cloud_asr_policy { defaults.set(policy, forKey: automaticTranscriptionKey(pairing)) }
            }
            self.isRecording = true
            self.isPaused = false
            self.recordedSeconds = 0
            self.meterLevels = Array(repeating: 0.16, count: 27)
            self.accumulated = 0
            self.startedAt = Date()
            self.lastRecordingCheckpoint = Date()
            timer?.invalidate()
            let recordingTimer = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, self.isRecording, self.draft?.id == id else { return }
                    self.recordedSeconds = max(0, Int(self.recorder?.currentTime ??
                        (self.accumulated + (self.startedAt.map { Date().timeIntervalSince($0) } ?? 0))))
                    self.recordingActivity.update(paused: self.isPaused, seconds: self.recordedSeconds, source: self.recordingSourceLabel)
                    if Date().timeIntervalSince(self.lastRecordingCheckpoint) >= 30,
                       var record = self.activeLocalRecording, let draft = self.draft {
                        record.draft = draft.withDuration(self.recordedSeconds * 1000); record.status = "recording"
                        _ = self.persistLocal(record); self.lastRecordingCheckpoint = Date()
                    }
                    if self.isPaused || UIApplication.shared.applicationState != .active { return }
                    if let recorder = self.recorder {
                        recorder.updateMeters()
                        let level = max(0, min(1, (recorder.averagePower(forChannel: 0) + 60) / 60))
                        self.meterLevels.removeFirst()
                        self.meterLevels.append(CGFloat(level))
                    }
                }
            }
            timer = recordingTimer
            RunLoop.main.add(recordingTimer, forMode: .common)
            observeCaptureReset(recordingID: id)
        } catch { errorMessage = "录音未能开始：\(error.localizedDescription)" }
    }

    func handleRecordingInterruption(type: UInt?, options: UInt) {
        guard isRecording else { return }
        if type == AVAudioSession.InterruptionType.began.rawValue {
            let resume = !isPaused
            if resume { pauseOrResume() }
            resumeAfterAudioInterruption = resume
        } else if type == AVAudioSession.InterruptionType.ended.rawValue {
            let resume = resumeAfterAudioInterruption && AVAudioSession.InterruptionOptions(rawValue: options).contains(.shouldResume)
            resumeAfterAudioInterruption = false
            if resume && isPaused { pauseOrResume() }
        }
    }

    func pauseOrResume() {
        resumeAfterAudioInterruption = false
        guard let recorder else { return }
        if isPaused {
            if recorder.record() { startedAt = Date(); isPaused = false }
        } else {
            accumulated += startedAt.map { Date().timeIntervalSince($0) } ?? 0
            startedAt = nil
            recorder.pause()
            isPaused = true
        }
        recordedSeconds = max(0, Int(recorder.currentTime))
        recordingActivity.update(paused: isPaused, seconds: recordedSeconds, source: recordingSourceLabel)
    }

    func finishRecording() {
        guard let recorder, let draft else { return }
        captureResetObservation = nil
        let measuredDuration = recorder.currentTime
        var duration = measuredDuration > 0 ? measuredDuration : max(0, Double(recordedSeconds))
        recorder.delegate = nil
        recordingEvents.recorder = nil
        recorder.stop()
        if let savedAudio = try? AVAudioFile(forReading: draft.fileURL), savedAudio.processingFormat.sampleRate > 0 {
            duration = Double(savedAudio.length) / savedAudio.processingFormat.sampleRate
        }
        recordingEvents.finished = nil
        resumeAfterAudioInterruption = false
        recordingActivity.finish()
        try? FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete],
                                               ofItemAtPath: draft.fileURL.path)
        self.recorder = nil
        timer?.invalidate()
        timer = nil
        isRecording = false
        isPaused = false
        startedAt = nil; accumulated = 0
        self.draft = draft.withDuration(Int(duration * 1000))
        if var record = activeLocalRecording, let finished = self.draft {
            record.draft = finished
            if record.status == "recording" { record.status = "saved" }
            _ = persistLocal(record)
        } else if let finished = self.draft {
            _ = persistLocal(LocalRecording(draft: finished, owner: pairing.map(RecordingOwner.init)))
        }
        persistActiveDraft()
    }

    func recoverInterruptedRecordings() {
        guard !isGuestMode, !isRecording, !isStartingRecording else { return }
        for var record in visibleLocalRecordings where record.status == "recording" || record.episodeID == nil && record.draft.durationMS == 0 {
            guard let audio = try? AVAudioFile(forReading: recordingStore.resolved(record.draft).fileURL), audio.fileFormat.sampleRate > 0 else { continue }
            record.draft = record.draft.withDuration(Int(Double(audio.length) / audio.fileFormat.sampleRate * 1000))
            record.status = "saved"
            if persistLocal(record), draft?.id == record.id { draft = recordingStore.resolved(record.draft); persistActiveDraft() }
        }
    }

    @discardableResult
    private func persistLocal(_ record: LocalRecording) -> Bool {
        do {
            try recordingStore.save(record)
            localRecordings.removeAll { $0.id == record.id }
            localRecordings.append(record)
            localRecordings.sort { $0.draft.recordedAt > $1.draft.recordedAt }
            return true
        } catch {
            errorMessage = "录音信息未能保存。原音没有删除，请留在此页重试：\(error.localizedDescription)"
            return false
        }
    }

    private func persistActiveDraft() {
        if let draft, let data = try? JSONEncoder().encode(draft) {
            defaults.set(data, forKey: "pending-recording")
        } else { defaults.removeObject(forKey: "pending-recording") }
        if let episodeID { defaults.set(episodeID, forKey: "pending-episode") }
        else { defaults.removeObject(forKey: "pending-episode") }
    }

    @discardableResult
    func prepareNewRecording() -> Bool {
        guard !recordingStartBlocked else { return false }
        if let draft {
            var record = activeLocalRecording ?? LocalRecording(draft: draft, owner: pairing.map(RecordingOwner.init))
            record.draft = draft
            record.episodeID = episodeID
            if !persistLocal(record) { return false }
        }
        stopPlayback()
        draft = nil; episodeID = nil; transcriptDraft = ""; isTranscriptReviewReady = false
        transcriptSupplement = ""; currentTranscriptReview = nil
        processingStatus = ""; recordedSeconds = 0; errorMessage = nil
        persistActiveDraft()
        return true
    }

    @discardableResult
    func selectLocalRecording(_ id: String) -> Bool {
        guard !isRecording, !isBusy, !isPollingEpisode, !isLocalTranscribing,
              let record = visibleLocalRecordings.first(where: { $0.id == id }) else { return false }
        if draft?.id != id && !prepareNewRecording() { return false }
        draft = recordingStore.resolved(record.draft)
        episodeID = record.episodeID
        recordedSeconds = record.draft.durationMS / 1000
        isTranscriptReviewReady = false
        transcriptDraft = ""; transcriptSupplement = record.supplementDraft ?? ""; currentTranscriptReview = nil
        processingStatus = record.status == "ready" ? "ready" : ""
        persistActiveDraft()
        return true
    }

    func resumeCalibrationTranscript(_ run: CalibrationRecord) -> Bool {
        guard !isBusy, !isRestoringChat, !isPollingEpisode, !isRecording, !isLocalTranscribing,
              !isQueryRecording, !isVoiceRecording, pairing != nil, cloudConsentID != nil,
              calibrationRun?.id == run.id, run.status == "awaiting_human", let id = run.human_episode_id,
              let episode = episodes.first(where: { $0.id == id }), episode.status != "ready" else { return false }
        if let local = visibleLocalRecordings.first(where: { $0.episodeID == id }) {
            return selectLocalRecording(local.id)
        }
        guard prepareNewRecording() else { return false }
        episodeID = id; processingStatus = episode.status
        persistActiveDraft()
        return true
    }

    func deleteRecording(localID: String? = nil, remoteID: String? = nil, owner: RecordingOwner?) async -> Bool {
        guard !connectionChangeBlocked, pairing.map(RecordingOwner.init) == owner else { return false }
        let record = localID.flatMap { id in visibleLocalRecordings.first { $0.id == id } }
        guard localID == nil || record != nil else { return false }
        guard record?.id != deviceUploadingRecordingID || deviceUploadingRecordingID == nil else { return false }
        let remote = record?.episodeID ?? remoteID
        guard record != nil || remote.map({ id in episodes.contains { $0.id == id } }) == true else { return false }
        isBusy = true; errorMessage = nil
        let token = pairing?.token
        defer { isBusy = false }
        do {
            if let remote {
                guard let client else { throw APIError.invalidURL }
                try await client.deleteRecording(remote)
            }
            guard pairing.map(RecordingOwner.init) == owner, pairing?.token == token else { return false }
            twinContentRevision = UUID()
            if let record {
                if playbackID == record.id || playbackID == remote { stopPlayback() }
                try recordingStore.remove(record)
                localRecordings.removeAll { $0.id == record.id }
            }
            if let remote {
                if playbackID == remote { stopPlayback() }
                episodes.removeAll { $0.id == remote }; memories.removeAll { $0.episode_id == remote }
                twinAnswer = nil; twinChat.invalidateAnswers(); chatHistoryMemory = nil; calibrationRun = nil
                if let pairing { discardChatIndex(pairing) }
                domains = []; graphFacts = []; resetMemorySearch()
            }
            if draft?.id == record?.id && record != nil || episodeID == remote && remote != nil {
                draft = nil; episodeID = nil; transcriptDraft = ""; processingStatus = ""
                isTranscriptReviewReady = false; recordedSeconds = 0; persistActiveDraft()
            }
            await refresh()
            return true
        } catch {
            if pairing.map(RecordingOwner.init) == owner, pairing?.token == token {
                errorMessage = "删除暂未完成，请重试。\n\(error.localizedDescription)"
            }
            return false
        }
    }

    func invalidateRecordingSource(_ id: String) {
        twinContentRevision = UUID()
        if playbackID == id { stopPlayback() }
        memories.removeAll { $0.episode_id == id }; episodes.removeAll { $0.id == id }
        twinAnswer = nil; twinChat.invalidateAnswers(); chatHistoryMemory = nil; calibrationRun = nil
        if let pairing { discardChatIndex(pairing) }
        domains = []; graphFacts = []; resetMemorySearch()
    }

    private var isImportingDeviceRecording = false

    func importDeviceRecording(_ file: BeanDownloadedFile, owner: RecordingOwner,
                               authorization: [String: String]) async -> Bool {
        guard !isGuestMode, !isBusy, !isImportingDeviceRecording, pairing.map(RecordingOwner.init) == owner else { return false }
        isImportingDeviceRecording = true
        defer { isImportingDeviceRecording = false }
        let store = recordingStore
        do {
            let result = try await Task.detached(priority: .utility) {
                try DeviceRecordingImporter.importFile(file, owner: owner, store: store, authorization: authorization)
            }.value
            guard pairing.map(RecordingOwner.init) == owner else { return false }
            for record in result.records where !localRecordings.contains(where: { $0.id == record.id }) { localRecordings.append(record) }
            localRecordings.sort { $0.draft.recordedAt > $1.draft.recordedAt }
            deviceSyncNotice = result.records.isEmpty ? "这段录音已经同步过。" : "已保留 \(result.records.count) 段录音，正在按声音归属整理。"
            processDeviceRecordingQueue()
            return true
        } catch {
            if pairing.map(RecordingOwner.init) == owner { deviceSyncNotice = "录音暂未导入，设备原文件保留，可重试。" }
            return false
        }
    }

    var isUsingRealtimeAudio: Bool { hasRealtimeAudioWork }
    private var hasRealtimeAudioWork: Bool {
        realtimeVoice.isActive || pendingNaturalCallStartID != nil || isRecording || isStartingRecording ||
            isSpeakerRecording || isVoiceRecording || isQueryRecording
    }
    private func deferDeviceUploads() {
        guard deviceUploadTask != nil else { return }
        deviceUploadGeneration = UUID()
        deviceUploadTask?.cancel(); deviceUploadTask = nil
        isSyncingDeviceRecordings = false; deviceUploadingRecordingID = nil
        deviceSyncNotice = "设备录音已保留，实时录音或通话结束后继续整理。"
    }
    func prepareRealtimeCapture() -> Bool {
        guard !recordingStartBlocked else { return false }
        deferDeviceUploads(); stopPlayback()
        return true
    }
    private func observeCaptureReset(recordingID: String? = nil, auxiliaryID: UUID? = nil) {
        captureResetObservation = NotificationCenter.default.publisher(for: AVAudioSession.mediaServicesWereResetNotification)
            .sink { [weak self] _ in
                Task { @MainActor in
                    guard let self else { return }
                    if let recordingID, self.isRecording, self.draft?.id == recordingID {
                        self.finishRecording()
                        self.errorMessage = "系统音频服务已重启，当前原音已保留。请重新开始录音。"
                    } else if let auxiliaryID, self.auxiliaryStartGeneration == auxiliaryID,
                              self.isQueryRecording || self.isVoiceRecording {
                        self.stopAuxiliaryForBackground()
                    }
                }
            }
    }
    /// One serialized, durable queue for new phone recordings and device imports.
    /// It yields to every realtime audio path and never changes the open recorder.
    func processDeviceRecordingQueue() {
        guard !isGuestMode, applicationIsActive(), !hasRealtimeAudioWork, !isBusy,
              !isPollingEpisode, !isPreparingAutomaticTranscription,
              deviceUploadTask == nil, automaticTranscriptionEnabled, let pairing, let client else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        let queued = visibleLocalRecordings.filter {
            $0.owner == owner && $0.episodeID == nil && $0.draft.durationMS > 0 &&
            ($0.draft.captureSource == "WORK_3200" || $0.automaticProcessing == true) &&
            !(isRecorderPresented && draft?.id == $0.id) &&
            ($0.automaticAttempts ?? 0) < 3 && ($0.automaticRetryAt ?? .distantPast) <= Date()
        }
        guard !queued.isEmpty else { return }
        let generation = UUID(); deviceUploadGeneration = generation
        isSyncingDeviceRecordings = true
        deviceUploadTask = Task { [weak self] in
            guard let self else { return }
            @MainActor func current() -> Bool {
                !Task.isCancelled && self.pairing.map(RecordingOwner.init) == owner && self.pairing?.token == token &&
                self.deviceUploadGeneration == generation && !self.hasRealtimeAudioWork && self.automaticTranscriptionEnabled
            }
            defer {
                if self.deviceUploadGeneration == generation {
                    self.isSyncingDeviceRecordings = false; self.deviceUploadTask = nil; self.deviceUploadingRecordingID = nil
                }
            }
            do {
                var grants = try await client.consents(subjectID: pairing.subjectID)
                let caps = try await client.capabilities()
                guard current(), caps.stt_configured, caps.stt_processing != "client" else { return }
                self.cloudCapabilities = caps
                for record in queued {
                    guard current(), !self.isBusy, !self.isPollingEpisode else { return }
                    guard self.visibleLocalRecordings.contains(where: { $0.id == record.id && $0.episodeID == nil }) else { continue }
                    let isDevice = record.draft.captureSource == "WORK_3200"
                    let purposes = record.draft.captureMetadata ?? [:]
                    var recording = isDevice ? purposes["device_recording_consent_id"] : grants.last(where: { $0.scope == "RECORDING" && $0.status == "granted" })?.id
                    let speaker = isDevice ? purposes["device_speaker_consent_id"] : grants.last(where: { $0.scope == "SPEAKER_IDENTIFICATION" && $0.status == "granted" })?.id
                    // A first start can establish recording consent, but retry/relaunch
                    // never silently restores a grant that has been revoked.
                    if !isDevice, recording == nil, !grants.contains(where: { $0.scope == "RECORDING" }),
                       self.defaults.bool(forKey: self.automaticTranscriptionKey(pairing) + "-start-" + record.id) {
                        let grant = try await client.grantConsent(subjectID: pairing.subjectID, scope: "RECORDING", evidenceRef: "ios-start-recording")
                        guard current() else { return }
                        grants.append(grant); recording = grant.id
                    }
                    guard let recording, grants.contains(where: { $0.id == recording && $0.scope == "RECORDING" && $0.status == "granted" }),
                          !isDevice || speaker.map({ id in grants.contains { $0.id == id && $0.scope == "SPEAKER_IDENTIFICATION" && $0.status == "granted" } }) == true else {
                        self.deviceSyncNotice = "录音用途授权已失效，原音仍在手机。请重新确认后继续。"; return
                    }
                    let policy = isDevice ? purposes["cloud_asr_policy"] : record.automaticASRPolicy ?? caps.cloud_asr_policy
                    guard caps.stt_processing != "cloud" || policy != nil && policy == caps.cloud_asr_policy else {
                        self.deviceSyncNotice = "转写用途已变化，原音已保留，请重新确认。"; return
                    }
                    var pending = record
                    pending.automaticASRPolicy = policy
                    guard self.persistLocal(pending) else { return }
                    self.deviceUploadingRecordingID = record.id
                    let authenticated = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token,
                        actorID: pairing.actorID, subjectID: pairing.subjectID, consentID: recording,
                        connectionKind: pairing.connectionKind, displayName: pairing.displayName, spaceName: pairing.spaceName)
                    do {
                        let episode = try await client.upload(record.draft, pairing: authenticated, cloudASRPolicy: policy,
                            speakerConsent: speaker, transcriptCorrectionPolicy: isDevice ? nil : caps.transcript_correction_policy)
                        guard current() else { return }
                        guard var saved = self.localRecordings.first(where: { $0.id == record.id }) else { continue }
                        saved.episodeID = episode; saved.status = "uploaded"; saved.automaticError = nil
                        saved.automaticAttempts = 0; saved.automaticRetryAt = nil
                        guard self.persistLocal(saved) else { return }
                    } catch {
                        guard current() else { return }
                        if var saved = self.localRecordings.first(where: { $0.id == record.id }) {
                            saved.automaticAttempts = (saved.automaticAttempts ?? 0) + 1
                            saved.automaticRetryAt = Date().addingTimeInterval(Double(saved.automaticAttempts ?? 1) * 15)
                            saved.automaticError = "转写暂未完成，原音已保留，可重试。"
                            _ = self.persistLocal(saved)
                        }
                    }
                    self.deviceUploadingRecordingID = nil
                }
                guard current() else { return }
                self.deviceSyncNotice = "原音已保留；文字准备好后可直接修改并保存。"
                await self.refreshCaptureDrafts()
            } catch {
                if current() {
                    self.deviceSyncNotice = "连接暂未完成，原音与待办已保留，可重试。"
                    for old in queued {
                        guard var saved = self.visibleLocalRecordings.first(where: { $0.id == old.id && $0.episodeID == nil }) else { continue }
                        saved.automaticAttempts = (saved.automaticAttempts ?? 0) + 1
                        saved.automaticRetryAt = Date().addingTimeInterval(Double(saved.automaticAttempts ?? 1) * 15)
                        saved.automaticError = "连接暂未完成，原音与待办已保留。"
                        _ = self.persistLocal(saved)
                    }
                }
            }
        }
    }

    var latestCaptureDraft: LocalRecording? {
        visibleLocalRecordings.first { $0.status == "reviewing" && $0.reviewDraft != nil }
    }
    var latestSavedCapture: LocalRecording? {
        guard let lastSavedCaptureID else { return nil }
        return visibleLocalRecordings.first { $0.id == lastSavedCaptureID }
    }
    var pendingAutomaticCaptures: [LocalRecording] {
        visibleLocalRecordings.filter { $0.automaticProcessing == true && $0.status != "ready" && $0.status != "reviewing" }
    }

    func saveCaptureDraft(_ id: String, text: String, supplement: String) {
        guard !isGuestMode, var record = visibleLocalRecordings.first(where: { $0.id == id }),
              record.status == "reviewing", savingCaptureID != id else { return }
        record.reviewDraft = text; record.supplementDraft = String(supplement.prefix(3000))
        _ = persistLocal(record)
    }

    func retryAutomaticRecording(_ id: String) {
        guard !isGuestMode, var record = visibleLocalRecordings.first(where: { $0.id == id }),
              record.automaticProcessing == true, record.episodeID == nil else { return }
        record.automaticAttempts = 0; record.automaticRetryAt = nil; record.automaticError = nil
        if persistLocal(record) { processDeviceRecordingQueue() }
    }

    /// Lightweight foreground refresh; no full-model refresh on each timer tick.
    func refreshCaptureDrafts() async {
        guard !isGuestMode, applicationIsActive(), !hasRealtimeAudioWork, !isRefreshingCaptureDrafts,
              let pairing, let client else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        guard visibleLocalRecordings.contains(where: { $0.episodeID != nil && (!["ready", "failed"].contains($0.status) || $0.cumulativeAnalysis?.isPending == true) }) else { return }
        isRefreshingCaptureDrafts = true
        defer { isRefreshingCaptureDrafts = false }
        @MainActor func current() -> Bool { !Task.isCancelled && self.pairing.map(RecordingOwner.init) == owner && self.pairing?.token == token && !hasRealtimeAudioWork }
        do {
            let loaded = try await client.episodes(pairing.subjectID)
            guard current() else { return }
            let completed = loaded.contains { remote in remote.status == "ready" && visibleLocalRecordings.contains { $0.episodeID == remote.id && $0.status != "ready" } }
            episodes = loaded
            reconcileRecordingStatuses(loaded, pairing: pairing)
            // Bounded: prepare the newest three drafts, preserving edits made while awaiting the server.
            let reviewing = visibleLocalRecordings.filter {
                $0.status == "reviewing" && $0.reviewDraft == nil || ["uploaded", "transcribing"].contains($0.status)
            }.prefix(3)
            for record in reviewing {
                guard current(), let remote = record.episodeID else { return }
                let review = try await client.transcriptReview(remote)
                guard current(), review.state == "reviewing", let text = review.transcript,
                      var fresh = visibleLocalRecordings.first(where: { $0.id == record.id }),
                      ["uploaded", "transcribing", "reviewing"].contains(fresh.status) else { continue }
                fresh.status = "reviewing"
                fresh.machineTranscript = fresh.machineTranscript ?? review.machine_transcript ?? text
                fresh.cloudMachineTranscript = fresh.cloudMachineTranscript ?? review.machine_transcript
                if fresh.supplementDraft == nil { fresh.supplementDraft = review.supplement }
                fresh.automaticCorrection = review.automatic_correction
                if fresh.reviewDraft == nil { fresh.reviewDraft = text }
                _ = persistLocal(fresh)
            }
            if completed, current(), !isBusy { await refresh() }
        } catch { /* Background refresh retains the last usable draft and original. */ }
    }

    /// One save from the home draft. Analysis continues asynchronously; the
    /// microphone and next recording never wait for that optional model work.
    func submitCaptureDraft(_ id: String) async {
        guard !isGuestMode, !isBusy, savingCaptureID == nil, !hasRealtimeAudioWork,
              let pairing, let client, var record = visibleLocalRecordings.first(where: { $0.id == id }),
              record.status == "reviewing", let remote = record.episodeID else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        let text = (record.reviewDraft ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, text.count <= 100_000 else { errorMessage = "请先填写有效的转写文字。"; return }
        savingCaptureID = id
        defer { if savingCaptureID == id { savingCaptureID = nil } }
        @MainActor func current() -> Bool { !Task.isCancelled && self.pairing.map(RecordingOwner.init) == owner && self.pairing?.token == token }
        do {
            let caps = try await client.capabilities()
            guard current() else { return }
            let grants = try await client.consents(subjectID: pairing.subjectID)
            guard current() else { return }
            cloudCapabilities = caps
            let consent = (caps.automatic_capture_version ?? 0) >= 1 && caps.automatic_profile_analysis == true
                ? grants.last(where: { $0.scope == "CLOUD_TWIN" && $0.status == "granted" })?.id : nil
            try await client.confirmTranscript(remote, transcript: text, supplement: record.supplementDraft ?? "", cloudAnalysisConsentID: consent)
            guard current(), visibleLocalRecordings.contains(where: { $0.id == id && $0.status == "reviewing" }) else { return }
            record.reviewedTranscript = text; record.reviewedAt = Date(); record.status = "extracting"
            record.automaticError = nil
            guard persistLocal(record) else { return }
            lastSavedCaptureID = id
            if draft?.id == id { self.draft = nil; episodeID = nil; isTranscriptReviewReady = false; currentTranscriptReview = nil; persistActiveDraft() }
        } catch {
            if current() { errorMessage = "暂未保存成功，文字与原音已保留，可重试。" }
        }
    }

    func deleteGroupRecording(_ record: LocalSpeakerRecording, archive: SpeakerLocalArchive) async -> Bool {
        guard !connectionChangeBlocked, pairing.map(RecordingOwner.init) == record.owner else { return false }
        isBusy = true; errorMessage = nil
        let token = pairing?.token
        defer { isBusy = false }
        do {
            if let id = record.remoteID {
                guard let pairing, let client else { throw APIError.invalidURL }
                try await client.deleteSpeakerRecording(subject: pairing.subjectID, id: id)
            }
            guard pairing.map(RecordingOwner.init) == record.owner, pairing?.token == token else { return false }
            try archive.remove(record.id)
            return true
        } catch { errorMessage = "删除暂未完成，请重试。\n\(error.localizedDescription)"; return false }
    }

    func playLocalRecording(_ id: String) {
        guard !isGuestMode else { return }
        guard !hasRealtimeAudioWork,
              let record = visibleLocalRecordings.first(where: { $0.id == id }) else { return }
        if playbackID == id { toggleCurrentPlayback(); return }
        do { try beginPlayback(AVAudioPlayer(contentsOf: recordingStore.resolved(record.draft).fileURL), identity: id) }
        catch { errorMessage = "本机原音无法打开，记录仍保留：\(error.localizedDescription)" }
    }

    func transcribeLocalRecording(_ id: String) async {
        guard !isGuestMode else { return }
        guard !isRecording, !isBusy, !isPollingEpisode, !isLocalTranscribing,
              var record = visibleLocalRecordings.first(where: { $0.id == id }) else { return }
        isLocalTranscribing = true
        errorMessage = nil
        defer { isLocalTranscribing = false }
        do {
            let text = try await localSpeech.transcribe(recordingStore.resolved(record.draft).fileURL)
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw LocalSpeechError.empty }
            // Preserve the first machine output separately from later user edits.
            if record.machineTranscript == nil { record.machineTranscript = text }
            _ = persistLocal(record)
        } catch { errorMessage = error.localizedDescription }
    }

    @discardableResult
    func saveLocalReview(_ id: String, text: String) -> Bool {
        guard !isGuestMode else { return false }
        guard !isBusy, !isLocalTranscribing, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              var record = visibleLocalRecordings.first(where: { $0.id == id }),
              record.machineTranscript != nil, record.episodeID == nil else { return false }
        record.reviewedTranscript = text.trimmingCharacters(in: .whitespacesAndNewlines)
        record.reviewDraft = text
        record.reviewedAt = Date()
        return persistLocal(record)
    }

    func saveLocalReviewDraft(_ id: String, text: String) {
        guard !isGuestMode else { return }
        guard var record = visibleLocalRecordings.first(where: { $0.id == id }),
              record.machineTranscript != nil, record.episodeID == nil else { return }
        record.reviewDraft = text
        _ = persistLocal(record)
    }

    func stopPlayback() {
        playbackMeterGeneration = UUID()
        playbackPositionTick = 0
        playbackRequestID = nil
        playbackTimer?.invalidate()
        playbackTimer = nil
        player?.stop()
        player = nil
        isPlaying = false
        playbackLoading = false
        playbackID = nil
        playbackPosition = 0
        playbackDuration = 0
        playbackAudioLevel = nil
    }

    func pausePlayback() {
        player?.pause()
        playbackMeterGeneration = UUID()
        playbackTimer?.invalidate()
        playbackTimer = nil
        isPlaying = false
        playbackAudioLevel = nil
    }

    func toggleCurrentPlayback() {
        guard let player, !hasRealtimeAudioWork else { return }
        if player.isPlaying { pausePlayback() }
        else {
            if player.currentTime >= player.duration - 0.05 { player.currentTime = 0 }
            player.play()
            isPlaying = player.isPlaying
            if isPlaying { startPlaybackMetering() }
        }
    }

    func seekPlayback(_ position: TimeInterval) {
        guard let player else { return }
        player.currentTime = min(max(0, position), player.duration)
        playbackPosition = player.currentTime
    }

    private func beginPlayback(_ next: AVAudioPlayer, identity: String) throws {
        guard !hasRealtimeAudioWork else { return }
        stopPlayback()
        try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
        try AVAudioSession.sharedInstance().setActive(true)
        player = next
        playbackID = identity
        playbackDuration = next.duration
        next.isMeteringEnabled = true
        next.prepareToPlay()
        guard next.play() else { throw APIError.invalidResponse }
        isPlaying = true
        startPlaybackMetering()
    }

    private func startPlaybackMetering() {
        playbackTimer?.invalidate()
        playbackMeterGeneration = UUID()
        let meterGeneration = playbackMeterGeneration
        let meterTimer = Timer(timeInterval: 0.05, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.playbackMeterGeneration == meterGeneration, let current = self.player else { return }
                if current.isPlaying {
                    current.updateMeters()
                    let power = (0..<current.numberOfChannels).map { current.averagePower(forChannel: $0) }.max() ?? -160
                    self.playbackAudioLevel = Self.normalizedPlaybackPower(power)
                    self.playbackPositionTick = (self.playbackPositionTick + 1) % 4
                    if self.playbackPositionTick == 0 { self.playbackPosition = current.currentTime }
                } else {
                    self.playbackAudioLevel = nil
                    if self.isPlaying { self.playbackPosition = current.duration }
                    self.playbackTimer?.invalidate()
                    self.playbackTimer = nil
                }
                self.isPlaying = current.isPlaying
            }
        }
        playbackTimer = meterTimer
        RunLoop.main.add(meterTimer, forMode: .common)
    }

    /// A display envelope of the player's measured dBFS, with silence below -60 dB.
    static func normalizedPlaybackPower(_ decibels: Float) -> Double {
        guard decibels.isFinite else { return 0 }
        return min(1, max(0, (Double(decibels) + 60) / 60))
    }

    func togglePlayback() {
        guard !isGuestMode else { return }
        guard let draft else { return }
        if playbackID == draft.id { toggleCurrentPlayback(); return }
        do { try beginPlayback(AVAudioPlayer(contentsOf: draft.fileURL), identity: draft.id) }
        catch { errorMessage = "本地录音无法播放：\(error.localizedDescription)" }
    }

    func saveTranscriptDraft() {
        guard !isGuestMode else { return }
        if let episodeID {
            if let pairing { defaults.set(transcriptDraft, forKey: "transcript-edit-" + RecordingOwner(pairing).storageNamespace + "-" + episodeID) }
            if let id = activeLocalRecording?.id { saveCaptureDraft(id, text: transcriptDraft, supplement: transcriptSupplement) }
        }
        else if let id = draft?.id { saveLocalReviewDraft(id, text: transcriptDraft) }
    }

    func sendRecording(cloudASRPolicy: String? = nil, requiresExistingConsent: Bool = false) async {
        guard !isBusy, !isPollingEpisode, !isLocalTranscribing, let draft, let pairing, let client,
              var record = activeLocalRecording, record.isVisible(to: pairing) else { return }
        record.owner = RecordingOwner(pairing)
        let scope = ReviewScope(pairing)
        func stillCurrent() -> Bool { self.pairing.map(ReviewScope.init) == scope && self.draft?.id == draft.id }
        guard persistLocal(record) else { return }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            if let episodeID {
                let status = try await client.status(episodeID)
                guard stillCurrent() else { return }
                if status.status == "failed" {
                    try await client.retry(episodeID)
                }
                await pollEpisode()
                return
            }
            if pairing.isCloud {
                let caps = try await client.capabilities()
                guard stillCurrent() else { return }
                guard caps.stt_configured, caps.stt_processing != "client",
                      caps.stt_processing != "cloud" || caps.cloud_asr_policy == cloudASRPolicy && cloudASRPolicy != nil else {
                    throw APIError.server(409, "转写用途或配置已变化，请重新确认本段上传。原音仍保留。")
                }
                cloudCapabilities = caps
            }
            let grants = try await client.consents(subjectID: pairing.subjectID)
            guard stillCurrent() else { return }
            let recordingConsent: String
            if let existing = grants.last(where: { $0.scope == "RECORDING" && $0.status == "granted" }) {
                recordingConsent = existing.id
            } else {
                guard !requiresExistingConsent else {
                    clearAutomaticTranscriptionApproval(pairing)
                    throw APIError.server(409, "录音采集授权已撤销，请重新确认转写用途。原音仍保留。")
                }
                recordingConsent = try await client.grantConsent(subjectID: pairing.subjectID, scope: "RECORDING").id
                guard stillCurrent() else { return }
            }
            var uploadPairing = pairing
            uploadPairing = Pairing(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token,
                actorID: pairing.actorID, subjectID: pairing.subjectID, consentID: recordingConsent,
                connectionKind: pairing.connectionKind, displayName: pairing.displayName, spaceName: pairing.spaceName)
            processingStatus = "正在上传录音"
            var speakerConsent: String?
            if cloudCapabilities?.voiceprint_available == true {
                let grants = try await client.consents(subjectID: pairing.subjectID)
                guard stillCurrent() else { return }
                if let active = grants.last(where: { $0.scope == "SPEAKER_IDENTIFICATION" && $0.status == "granted" }) { speakerConsent = active.id }
                else { speakerConsent = try await client.grantConsent(subjectID: pairing.subjectID, scope: "SPEAKER_IDENTIFICATION", evidenceRef: "ios-start-recording").id }
                guard stillCurrent() else { return }
            }
            let id = try await client.upload(draft, pairing: uploadPairing, cloudASRPolicy: cloudASRPolicy, speakerConsent: speakerConsent,
                                             transcriptCorrectionPolicy: cloudCapabilities?.transcript_correction_policy)
            guard stillCurrent() else { return }
            episodeID = id
            record.episodeID = id; record.status = "uploaded"
            _ = persistLocal(record)
            persistActiveDraft()
            await pollEpisode()
        } catch {
            guard stillCurrent() else { return }
            processingStatus = episodeID == nil ? "原音已保存，待转写" : "处理未完成，可重试"
            errorMessage = "转写未完成，录音仍在手机里，可重试。\n\(error.localizedDescription)"
        }
    }

    func pollEpisode() async {
        guard !isPollingEpisode, let episodeID, let client, let pairing else { return }
        let draftID = draft?.id
        let owner = RecordingOwner(pairing)
        isPollingEpisode = true
        defer { isPollingEpisode = false }
        var consecutiveReadFailures = 0
        for _ in 0..<180 {
            guard !Task.isCancelled, self.episodeID == episodeID, draft?.id == draftID,
                  self.pairing.map(RecordingOwner.init) == owner else { return }
            do {
                let status = try await client.status(episodeID)
                guard self.episodeID == episodeID, draft?.id == draftID,
                      self.pairing.map(RecordingOwner.init) == owner else { return }
                processingStatus = status.status
                if var record = activeLocalRecording, record.status != status.status {
                    record.status = status.status
                    _ = persistLocal(record)
                }
                if status.status == "ready" {
                    let calibrationID = draft?.calibrationID
                    defaults.removeObject(forKey: "transcript-edit-\(episodeID)")
                    defaults.removeObject(forKey: "pending-recording")
                    defaults.removeObject(forKey: "pending-episode")
                    draft = nil
                    self.episodeID = nil
                    isTranscriptReviewReady = false
                    transcriptDraft = ""
                    await refresh()
                    if let calibrationID {
                        await completeCalibration(calibrationID)
                    }
                    return
                }
                if status.status == "failed" {
                    processingStatus = "failed"
                    errorMessage = "处理失败：\(status.error_message ?? status.error_code ?? "请稍后重试")。原录音仍保存在手机和本机服务里。"
                    return
                }
                let review = try await client.transcriptReview(episodeID)
                guard self.episodeID == episodeID, draft?.id == draftID,
                      self.pairing.map(RecordingOwner.init) == owner else { return }
                if review.state == "reviewing", let text = review.transcript {
                    currentTranscriptReview = review
                    if var record = activeLocalRecording {
                        record.machineTranscript = record.machineTranscript ?? review.machine_transcript ?? text
                        record.cloudMachineTranscript = record.cloudMachineTranscript ?? review.machine_transcript
                        if record.supplementDraft == nil { record.supplementDraft = review.supplement }
                        record.automaticCorrection = review.automatic_correction
                        if record.reviewDraft == nil { record.reviewDraft = text }
                        _ = persistLocal(record)
                        transcriptSupplement = record.supplementDraft ?? ""
                    }
                    if !isTranscriptReviewReady {
                        transcriptDraft = defaults.string(forKey: "transcript-edit-" + owner.storageNamespace + "-" + episodeID)
                            ?? activeLocalRecording?.reviewDraft ?? activeLocalRecording?.reviewedTranscript ?? text
                    }
                    isTranscriptReviewReady = true
                    processingStatus = "请核对转写文字"
                    return
                }
                consecutiveReadFailures = 0
            } catch {
                if Task.isCancelled || error is CancellationError || (error as? URLError)?.code == .cancelled { return }
                guard self.episodeID == episodeID, draft?.id == draftID,
                      self.pairing.map(RecordingOwner.init) == owner else { return }
                consecutiveReadFailures += 1
                let transient: Bool
                if let network = error as? URLError {
                    transient = [.timedOut, .networkConnectionLost, .notConnectedToInternet,
                                 .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed].contains(network.code)
                } else if case let APIError.server(code, _) = error {
                    transient = [502, 503, 504].contains(code)
                } else { transient = false }
                if transient && consecutiveReadFailures < 3 {
                    processingStatus = "连接暂时中断，正在重新查看处理结果"
                } else {
                    errorMessage = "连接中断，录音已保留。恢复网络后可继续查看。\n\(error.localizedDescription)"
                    return
                }
            }
            do { try await Task.sleep(for: .seconds(2)) } catch { return }
        }
        errorMessage = "处理时间较长。录音已保存，可稍后回来查看。"
    }

    func submitTranscript() async {
        if episodeID == nil, let id = draft?.id, isTranscriptReviewReady {
            if saveLocalReview(id, text: transcriptDraft) {
                isTranscriptReviewReady = false; processingStatus = "文字已保存在手机"
            }
            return
        }
        guard !isGuestMode, !isBusy, savingCaptureID == nil, let episodeID, let client, let pairing else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        let text = transcriptDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            errorMessage = "转写文字不能为空。请修改后再确认。"
            return
        }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let caps = try await client.capabilities()
            guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token, self.episodeID == episodeID else { return }
            let grants = try await client.consents(subjectID: pairing.subjectID)
            guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token, self.episodeID == episodeID else { return }
            cloudCapabilities = caps
            let analysisConsent = (caps.automatic_capture_version ?? 0) >= 1 && caps.automatic_profile_analysis == true
                ? grants.last(where: { $0.scope == "CLOUD_TWIN" && $0.status == "granted" })?.id : nil
            try await client.confirmTranscript(episodeID, transcript: text, supplement: transcriptSupplement, cloudAnalysisConsentID: analysisConsent)
            guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token, self.episodeID == episodeID else { return }
            if var record = activeLocalRecording {
                record.reviewedTranscript = text; record.reviewedAt = Date(); record.status = "extracting"
                record.supplementDraft = transcriptSupplement
                guard persistLocal(record) else { return }
                lastSavedCaptureID = record.id
                if record.draft.calibrationID == nil {
                    draft = nil; self.episodeID = nil; currentTranscriptReview = nil
                    isTranscriptReviewReady = false; processingStatus = "已保存，正在后台整理"
                    persistActiveDraft()
                    return
                }
            }
            isTranscriptReviewReady = false
            processingStatus = "正在提取记忆"
            await pollEpisode()
        } catch {
            guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token else { return }
            errorMessage = "文字还没有确认，原音与草稿仍保留，可重试。\n\(error.localizedDescription)"
        }
    }

    var memoryContentRevision: UUID { twinContentRevision }

    func saveGardenEntry(_ entry: GardenEntry, record: ReviewRecord?, title: String, text: String,
                         scope: ReviewScope) async -> Bool {
        guard !Task.isCancelled, !isGuestMode, !isBusy, !personReview.isMutating, let pairing,
              ReviewScope(pairing) == scope else { return false }
        isBusy = true; errorMessage = nil
        defer { isBusy = false }
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let openedEvent = entry.memories.first { entry.id == "event:" + $0.id && $0.memory_type == "EVENT" }
        if let record {
            guard entry.id == "record:" + record.id, record.kind == "story", record.editable,
                  ["pending", "confirmed"].contains(record.status) else {
                errorMessage = "这条故事暂时不能编辑，请刷新后重试。"; return false
            }
        } else if openedEvent == nil {
            errorMessage = "事件已变化，请刷新后再编辑。"; return false
        }

        await personReview.reload()
        guard !Task.isCancelled, !isGuestMode, self.pairing.map(ReviewScope.init) == scope,
              personReview.scope == scope else { return false }
        guard personReview.isReady else {
            errorMessage = personReview.errorMessage ?? "故事来源暂时无法读取，请稍后重试。"; return false
        }
        var input: ReviewRecordInput
        if let record {
            guard let current = personReview.records.first(where: {
                $0.id == record.id && $0.revision == record.revision && $0.kind == "story" &&
                $0.editable && ["pending", "confirmed"].contains($0.status)
            }) else {
                errorMessage = "故事已变化，请刷新后再编辑。"; return false
            }
            input = ReviewRecordInput(current)
            input.title = title; input.text = text
        } else {
            guard let openedEvent, let current = memories.first(where: { $0.id == openedEvent.id }),
                  current.memory_type == "EVENT", current.episode_id == openedEvent.episode_id,
                  current.content == openedEvent.content, current.source_type == openedEvent.source_type,
                  !current.evidence.isEmpty,
                  Set(current.evidence.map(\.id)) == Set(openedEvent.evidence.map(\.id)) else {
                errorMessage = "事件或原文依据已变化，请刷新后再编辑。"; return false
            }
            // Editing a presentation creates a story; it never rewrites the source event or Episode.
            input = ReviewRecordInput(kind: "story", title: title, text: text,
                                      evidenceIDs: current.evidence.map(\.id), facets: ["EXPERIENCE"])
        }
        let saved = await personReview.saveRecord(input, recordID: record?.id)
        guard !Task.isCancelled, self.pairing.map(ReviewScope.init) == scope, !isGuestMode else { return false }
        if !saved { errorMessage = personReview.errorMessage ?? "故事未能保存，请稍后重试。" }
        return saved
    }

    func deleteGardenEntry(_ entry: GardenEntry, record: ReviewRecord?, scope: ReviewScope) async -> Bool {
        guard !Task.isCancelled, !isGuestMode, !isBusy, !personReview.isMutating, let pairing,
              ReviewScope(pairing) == scope else { return false }
        isBusy = true; errorMessage = nil
        defer { isBusy = false }
        if let record {
            guard entry.id == "record:" + record.id, record.kind == "story", record.editable,
                  ["pending", "confirmed"].contains(record.status) else { return false }
            // Use the existing revision-checked owner mutation and cache invalidation.
            await personReview.reload()
            guard !Task.isCancelled, !isGuestMode, self.pairing.map(ReviewScope.init) == scope,
                  personReview.scope == scope else { return false }
            guard personReview.isReady, let current = personReview.records.first(where: {
                $0.id == record.id && $0.revision == record.revision && $0.kind == "story"
            }) else {
                errorMessage = personReview.errorMessage ?? "故事已变化，请刷新后再删除。"
                return false
            }
            let deleted = await personReview.decideRecord(current, confirm: false)
            if !deleted { errorMessage = personReview.errorMessage ?? "故事未能删除，请刷新后重试。" }
            return deleted && self.pairing.map(ReviewScope.init) == scope && !isGuestMode
        }
        guard let opened = entry.memories.first(where: { entry.id == "event:" + $0.id && $0.memory_type == "EVENT" }),
              let memory = memories.first(where: { $0.id == opened.id && $0.memory_type == "EVENT" }),
              memory.episode_id == opened.episode_id, memory.content == opened.content,
              memory.source_type == opened.source_type, !memory.evidence.isEmpty,
              Set(memory.evidence.map(\.id)) == Set(opened.evidence.map(\.id)) else {
            errorMessage = "事件已变化，请刷新后再删除。"; return false
        }
        personReview.onMutation?(scope)
        return await delete(memory)
    }

    func correct(_ memory: MemoryRecord, to content: String) async -> Bool {
        guard let pairing, let client else { return false }
        do {
            try await client.correct(subjectID: pairing.subjectID, memoryID: memory.id, content: content)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return false }
            twinAnswer = nil
        chatHistoryMemory = nil; calibrationRun = nil; twinContentRevision = UUID()
            discardChatIndex(pairing)
            resetMemorySearch(); await refresh(); return true
        }
        catch { errorMessage = error.localizedDescription; return false }
    }
    func delete(_ memory: MemoryRecord) async -> Bool {
        guard let pairing, let client else { return false }
        do {
            try await client.delete(subjectID: pairing.subjectID, memoryID: memory.id)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return false }
            memories.removeAll { $0.id == memory.id }
            twinAnswer = nil
        chatHistoryMemory = nil; calibrationRun = nil; twinContentRevision = UUID()
            discardChatIndex(pairing)
            resetMemorySearch()
            return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func playOriginal(_ memory: MemoryRecord) async {
        await playOriginal(episodeID: memory.episode_id)
    }

    func playOriginal(episodeID: String) async {
        guard let client, !hasRealtimeAudioWork else { return }
        if playbackID == episodeID { toggleCurrentPlayback(); return }
        stopPlayback()
        let request = UUID()
        playbackRequestID = request
        playbackLoading = true
        defer { if playbackRequestID == request { playbackLoading = false } }
        do {
            let data = try await client.audio(episodeID)
            guard playbackRequestID == request else { return }
            try beginPlayback(AVAudioPlayer(data: data), identity: episodeID)
        } catch {
            guard playbackRequestID == request, !hasRealtimeAudioWork, !Task.isCancelled,
                  !(error is CancellationError), (error as? URLError)?.code != .cancelled else { return }
            errorMessage = "原音暂时无法播放：\(error.localizedDescription)"
        }
    }

    func retryEpisode(_ episodeID: String) async {
        guard !isBusy, !isPollingEpisode, let pairing, let client,
              episodes.contains(where: { $0.id == episodeID }) || self.episodeID == episodeID else { return }
        isBusy = true; defer { isBusy = false }
        do {
            try await client.retry(episodeID)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return }
            await refresh()
            // Polling returns as soon as text needs human review. Waiting only
            // for ready here used to trap an otherwise successful STT job.
            if self.episodeID == episodeID { await pollEpisode() }
        } catch { errorMessage = error.localizedDescription }
    }

    func enableCloudTwin() async {
        guard let pairing, let client else { return }
        do {
            let consent = try await client.grantConsent(subjectID: pairing.subjectID, scope: "CLOUD_TWIN")
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            cloudConsentID = consent.id
        } catch {
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            errorMessage = "Twin 授权未完成：\(error.localizedDescription)"
        }
    }

    func revokeCloudTwin() async {
        guard let cloudConsentID, let pairing, let client else { return }
        do {
            try await client.revokeConsent(cloudConsentID)
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            twinContentRevision = UUID()
            self.cloudConsentID = nil
            twinAnswer = nil
        chatHistoryMemory = nil; calibrationRun = nil; queryDraft = ""
            discardChatIndex(pairing)
            defaults.removeObject(forKey: answerStorageKey(pairing))
        } catch {
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            errorMessage = "Twin 授权未能撤销：\(error.localizedDescription)"
        }
    }

    func searchMemories() async {
        guard let pairing, let client else { return }
        let query = memorySearchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { resetMemorySearch(); return }
        let requestID = UUID()
        let revision = twinContentRevision
        memorySearchRequestID = requestID; isSearchingMemories = true
        memorySearchResults = []; memorySearchCompleted = false; memorySearchError = nil
        defer { if memorySearchRequestID == requestID { isSearchingMemories = false } }
        do {
            let results = try await client.searchMemories(subjectID: pairing.subjectID, query: query)
            guard memorySearchRequestID == requestID, revision == twinContentRevision,
                  self.pairing?.token == pairing.token,
                  self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            memorySearchResults = results; memorySearchCompleted = true
        } catch {
            guard memorySearchRequestID == requestID, revision == twinContentRevision,
                  self.pairing?.token == pairing.token,
                  self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            memorySearchError = "暂时没有查到结果：\(error.localizedDescription)"
        }
    }

    func loadTwinArchive(nextPage: Bool = false) async {
        guard !isGuestMode, !isLoadingTwinArchive, let pairing, let client, let cloudConsentID else { return }
        let owner = RecordingOwner(pairing), request = UUID()
        let cursor = nextPage ? twinArchiveCursor : nil
        guard !nextPage || cursor != nil else { return }
        if twinArchiveOwner != owner { twinArchive = []; twinArchiveCursor = nil }
        twinArchiveOwner = owner; twinArchiveRequest = request; twinArchiveError = nil
        isLoadingTwinArchive = true
        defer { if twinArchiveRequest == request { isLoadingTwinArchive = false } }
        do {
            let history = try await client.twinAnswerHistory(subjectID: pairing.subjectID, cloudConsentID: cloudConsentID, cursor: cursor)
            guard !isGuestMode, twinArchiveRequest == request, self.pairing?.token == pairing.token,
                  self.pairing.map(RecordingOwner.init) == owner, self.cloudConsentID == cloudConsentID else { return }
            if nextPage {
                let existing = Set(twinArchive.map(\.id))
                twinArchive += history.items.filter { !existing.contains($0.id) }
            } else { twinArchive = history.items }
            twinArchiveCursor = history.next_cursor
        } catch {
            guard !Task.isCancelled, !(error is CancellationError), (error as? URLError)?.code != .cancelled,
                  !isGuestMode, twinArchiveRequest == request, self.pairing?.token == pairing.token,
                  self.pairing.map(RecordingOwner.init) == owner else { return }
            twinArchiveError = "对话暂未载入，请重试。\n\(error.localizedDescription)"
        }
    }
    func deleteArchivedTwinTurn(_ turn: HistoricalChatTurn, owner: RecordingOwner) async -> Bool {
        guard !connectionChangeBlocked, !isGuestMode, let pairing, RecordingOwner(pairing) == owner, let client else { return false }
        twinArchiveError = nil
        isBusy = true; defer { isBusy = false }
        do {
            let complete = try await client.deleteTwinAnswer(subjectID: pairing.subjectID, answerID: turn.id)
            guard !isGuestMode, self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner else { return false }
            twinArchiveRequest = UUID(); isLoadingTwinArchive = false
            twinContentRevision = UUID(); stopPlayback()
            twinChat.removeAnswer(turn.id)
            let remaining = twinChat
            if twinAnswer?.id == turn.id { twinAnswer = remaining.turns.last?.answer; twinChat = remaining }
            defaults.removeObject(forKey: answerStorageKey(pairing))
            persistChatIndex(); chatHistoryMemory = nil
            // Other replies can quote this turn. Revalidate them before showing
            // cached assistant text again; their independent questions remain.
            twinArchive = twinArchive.map { item in
                HistoricalChatTurn(answer_id: item.id, question: item.question, answer: nil,
                    assistant_stale: true, created_at: item.created_at, deletion_pending: item.deletion_pending)
            }
            if complete {
                twinArchive.removeAll { $0.id == turn.id }
            } else if let index = twinArchive.firstIndex(where: { $0.id == turn.id }) {
                twinArchive[index] = HistoricalChatTurn(answer_id: turn.id, question: "对话已删除，清理待重试", answer: nil,
                    assistant_stale: true, created_at: turn.created_at, deletion_pending: true)
                twinArchiveError = "对话内容已删除，声音清理暂未完成，左滑此条可重试。"
            }
            return complete
        } catch {
            guard !isGuestMode, self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == owner else { return false }
            twinArchiveError = "删除暂未完成，请左滑重试。\n\(error.localizedDescription)"
            return false
        }
    }
    func loadChatHistoryMemory(query: String = "", answerIDs: [String] = []) async {
        guard !isLoadingChatMemory, let pairing, let client, let cloudConsentID,
              cloudCapabilities?.chat_history_memory == true else { return }
        chatHistoryMemory = nil
        isLoadingChatMemory = true; defer { isLoadingChatMemory = false }
        do {
            let result = try await client.chatHistoryMemory(subjectID: pairing.subjectID, cloudConsentID: cloudConsentID, query: query, answerIDs: answerIDs)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), self.cloudConsentID == cloudConsentID else { return }
            chatHistoryMemory = result
        } catch {
            guard !Task.isCancelled, !(error is CancellationError),
                  (error as? URLError)?.code != .cancelled,
                  self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return }
            errorMessage = error.localizedDescription
        }
    }
    func setChatHistoryMemory(enabled: Bool) async {
        guard !isBusy, let pairing, let client else { return }
        isBusy = true
        do {
            try await client.setChatHistoryMemory(subjectID: pairing.subjectID, enabled: enabled)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { isBusy = false; return }
            twinContentRevision = UUID(); twinChat.invalidateAnswers()
            chatHistoryMemory = nil
            isBusy = false
            await loadChatHistoryMemory()
        } catch { isBusy = false; errorMessage = error.localizedDescription }
    }
    func clearChatHistoryMemory() async {
        guard !isBusy, let pairing, let client else { return }
        isBusy = true
        do {
            try await client.clearChatHistoryMemory(subjectID: pairing.subjectID)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { isBusy = false; return }
            twinContentRevision = UUID(); twinChat.invalidateAnswers()
            chatHistoryMemory = nil
            isBusy = false
            await loadChatHistoryMemory()
        } catch { isBusy = false; errorMessage = error.localizedDescription }
    }

    func receiveTwinAnswer(_ answer: TwinAnswerRecord, turnID: UUID? = nil) {
        guard !isGuestMode else { return }
        twinAnswer = answer
        twinChat.receive(answer, for: turnID)
        persistChatIndex()
        if (answer.recalled_turn_count ?? 0) > 0 {
            chatNotice = "已找回 \(answer.recalled_turn_count ?? 0) 段旧聊天。" + (answer.history_summary_status == "unavailable" ? "摘要暂不可用，仍参考原消息。" : "")
        } else if answer.context_truncated == true {
            chatNotice = "较早前文已移出即时上下文；旧聊天会按问题检索，重要条件可以再核对。"
        }
    }

    func rememberChatTurn(_ id: UUID) async -> Bool {
        guard !isBusy, !personReview.isMutating, cloudCapabilities?.chat_memory == true,
              let pairing, let client, let cloudConsentID,
              let turn = twinChat.turns.first(where: { $0.id == id }), let answerID = turn.answer?.id ?? turn.savedAnswerID else { return false }
        isBusy = true; defer { isBusy = false }
        do {
            let grants = try await client.consents(subjectID: pairing.subjectID)
            let recordingID: String
            if let existing = grants.last(where: { $0.scope == "RECORDING" && $0.status == "granted" }) { recordingID = existing.id }
            else { recordingID = try await client.grantConsent(subjectID: pairing.subjectID, scope: "RECORDING").id }
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return false }
            _ = try await client.rememberChatMessage(subjectID: pairing.subjectID, answerID: answerID,
                                                     cloudConsentID: cloudConsentID, recordingConsentID: recordingID)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return false }
            twinContentRevision = UUID(); twinChat.invalidateAnswers()
            // Existing reviewed-profile pipeline: suggestions remain pending.
            let queued = await personReview.requestSuggestions(consentID: cloudConsentID, narrative: false)
            await refresh()
            chatNotice = queued ? "已保存这条本人文字记忆。新的理解整理后，仍由你核对确认。" : "文字记忆已保存；人物整理暂未提交，可以到「我的理解与表达」重试。"
            return true
        } catch {
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing) else { return false }
            errorMessage = "暂时没能记住这句话：\(error.localizedDescription)"; return false
        }
    }

    func askTwin() async {
        await sendTwin(question: queryDraft.trimmingCharacters(in: .whitespacesAndNewlines))
    }
    func retryTwin(_ turnID: UUID) async {
        guard let turn = twinChat.turns.first(where: { $0.id == turnID }), turn.failure != nil else { return }
        if let id = turn.savedAnswerID { await refreshChatAnswer(id) }
        else { await sendTwin(question: turn.question, retryID: turnID) }
    }
    private func sendTwin(question: String, retryID: UUID? = nil) async {
        guard !isBusy, !isRestoringChat, !personReview.isMutating, !isRecording, !isQueryRecording,
              let pairing, let client, let cloudConsentID else { return }
        let contentRevision = twinContentRevision
        guard cloudCapabilities?.twin_conversation == true || !memories.isEmpty || episodes.contains(where: { $0.status == "ready" }) else { errorMessage = "请先录音并核对文字，再向 Twin 提问。"; return }
        guard !question.isEmpty else { return }
        let turnID: UUID
        if let retryID {
            guard twinChat.retry(retryID) else { return }
            turnID = retryID
        } else { turnID = twinChat.begin(question, conversationMode: cloudCapabilities?.twin_conversation == true); queryDraft = "" }
        guard let sendingTurn = twinChat.turns.first(where: { $0.id == turnID }) else { return }
        errorMessage = nil; persistChatIndex()
        isBusy = true; isAskingTwin = true
        defer { isBusy = false; isAskingTwin = false }
        do {
            let result = try await client.askTwin(subjectID: pairing.subjectID, question: question,
                cloudConsentID: cloudConsentID, conversationMode: sendingTurn.conversationMode == true,
                previousAnswerID: sendingTurn.previousAnswerID, requestID: sendingTurn.requestID ?? turnID.uuidString)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            receiveTwinAnswer(result, turnID: turnID)
            defaults.set(result.id, forKey: answerStorageKey(pairing))
        } catch {
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            if case APIError.server(409, _) = error { twinChat.renewRequest(turnID) }
            twinChat.fail(turnID, message: "暂时没能回答，请稍后重试。")
            if retryID == nil && queryDraft.isEmpty { queryDraft = question }
            persistChatIndex()
            errorMessage = "孪生暂时没能回答：\(error.localizedDescription)"
        }
    }

    private func beginAuxiliaryRecording(voice: Bool, cloudASRPolicy: String? = nil, readingPrompt: String? = nil) async {
        stopPlayback()
        errorMessage = nil
        guard !isBusy, let pairing else { errorMessage = "请先连接记忆服务。"; return }
        guard !realtimeVoice.isActive else { errorMessage = "请先结束语音通话。"; return }
        if !voice && pairing.isCloud && cloudCapabilities?.stt_processing == "cloud" && cloudASRPolicy == nil {
            errorMessage = "请先确认提问原音的云端转写用途。"; return
        }
        guard !isSpeakerRecording && !isRecording && !isStartingRecording && auxiliaryRecorder == nil else {
            errorMessage = "请先结束正在进行的录音。"
            return
        }
        deferDeviceUploads()
        let owner = RecordingOwner(pairing), token = pairing.token, start = UUID()
        auxiliaryStartGeneration = start; auxiliaryRecordingOwner = owner
        isBusy = true
        defer {
            if auxiliaryStartGeneration == start {
                isBusy = false
                if auxiliaryRecorder == nil { auxiliaryRecordingOwner = nil }
            }
        }
        let granted = await recordPermission()
        guard auxiliaryStartGeneration == start,
              self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token,
              !Task.isCancelled, !realtimeVoice.isActive, !isRecording, auxiliaryRecorder == nil else { return }
        guard granted else { errorMessage = "麦克风权限已拒绝。请到系统设置中打开。"; return }
        guard applicationIsActive() else { return }
        do {
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP])
            try audio.setActive(true)
            let url: URL
            if voice {
                var root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                    .appendingPathComponent("VoiceSamples", isDirectory: true)
                try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
                var values = URLResourceValues()
                values.isExcludedFromBackup = true
                try root.setResourceValues(values)
                url = root.appendingPathComponent(UUID().uuidString + ".m4a")
            } else {
                url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
            }
            let settings: [String: Any] = [AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                                           AVSampleRateKey: 44100, AVNumberOfChannelsKey: 1,
                                           AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            guard recorder.record() else { throw APIError.invalidResponse }
            auxiliaryRecorder = recorder
            auxiliaryCloudPolicy = cloudASRPolicy
            auxiliaryReadingPrompt = voice ? readingPrompt : nil
            auxiliaryURL = url
            isVoiceRecording = voice
            isQueryRecording = !voice
            auxiliarySeconds = 0
            auxiliaryStartedAt = Date()
            auxiliaryTimer?.invalidate()
            let recordingTimer = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, self.auxiliaryStartGeneration == start, let recorder = self.auxiliaryRecorder else { return }
                    self.auxiliarySeconds = max(0, Int(recorder.currentTime))
                }
            }
            auxiliaryTimer = recordingTimer
            RunLoop.main.add(recordingTimer, forMode: .common)
            observeCaptureReset(auxiliaryID: start)
        } catch { errorMessage = "录音无法开始：\(error.localizedDescription)" }
    }

    func startQueryRecording(cloudASRPolicy: String? = nil) async { await beginAuxiliaryRecording(voice: false, cloudASRPolicy: cloudASRPolicy) }
    func startVoiceSample(readingPrompt: String? = nil) async { await beginAuxiliaryRecording(voice: true, readingPrompt: readingPrompt) }

    func finishAuxiliaryRecording() async {
        guard let recorder = auxiliaryRecorder, let url = auxiliaryURL else { return }
        captureResetObservation = nil
        let policy = auxiliaryCloudPolicy
        let readingPrompt = auxiliaryReadingPrompt
        auxiliaryReadingPrompt = nil
        auxiliaryCloudPolicy = nil
        let wasVoice = isVoiceRecording
        let owner = auxiliaryRecordingOwner
        auxiliaryRecordingOwner = nil
        recorder.stop()
        auxiliaryTimer?.invalidate()
        auxiliaryTimer = nil
        auxiliaryStartedAt = nil
        auxiliaryRecorder = nil
        auxiliaryURL = nil
        isVoiceRecording = false
        isQueryRecording = false
        if wasVoice, let owner {
            // The prompt becomes sample text only after an intentional finish.
            // The UI still requires the speaker to confirm that it matches the audio.
            retainVoiceSample(url, owner: owner, transcript: readingPrompt ?? "", readingPrompt: readingPrompt)
            if readingPrompt != nil { return }
        }
        guard let pairing, let client, let owner, RecordingOwner(pairing) == owner else {
            errorMessage = "录音已停止并保留，请重新连接原来的本人空间。"; return
        }
        let token = pairing.token
        isBusy = true
        defer { isBusy = false }
        do {
            if pairing.isCloud && !wasVoice {
                let caps = try await client.capabilities()
                guard caps.stt_processing != "cloud" || caps.cloud_asr_policy == policy && policy != nil else {
                    throw APIError.server(409, "转写用途已变化，请重新确认后再提问。")
                }
            }
            guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token else { return }
            let audio = try Data(contentsOf: url)
            if wasVoice {
                let transcript = pairing.isCloud ? nil : try? await client.transcribeQuery(subjectID: pairing.subjectID, audio: audio)
                guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token else { return }
                retainVoiceSample(url, owner: owner, transcript: transcript?.text ?? "")
                if voiceSampleTranscript.isEmpty {
                    errorMessage = "样本已保留。请按你实际说的话填写文字，再确认提交。"
                }
            } else {
                defer { try? FileManager.default.removeItem(at: url) }
                let transcript = try await client.transcribeQuery(subjectID: pairing.subjectID, audio: audio, cloudASRPolicy: policy).text
                guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token else { return }
                queryDraft = transcript
            }
        } catch { errorMessage = "识别暂时失败，仍可手动输入问题：\(error.localizedDescription)" }
    }

    func stopAuxiliaryForBackground() {
        auxiliaryStartGeneration = UUID()
        guard let recorder = auxiliaryRecorder else {
            if auxiliaryRecordingOwner != nil { isBusy = false }
            auxiliaryRecordingOwner = nil
            return
        }
        captureResetObservation = nil
        let wasVoice = isVoiceRecording
        let owner = auxiliaryRecordingOwner
        auxiliaryRecordingOwner = nil
        recorder.stop(); auxiliaryTimer?.invalidate(); auxiliaryTimer = nil
        auxiliaryRecorder = nil; auxiliaryStartedAt = nil
        isVoiceRecording = false; isQueryRecording = false
        if let url = auxiliaryURL, wasVoice, let owner {
            retainVoiceSample(url, owner: owner, transcript: "")
        } else if let url = auxiliaryURL {
            defaults.set(url.path, forKey: "pending-query-recording")
        }
        auxiliaryURL = nil; auxiliaryCloudPolicy = nil; auxiliaryReadingPrompt = nil
        errorMessage = "录音已停止并保留在手机。回到前台后请试听；提问可重新录制或输入文字。"
    }
    func retainVoiceSample(_ url: URL, owner: RecordingOwner, transcript: String, readingPrompt: String? = nil) {
        if pairing.map(RecordingOwner.init) == owner,
           let old = voiceSampleURL, old != url { try? FileManager.default.removeItem(at: old) }
        try? FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: url.path)
        defaults.set(url.path, forKey: "pending-voice-sample")
        defaults.set(try? JSONEncoder().encode(owner), forKey: "pending-voice-owner")
        defaults.set(transcript, forKey: "pending-voice-transcript")
        defaults.set(readingPrompt, forKey: "pending-voice-reading-prompt")
        if pairing.map(RecordingOwner.init) == owner {
            voiceSampleURL = url; voiceSampleTranscript = transcript; voiceSampleReadingPrompt = readingPrompt
        }
    }
    func playVoiceSample() {
        guard !isGuestMode else { return }
        guard !isRecording, !isQueryRecording, !isVoiceRecording, let voiceSampleURL else { return }
        do { try beginPlayback(AVAudioPlayer(contentsOf: voiceSampleURL), identity: "voice-sample") }
        catch { errorMessage = "样本无法播放：\(error.localizedDescription)" }
    }

    func enrollVoice() async {
        guard let pairing, let client, let voiceSampleURL else { return }
        let transcript = voiceSampleTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !transcript.isEmpty else { errorMessage = "请先核对样本的原话文字。"; return }
        isBusy = true
        defer { isBusy = false }
        do {
            let consentID: String
            if let voiceConsentID { consentID = voiceConsentID }
            else {
                consentID = try await client.grantConsent(subjectID: pairing.subjectID, scope: "VOICE").id
                voiceConsentID = consentID
            }
            let audio = try Data(contentsOf: voiceSampleURL)
            let profile = try await client.enrollVoice(subjectID: pairing.subjectID, consentID: consentID,
                                                       transcript: transcript, audio: audio)
            voiceProfileReady = profile.ready
            try? FileManager.default.removeItem(at: voiceSampleURL)
            self.voiceSampleURL = nil; voiceSampleReadingPrompt = nil
            defaults.removeObject(forKey: "pending-voice-sample")
            defaults.removeObject(forKey: "pending-voice-transcript")
            defaults.removeObject(forKey: "pending-voice-reading-prompt")
        } catch { errorMessage = "声音样本未能提交，手机里的样本还在：\(error.localizedDescription)" }
    }

    func revokeVoice() async {
        guard let voiceConsentID, let pairing, let client else { return }
        do {
            try await client.revokeConsent(voiceConsentID)
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            twinContentRevision = UUID()
            self.voiceConsentID = nil
            voiceProfileReady = false
            if let voiceSampleURL { try? FileManager.default.removeItem(at: voiceSampleURL) }
            voiceSampleURL = nil; voiceSampleReadingPrompt = nil
            defaults.removeObject(forKey: "pending-voice-sample")
            defaults.removeObject(forKey: "pending-voice-transcript")
            defaults.removeObject(forKey: "pending-voice-reading-prompt")
        } catch {
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            errorMessage = "声音授权未能撤销：\(error.localizedDescription)"
        }
    }

    func playTwinVoice() async {
        guard !hasRealtimeAudioWork, !personReview.isMutating, let pairing, let client, let twinAnswer, !twinAnswer.stale else { return }
        let contentRevision = twinContentRevision
        isBusy = true
        defer { isBusy = false }
        do {
            let asset = try await client.createSpeech(subjectID: pairing.subjectID, answerID: twinAnswer.id)
            let audio = try await client.speechAudio(subjectID: pairing.subjectID, assetID: asset.asset_id)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            try beginPlayback(AVAudioPlayer(data: audio), identity: "twin-\(twinAnswer.id)")
        } catch {
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            errorMessage = "个人声音暂时无法播放：\(error.localizedDescription)"
        }
    }

    func startCalibration(answerID: String? = nil) async {
        guard !isBusy, !personReview.isMutating, let pairing, let client, let cloudConsentID,
              let id = answerID ?? twinAnswer?.id,
              let displayed = twinChat.turns.first(where: { $0.answer?.id == id }), !displayed.invalidated,
              ["ORIGINAL", "SIMULATION"].contains(displayed.answer?.response_type ?? "") else { return }
        let contentRevision = twinContentRevision
        isBusy = true
        defer { isBusy = false }
        do {
            let answer = try await client.twinAnswer(subjectID: pairing.subjectID, answerID: id)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            twinChat.receive(answer)
            guard !answer.stale, ["ORIGINAL", "SIMULATION"].contains(answer.response_type) else {
                errorMessage = "相关记忆已有变化，请重新提问后再纠正。"; return
            }
            let result = try await client.startCalibration(
                subjectID: pairing.subjectID, answerID: answer.id, cloudConsentID: cloudConsentID)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            calibrationRun = result
        } catch {
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            errorMessage = "暂时无法锁定 Twin 回答：\(error.localizedDescription)"
        }
    }

    func completeCalibration(_ calibrationID: String) async {
        guard !personReview.isMutating, let pairing, let client, let cloudConsentID else { return }
        let contentRevision = twinContentRevision
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await client.completeCalibration(
                subjectID: pairing.subjectID, calibrationID: calibrationID,
                cloudConsentID: cloudConsentID)
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            calibrationRun = result
        } catch {
            guard self.pairing.map(ReviewScope.init) == ReviewScope(pairing), contentRevision == twinContentRevision else { return }
            errorMessage = "录音已保存，校准比较可稍后重试：\(error.localizedDescription)"
        }
    }
}


extension AppModel {
    func startDefaultVoiceCall() async { await startNaturalVoiceCall(useDefault: true) }
    func startNaturalVoiceCall(useDefault: Bool, enrollOwnerVoice: Bool = false) async {
        guard !Task.isCancelled, applicationIsActive(), !recordingStartBlocked, let pairing, let client,
              realtimeVoice.capabilities?.available == true else { return }
        guard useDefault || personalVoiceAccepted else {
            errorMessage = "请先试听，并确认使用这个本人音色。"; return
        }
        deferDeviceUploads()
        let owner = RecordingOwner(pairing), token = pairing.token, request = UUID()
        naturalCallStartID = request
        pendingNaturalCallStartID = request
        isBusy = true; errorMessage = nil
        defer {
            if pendingNaturalCallStartID == request {
                pendingNaturalCallStartID = nil; isBusy = false
                if !realtimeVoice.isActive { processDeviceRecordingQueue() }
            }
        }
        stopPlayback()
        @MainActor func current() -> Bool { !Task.isCancelled && applicationIsActive() && naturalCallStartID == request && self.pairing?.token == token && self.pairing.map(RecordingOwner.init) == owner }
        do {
            let grants = try await client.consents(subjectID: pairing.subjectID)
            guard current() else { return }
            func grant(_ scope: String) async throws -> String {
                if let existing = grants.last(where: { $0.scope == scope && $0.status == "granted" }) { return existing.id }
                let result = try await client.grantConsent(subjectID: pairing.subjectID, scope: scope, evidenceRef: "ios-start-natural-call").id
                guard current() else { throw CancellationError() }
                return result
            }
            let cloud = try await grant("CLOUD_TWIN")
            let voice = useDefault ? try await grant("VOICE") : realtimeVoice.profile?.voice_consent_id
            guard current(), let voice else { return }
            var recording: String?, speaker: String?
            if realtimeVoice.capabilities?.dialogue_capture_available == true {
                recording = try await grant("RECORDING")
                speaker = try await grant("SPEAKER_IDENTIFICATION")
            }
            guard current() else { return }
            cloudConsentID = cloud; voiceConsentID = voice
            await realtimeVoice.start(cloudConsent: cloud, voiceConsent: voice, voiceMode: useDefault ? "default" : "personal", recordingConsent: recording, speakerConsent: speaker, enrollOwnerVoice: enrollOwnerVoice || (realtimeVoice.capabilities?.voiceprint_available == true && realtimeVoice.capabilities?.owner_voice_registered != true))
        } catch {
            guard current() else { return }
            errorMessage = "通话未能开始，可稍后重试：\(error.localizedDescription)"
        }
    }
    func saveVoiceSampleTranscript(_ text: String) {
        guard voiceSampleURL != nil else { return }
        defaults.set(text, forKey: "pending-voice-transcript")
    }
    func previewRealtimeVoice() async {
        guard let pairing, let client, realtimeVoice.profile?.ready == true,
              !realtimeVoice.isActive, !isRecording, !isQueryRecording, !isVoiceRecording else { return }
        stopPlayback()
        let request = UUID(), scope = RecordingOwner(pairing), profileID = realtimeVoice.profile?.profile_id
        var startingPlayback = false
        playbackRequestID = request; playbackLoading = true; errorMessage = nil
        recordVoicePreviewDiagnostics("requesting")
        defer { if playbackRequestID == request { playbackLoading = false } }
        do {
            let audio = try await client.realtimeVoicePreview(subjectID: pairing.subjectID, transport: realtimeVoice.capabilities?.transport)
            guard playbackRequestID == request, self.pairing?.token == pairing.token,
                  self.pairing.map(RecordingOwner.init) == scope, realtimeVoice.profile?.profile_id == profileID,
                  !realtimeVoice.isActive else { return }
            let preview = try AVAudioPlayer(data: audio)
            startingPlayback = true
            try beginPlayback(preview, identity: "realtime-voice-preview")
            recordVoicePreviewDiagnostics("playing", byteCount: audio.count)
            await refreshRealtimeVoiceReview()
            if AVAudioSession.sharedInstance().outputVolume <= 0.001 {
                errorMessage = "试听已开始，但手机媒体音量为零，请按侧边音量加键。"
            }
            Task { @MainActor [weak self] in
                try? await Task.sleep(for: .milliseconds(750))
                guard let self, self.player === preview, self.playbackID == "realtime-voice-preview" else { return }
                self.recordVoicePreviewDiagnostics("progress", byteCount: audio.count)
            }
        } catch {
            // beginPlayback clears the fetch request when it releases previous
            // playback. A session/player failure after that still needs a notice.
            guard playbackRequestID == request || startingPlayback,
                  self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == scope,
                  realtimeVoice.profile?.profile_id == profileID, !realtimeVoice.isActive else { return }
            recordVoicePreviewDiagnostics("failed")
            errorMessage = "音色试听未能生成：\(error.localizedDescription)"
        }
    }
    private func recordVoicePreviewDiagnostics(_ phase: String, byteCount: Int = 0) {
        // Numeric playback state only: no audio, text, profile IDs or credentials.
        guard let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return }
        var directory = base.appendingPathComponent("VoiceDiagnostics", isDirectory: true)
        let audio = AVAudioSession.sharedInstance()
        let snapshot: [String: Any] = ["phase":phase,"timestamp":Date().timeIntervalSince1970,
            "bytes":byteCount,"duration":player?.duration ?? 0,"position":player?.currentTime ?? 0,
            "playing":player?.isPlaying ?? false,"playerVolume":player?.volume ?? 0,
            "outputVolume":audio.outputVolume,
            "speakerOutput":audio.currentRoute.outputs.contains { $0.portType == .builtInSpeaker }]
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            var values = URLResourceValues(); values.isExcludedFromBackup = true
            try directory.setResourceValues(values)
            let data = try JSONSerialization.data(withJSONObject: snapshot)
            try data.write(to: directory.appendingPathComponent("preview.json"), options: [.atomic,.completeFileProtection])
        } catch { /* Diagnostics never prevent playback. */ }
    }
    func prepareRealtimeVoice() async {
        guard let pairing, let client else { return }
        realtimeVoice.configure(pairing, client: client)
        await realtimeVoice.prepare()
        await refreshRealtimeVoiceReview()
    }
    func refreshRealtimeVoiceReview() async {
        guard let pairing, let client else { realtimeVoiceReview = nil; return }
        let token = pairing.token, owner = RecordingOwner(pairing), profileID = realtimeVoice.profile?.profile_id
        do {
            let review = try await client.realtimeVoiceReview(subjectID: pairing.subjectID, transport: realtimeVoice.capabilities?.transport)
            guard self.pairing?.token == token, self.pairing.map(RecordingOwner.init) == owner,
                  realtimeVoice.profile?.profile_id == profileID else { return }
            guard review.profile_id == profileID else { realtimeVoiceReview = nil; return }
            realtimeVoiceReview = review
        } catch {
            guard self.pairing?.token == token, self.pairing.map(RecordingOwner.init) == owner,
                  realtimeVoice.profile?.profile_id == profileID else { return }
            realtimeVoiceReview = nil
        }
    }
    func reviewRealtimeVoice(accepted: Bool) async {
        guard !isBusy, !realtimeVoice.isActive, let pairing, let client,
              let profileID = realtimeVoice.profile?.profile_id else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        stopPlayback(); isBusy = true; errorMessage = nil; defer { isBusy = false }
        do {
            let review = try await client.realtimeVoiceReview(subjectID: pairing.subjectID,
                transport: realtimeVoice.capabilities?.transport, profileID: profileID, accepted: accepted)
            guard self.pairing?.token == token, self.pairing.map(RecordingOwner.init) == owner,
                  realtimeVoice.profile?.profile_id == profileID else { return }
            guard review.profile_id == profileID else { throw APIError.invalidResponse }
            realtimeVoiceReview = review
        } catch {
            guard self.pairing?.token == token, self.pairing.map(RecordingOwner.init) == owner else { return }
            errorMessage = "音色确认未能保存：\(error.localizedDescription)"
        }
    }
    func retryRealtimeVoice() async {
        guard !isBusy, !realtimeVoice.isActive, let pairing, let client,
              let profileID = realtimeVoice.profile?.profile_id else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        stopPlayback(); isBusy = true; errorMessage = nil; defer { isBusy = false }
        do {
            try await client.retryRealtimeVoice(subjectID: pairing.subjectID, profileID: profileID,
                transport: realtimeVoice.capabilities?.transport)
            guard self.pairing?.token == token, self.pairing.map(RecordingOwner.init) == owner,
                  realtimeVoice.profile?.profile_id == profileID else { return }
            realtimeVoice.resetProfile(); realtimeVoiceReview = nil
            await prepareRealtimeVoice()
        } catch {
            guard self.pairing?.token == token, self.pairing.map(RecordingOwner.init) == owner else { return }
            errorMessage = "音色未能重新准备，请刷新后重试：\(error.localizedDescription)"
        }
    }
    func enrollRealtimeVoice(policy: String) async {
        guard !realtimeVoice.isActive, let pairing, let client, let url = voiceSampleURL else { return }
        let scope = RecordingOwner(pairing), token = pairing.token
        isBusy = true; errorMessage = nil; defer { isBusy = false }
        let text = voiceSampleTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        do {
            let consent: String
            if let voiceConsentID { consent = voiceConsentID }
            else {
                consent = try await client.grantConsent(subjectID: pairing.subjectID, scope: "VOICE").id
            }
            guard self.pairing.map(RecordingOwner.init) == scope, self.pairing?.token == token else { return }
            voiceConsentID = consent
            let profile = try await client.enrollRealtimeVoice(subjectID: pairing.subjectID, consentID: consent,
                transcript: text, policy: policy, audio: Data(contentsOf: url), transport: realtimeVoice.capabilities?.transport)
            guard self.pairing.map(RecordingOwner.init) == scope, self.pairing?.token == token else { return }
            realtimeVoice.enrolled(profile)
            realtimeVoiceReview = nil
            try? FileManager.default.removeItem(at: url)
            voiceSampleURL = nil; voiceSampleTranscript = ""; voiceSampleReadingPrompt = nil
            defaults.removeObject(forKey: "pending-voice-sample")
            defaults.removeObject(forKey: "pending-voice-transcript")
            defaults.removeObject(forKey: "pending-voice-reading-prompt")
            defaults.removeObject(forKey: "pending-voice-owner")
        } catch { errorMessage = "声音样本未能提交，手机里的样本还在：\(error.localizedDescription)" }
    }
    func revokeRealtimeVoice() async {
        guard !isBusy, let pairing else { return }
        isBusy = true; defer { isBusy = false }
        stopPlayback()
        await realtimeVoice.end()
        guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
        guard let consent = realtimeVoice.profile?.voice_consent_id ?? voiceConsentID, let client else { return }
        do {
            try await client.revokeConsent(consent)
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            twinContentRevision = UUID()
            realtimeVoice.resetProfile(); realtimeVoiceReview = nil; voiceConsentID = nil; voiceProfileReady = false
            if let voiceSampleURL { try? FileManager.default.removeItem(at: voiceSampleURL) }
            voiceSampleURL = nil; voiceSampleTranscript = ""; voiceSampleReadingPrompt = nil
            for key in ["pending-voice-sample", "pending-voice-transcript", "pending-voice-owner", "pending-voice-reading-prompt"] { defaults.removeObject(forKey: key) }
        } catch {
            guard self.pairing?.token == pairing.token, self.pairing.map(RecordingOwner.init) == RecordingOwner(pairing) else { return }
            errorMessage = "声音授权未能撤销：\(error.localizedDescription)"
        }
    }
}

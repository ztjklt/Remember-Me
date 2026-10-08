import Foundation
import AVFoundation
import SwiftUI

struct RecordingDraft: Codable, Identifiable {
    let id: String
    let fileURL: URL
    let recordedAt: Date
    let durationMS: Int
    let questionID: String?
    let calibrationID: String?
    let consentConfirmedAt: Date
}

@MainActor
final class AppModel: ObservableObject {
    @Published var showConnection = false
    @Published var pairing: Pairing? = PairingStore.load()
    @Published var pairingServer = ""
    @Published var pairingCode = ""
    @Published var pairingFingerprint = ""
    @Published var memories: [MemoryRecord] = []
    @Published var episodes: [EpisodeRecord] = []
    @Published var domains: [DomainRecord] = []
    @Published var questions: [QuestionRecord] = []
    @Published var modelVersion = 0
    @Published var draft: RecordingDraft?
    @Published var episodeID: String?
    @Published var processingStatus = ""
    @Published var transcriptDraft = ""
    @Published var isTranscriptReviewReady = false
    @Published var errorMessage: String?
    @Published var isBusy = false
    @Published var isRecording = false
    @Published var isPaused = false
    @Published var recordedSeconds = 0
    @Published var meterLevels: [CGFloat] = Array(repeating: 0.16, count: 27)
    @Published var isPlaying = false
    @Published var playbackID: String?
    @Published var playbackPosition: TimeInterval = 0
    @Published var playbackDuration: TimeInterval = 0
    @Published var playbackLoading = false
    private var playbackTimer: Timer?
    private var playbackRequestID: UUID?
    @Published var queryDraft = ""
    @Published var twinAnswer: TwinAnswerRecord?
    @Published var cloudConsentID: String?
    @Published var voiceConsentID: String?
    @Published var voiceProfileReady = false
    @Published var voiceSampleTranscript = ""
    @Published var voiceSampleURL: URL?
    @Published var isQueryRecording = false
    @Published var isVoiceRecording = false
    @Published var memorySearchQuery = ""
    @Published var memorySearchResults: [MemorySearchRecord] = []
    @Published var auxiliarySeconds = 0
    @Published var calibrationRun: CalibrationRecord?

    private var recorder: AVAudioRecorder?
    private var player: AVAudioPlayer?
    private var timer: Timer?
    private var startedAt: Date?
    private var accumulated: TimeInterval = 0
    private var auxiliaryRecorder: AVAudioRecorder?
    private var auxiliaryURL: URL?
    private var auxiliaryTimer: Timer?
    private var auxiliaryStartedAt: Date?

    init() {
        if let data = UserDefaults.standard.data(forKey: "pending-recording") {
            draft = try? JSONDecoder().decode(RecordingDraft.self, from: data)
            if let pending = draft, !FileManager.default.fileExists(atPath: pending.fileURL.path) {
                self.draft = nil
            }
        }
        episodeID = UserDefaults.standard.string(forKey: "pending-episode")
        if let path = UserDefaults.standard.string(forKey: "pending-voice-sample"),
           FileManager.default.fileExists(atPath: path) {
            voiceSampleURL = URL(fileURLWithPath: path)
            voiceSampleTranscript = UserDefaults.standard.string(forKey: "pending-voice-transcript") ?? ""
        }
    }

    private var client: APIClient? {
        guard let pairing else { return nil }
        return try? APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint,
                              token: pairing.token)
    }

    func importPairingLink(_ url: URL) {
        guard url.scheme == "rememberme", url.host == "pair",
              let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return }
        func value(_ name: String) -> String { parts.first(where: { $0.name == name })?.value ?? "" }
        showConnection = true
        pairingServer = value("server")
        pairingCode = value("code")
        pairingFingerprint = value("sha256")
    }

    func connect() async {
        guard pairing == nil || (draft == nil && episodeID == nil && !isRecording) else {
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
            try PairingStore.save(connected)
            if pairing?.baseURL != connected.baseURL || pairing?.fingerprint != connected.fingerprint ||
                pairing?.subjectID != connected.subjectID || pairing?.actorID != connected.actorID {
                memories = []; episodes = []; domains = []; questions = []
                modelVersion = 0; twinAnswer = nil; calibrationRun = nil
                cloudConsentID = nil; voiceConsentID = nil; voiceProfileReady = false
                memorySearchResults = []; memorySearchQuery = ""; queryDraft = ""
                stopPlayback()
            }
            pairing = connected
            showConnection = false
            await refresh()
        } catch { errorMessage = error.localizedDescription }
    }

    func refresh() async {
        guard let pairing, let client else { return }
        do {
            async let nextMemories = client.memories(pairing.subjectID)
            async let nextEpisodes = client.episodes(pairing.subjectID)
            async let nextModel = client.model(pairing.subjectID)
            async let nextQuestions = client.questions(pairing.subjectID)
            async let nextConsents = client.consents(subjectID: pairing.subjectID)
            async let nextVoiceProfile = client.voiceProfile(subjectID: pairing.subjectID)
            async let nextCalibrations = client.calibrations(subjectID: pairing.subjectID)
            memories = try await nextMemories
            episodes = try await nextEpisodes
            let snapshot = try await nextModel
            domains = snapshot.domains
            modelVersion = snapshot.version
            questions = try await nextQuestions
            let grants = try await nextConsents
            cloudConsentID = grants.last(where: { $0.scope == "CLOUD_TWIN" && $0.status == "granted" })?.id
            voiceConsentID = grants.last(where: { $0.scope == "VOICE" && $0.status == "granted" })?.id
            let profile = try await nextVoiceProfile
            voiceProfileReady = profile.ready
            calibrationRun = try await nextCalibrations.first
            if cloudConsentID != nil,
               let answerID = UserDefaults.standard.string(forKey: "last-twin-answer-\(pairing.subjectID)") {
                twinAnswer = try? await client.twinAnswer(subjectID: pairing.subjectID, answerID: answerID)
            } else {
                twinAnswer = nil
            }
            errorMessage = nil
        } catch { errorMessage = error.localizedDescription }
    }

    func startRecording(questionID: String? = nil, calibrationID: String? = nil) async {
        guard !isRecording else { return }
        stopPlayback()
        errorMessage = nil
        transcriptDraft = ""
        isTranscriptReviewReady = false
        let granted = await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard granted else {
            errorMessage = "麦克风权限已拒绝。请在系统设置中允许 Remember Me 使用麦克风，然后再试。"
            return
        }
        do {
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP])
            try audio.setActive(true)
            var root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("Recordings", isDirectory: true)
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
            guard recorder.record() else { throw APIError.invalidResponse }
            self.recorder = recorder
            self.draft = RecordingDraft(id: id, fileURL: url, recordedAt: Date(),
                                        durationMS: 0, questionID: questionID,
                                        calibrationID: calibrationID,
                                        consentConfirmedAt: Date())
            self.isRecording = true
            self.isPaused = false
            self.recordedSeconds = 0
            self.meterLevels = Array(repeating: 0.16, count: 27)
            self.accumulated = 0
            self.startedAt = Date()
            timer?.invalidate()
            timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self else { return }
                    self.recordedSeconds = Int(self.accumulated + (self.startedAt.map { Date().timeIntervalSince($0) } ?? 0))
                    if self.isPaused { return }
                    if let recorder = self.recorder {
                        recorder.updateMeters()
                        let level = max(0.16, min(1, (recorder.averagePower(forChannel: 0) + 60) / 60))
                        self.meterLevels.removeFirst()
                        self.meterLevels.append(CGFloat(level))
                    }
                }
            }
        } catch { errorMessage = "录音未能开始：\(error.localizedDescription)" }
    }

    func pauseOrResume() {
        guard let recorder else { return }
        if isPaused {
            if recorder.record() { startedAt = Date(); isPaused = false }
        } else {
            accumulated += startedAt.map { Date().timeIntervalSince($0) } ?? 0
            startedAt = nil
            recorder.pause()
            isPaused = true
        }
    }

    func finishRecording() {
        guard let recorder, let draft else { return }
        let duration = accumulated + (startedAt.map { Date().timeIntervalSince($0) } ?? 0)
        recorder.stop()
        try? FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete],
                                               ofItemAtPath: draft.fileURL.path)
        self.recorder = nil
        timer?.invalidate()
        timer = nil
        isRecording = false
        isPaused = false
        self.draft = RecordingDraft(id: draft.id, fileURL: draft.fileURL,
                                    recordedAt: draft.recordedAt,
                                    durationMS: Int(duration * 1000), questionID: draft.questionID,
                                    calibrationID: draft.calibrationID,
                                    consentConfirmedAt: draft.consentConfirmedAt)
        if let data = try? JSONEncoder().encode(self.draft) {
            UserDefaults.standard.set(data, forKey: "pending-recording")
        }
    }

    func stopPlayback() {
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
    }

    func pausePlayback() {
        player?.pause()
        isPlaying = false
    }

    func toggleCurrentPlayback() {
        guard let player, !isRecording, !isQueryRecording, !isVoiceRecording else { return }
        if player.isPlaying { pausePlayback() }
        else {
            if player.currentTime >= player.duration - 0.05 { player.currentTime = 0 }
            player.play()
            isPlaying = player.isPlaying
        }
    }

    func seekPlayback(_ position: TimeInterval) {
        guard let player else { return }
        player.currentTime = min(max(0, position), player.duration)
        playbackPosition = player.currentTime
    }

    private func beginPlayback(_ next: AVAudioPlayer, identity: String) throws {
        guard !isRecording, !isQueryRecording, !isVoiceRecording else { return }
        stopPlayback()
        try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
        try AVAudioSession.sharedInstance().setActive(true)
        player = next
        playbackID = identity
        playbackDuration = next.duration
        next.prepareToPlay()
        guard next.play() else { throw APIError.invalidResponse }
        isPlaying = true
        playbackTimer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let current = self.player else { return }
                if self.isPlaying && !current.isPlaying { self.playbackPosition = current.duration }
                else if current.isPlaying { self.playbackPosition = current.currentTime }
                self.isPlaying = current.isPlaying
            }
        }
    }

    func togglePlayback() {
        guard let draft else { return }
        if playbackID == draft.id { toggleCurrentPlayback(); return }
        do { try beginPlayback(AVAudioPlayer(contentsOf: draft.fileURL), identity: draft.id) }
        catch { errorMessage = "本地录音无法播放：\(error.localizedDescription)" }
    }

    func saveTranscriptDraft() {
        guard let episodeID else { return }
        UserDefaults.standard.set(transcriptDraft, forKey: "transcript-edit-\(episodeID)")
    }

    func sendRecording() async {
        guard let draft, let pairing, let client else { return }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            if let episodeID {
                let status = try await client.status(episodeID)
                if status.status == "failed" {
                    try await client.retry(episodeID)
                }
                await pollEpisode()
                return
            }
            let id = try await client.upload(draft, pairing: pairing)
            episodeID = id
            UserDefaults.standard.set(id, forKey: "pending-episode")
            await pollEpisode()
        } catch { errorMessage = "上传失败，录音仍在手机里，可重试。\n\(error.localizedDescription)" }
    }

    func pollEpisode() async {
        guard let episodeID, let client else { return }
        for _ in 0..<180 {
            do {
                let status = try await client.status(episodeID)
                processingStatus = status.status
                if status.status == "ready" {
                    let calibrationID = draft?.calibrationID
                    UserDefaults.standard.removeObject(forKey: "transcript-edit-\(episodeID)")
                    UserDefaults.standard.removeObject(forKey: "pending-recording")
                    UserDefaults.standard.removeObject(forKey: "pending-episode")
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
                if review.state == "reviewing", let text = review.transcript {
                    if !isTranscriptReviewReady { transcriptDraft = UserDefaults.standard.string(forKey: "transcript-edit-\(episodeID)") ?? text }
                    isTranscriptReviewReady = true
                    processingStatus = "请核对转写文字"
                    return
                }
            } catch {
                errorMessage = "连接中断，录音已保留。恢复网络后可继续查看。\n\(error.localizedDescription)"
                return
            }
            try? await Task.sleep(for: .seconds(2))
        }
        errorMessage = "处理时间较长。录音已保存，可稍后回来查看。"
    }

    func submitTranscript() async {
        guard let episodeID, let client else { return }
        let text = transcriptDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            errorMessage = "转写文字不能为空。请修改后再确认。"
            return
        }
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            try await client.confirmTranscript(episodeID, transcript: text)
            isTranscriptReviewReady = false
            processingStatus = "正在提取记忆"
            await pollEpisode()
        } catch { errorMessage = "文字还没有确认，录音仍在手机和 Mac 上。\n\(error.localizedDescription)" }
    }

    func correct(_ memory: MemoryRecord, to content: String) async -> Bool {
        guard let pairing, let client else { return false }
        do { try await client.correct(subjectID: pairing.subjectID, memoryID: memory.id, content: content); await refresh(); return true }
        catch { errorMessage = error.localizedDescription; return false }
    }
    func delete(_ memory: MemoryRecord) async -> Bool {
        guard let pairing, let client else { return false }
        do {
            try await client.delete(subjectID: pairing.subjectID, memoryID: memory.id)
            memories.removeAll { $0.id == memory.id }
            memorySearchResults.removeAll { $0.id == memory.id }
            return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func playOriginal(_ memory: MemoryRecord) async {
        await playOriginal(episodeID: memory.episode_id)
    }

    func playOriginal(episodeID: String) async {
        guard let client, !isRecording, !isQueryRecording, !isVoiceRecording else { return }
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
        } catch { errorMessage = "原音暂时无法播放：\(error.localizedDescription)" }
    }

    func retryEpisode(_ episodeID: String) async {
        guard let client else { return }
        do {
            try await client.retry(episodeID)
            await refresh()
            for _ in 0..<180 {
                let status = try await client.status(episodeID)
                if status.status == "ready" || status.status == "failed" { break }
                try? await Task.sleep(for: .seconds(2))
            }
            await refresh()
        } catch { errorMessage = error.localizedDescription }
    }

    func enableCloudTwin() async {
        guard let pairing, let client else { return }
        do {
            cloudConsentID = try await client.grantConsent(subjectID: pairing.subjectID, scope: "CLOUD_TWIN").id
        } catch { errorMessage = "Twin 授权未完成：\(error.localizedDescription)" }
    }

    func revokeCloudTwin() async {
        guard let cloudConsentID, let pairing, let client else { return }
        do {
            try await client.revokeConsent(cloudConsentID)
            self.cloudConsentID = nil
            twinAnswer = nil
            UserDefaults.standard.removeObject(forKey: "last-twin-answer-\(pairing.subjectID)")
        } catch { errorMessage = "Twin 授权未能撤销：\(error.localizedDescription)" }
    }

    func searchMemories() async {
        guard let pairing, let client else { return }
        let query = memorySearchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { memorySearchResults = []; return }
        do { memorySearchResults = try await client.searchMemories(subjectID: pairing.subjectID, query: query) }
        catch { errorMessage = "记忆检索暂时不可用：\(error.localizedDescription)" }
    }

    func askTwin() async {
        guard let pairing, let client, let cloudConsentID else { return }
        let question = queryDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !question.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await client.askTwin(subjectID: pairing.subjectID, question: question,
                                                  cloudConsentID: cloudConsentID)
            twinAnswer = result
            UserDefaults.standard.set(result.id, forKey: "last-twin-answer-\(pairing.subjectID)")
        } catch { errorMessage = "Twin 暂时没能回答：\(error.localizedDescription)" }
    }

    private func beginAuxiliaryRecording(voice: Bool) async {
        stopPlayback()
        errorMessage = nil
        guard !isRecording && auxiliaryRecorder == nil else {
            errorMessage = "请先结束正在进行的录音。"
            return
        }
        let granted = await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard granted else { errorMessage = "麦克风权限已拒绝。请到系统设置中打开。"; return }
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
            auxiliaryURL = url
            isVoiceRecording = voice
            isQueryRecording = !voice
            auxiliarySeconds = 0
            auxiliaryStartedAt = Date()
            auxiliaryTimer?.invalidate()
            auxiliaryTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, let started = self.auxiliaryStartedAt else { return }
                    self.auxiliarySeconds = Int(Date().timeIntervalSince(started))
                }
            }
        } catch { errorMessage = "录音无法开始：\(error.localizedDescription)" }
    }

    func startQueryRecording() async { await beginAuxiliaryRecording(voice: false) }
    func startVoiceSample() async { await beginAuxiliaryRecording(voice: true) }

    func finishAuxiliaryRecording() async {
        guard let recorder = auxiliaryRecorder, let url = auxiliaryURL, let pairing, let client else { return }
        let wasVoice = isVoiceRecording
        recorder.stop()
        auxiliaryTimer?.invalidate()
        auxiliaryTimer = nil
        auxiliaryStartedAt = nil
        auxiliaryRecorder = nil
        auxiliaryURL = nil
        isVoiceRecording = false
        isQueryRecording = false
        do {
            let audio = try Data(contentsOf: url)
            if wasVoice {
                if let old = voiceSampleURL { try? FileManager.default.removeItem(at: old) }
                try? FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: url.path)
                voiceSampleURL = url
                let transcript = try? await client.transcribeQuery(subjectID: pairing.subjectID, audio: audio)
                voiceSampleTranscript = transcript?.text ?? ""
                UserDefaults.standard.set(url.path, forKey: "pending-voice-sample")
                UserDefaults.standard.set(voiceSampleTranscript, forKey: "pending-voice-transcript")
                if voiceSampleTranscript.isEmpty {
                    errorMessage = "样本已保留。请按你实际说的话填写文字，再确认提交。"
                }
            } else {
                defer { try? FileManager.default.removeItem(at: url) }
                queryDraft = try await client.transcribeQuery(subjectID: pairing.subjectID, audio: audio).text
            }
        } catch { errorMessage = "识别暂时失败，仍可手动输入问题：\(error.localizedDescription)" }
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
            self.voiceSampleURL = nil
            UserDefaults.standard.removeObject(forKey: "pending-voice-sample")
            UserDefaults.standard.removeObject(forKey: "pending-voice-transcript")
        } catch { errorMessage = "声音样本未能提交，手机里的样本还在：\(error.localizedDescription)" }
    }

    func revokeVoice() async {
        guard let voiceConsentID, let client else { return }
        do {
            try await client.revokeConsent(voiceConsentID)
            self.voiceConsentID = nil
            voiceProfileReady = false
            if let voiceSampleURL { try? FileManager.default.removeItem(at: voiceSampleURL) }
            voiceSampleURL = nil
            UserDefaults.standard.removeObject(forKey: "pending-voice-sample")
            UserDefaults.standard.removeObject(forKey: "pending-voice-transcript")
        } catch { errorMessage = "声音授权未能撤销：\(error.localizedDescription)" }
    }

    func playTwinVoice() async {
        guard let pairing, let client, let twinAnswer, !twinAnswer.stale else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let asset = try await client.createSpeech(subjectID: pairing.subjectID, answerID: twinAnswer.id)
            let audio = try await client.speechAudio(subjectID: pairing.subjectID, assetID: asset.asset_id)
            try beginPlayback(AVAudioPlayer(data: audio), identity: "twin-\(twinAnswer.id)")
        } catch { errorMessage = "个人声音暂时无法播放：\(error.localizedDescription)" }
    }

    func startCalibration() async {
        guard let pairing, let client, let cloudConsentID,
              let twinAnswer, !twinAnswer.stale, twinAnswer.response_type != "UNKNOWN" else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            calibrationRun = try await client.startCalibration(
                subjectID: pairing.subjectID, answerID: twinAnswer.id, cloudConsentID: cloudConsentID)
        } catch { errorMessage = "暂时无法锁定 Twin 回答：\(error.localizedDescription)" }
    }

    func completeCalibration(_ calibrationID: String) async {
        guard let pairing, let client, let cloudConsentID else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            calibrationRun = try await client.completeCalibration(
                subjectID: pairing.subjectID, calibrationID: calibrationID,
                cloudConsentID: cloudConsentID)
        } catch { errorMessage = "录音已保存，校准比较可稍后重试：\(error.localizedDescription)" }
    }
}

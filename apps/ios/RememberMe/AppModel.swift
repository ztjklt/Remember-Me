import Foundation
import AVFoundation
import SwiftUI

struct RecordingDraft: Codable, Identifiable {
    let id: String
    let fileURL: URL
    let recordedAt: Date
    let durationMS: Int
    let questionID: String?
    let consentConfirmedAt: Date
}

@MainActor
final class AppModel: ObservableObject {
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

    private var recorder: AVAudioRecorder?
    private var player: AVAudioPlayer?
    private var timer: Timer?
    private var startedAt: Date?
    private var accumulated: TimeInterval = 0

    init() {
        if let data = UserDefaults.standard.data(forKey: "pending-recording") {
            draft = try? JSONDecoder().decode(RecordingDraft.self, from: data)
            if let pending = draft, !FileManager.default.fileExists(atPath: pending.fileURL.path) {
                self.draft = nil
            }
        }
        episodeID = UserDefaults.standard.string(forKey: "pending-episode")
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
        pairingServer = value("server")
        pairingCode = value("code")
        pairingFingerprint = value("sha256")
    }

    func connect() async {
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
            pairing = connected
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
            memories = try await nextMemories
            episodes = try await nextEpisodes
            let snapshot = try await nextModel
            domains = snapshot.domains
            modelVersion = snapshot.version
            questions = try await nextQuestions
            errorMessage = nil
        } catch { errorMessage = error.localizedDescription }
    }

    func startRecording(questionID: String? = nil) async {
        errorMessage = nil
        transcriptDraft = ""
        isTranscriptReviewReady = false
        let granted = await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard granted else {
            errorMessage = "麦克风权限已拒绝。请在系统设置中允许拾光使用麦克风，然后再试。"
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
                    if self.isPaused {
                        self.meterLevels.removeFirst()
                        self.meterLevels.append(0.16)
                    } else if let recorder = self.recorder {
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
                                    consentConfirmedAt: draft.consentConfirmedAt)
        if let data = try? JSONEncoder().encode(self.draft) {
            UserDefaults.standard.set(data, forKey: "pending-recording")
        }
    }

    func togglePlayback() {
        guard let draft else { return }
        if player?.isPlaying == true {
            player?.stop(); isPlaying = false; return
        }
        do {
            player = try AVAudioPlayer(contentsOf: draft.fileURL)
            player?.play()
            isPlaying = true
        } catch { errorMessage = "本地录音无法播放：\(error.localizedDescription)" }
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
                    UserDefaults.standard.removeObject(forKey: "pending-recording")
                    UserDefaults.standard.removeObject(forKey: "pending-episode")
                    draft = nil
                    self.episodeID = nil
                    isTranscriptReviewReady = false
                    transcriptDraft = ""
                    await refresh()
                    return
                }
                if status.status == "failed" {
                    processingStatus = "failed"
                    errorMessage = "处理失败：\(status.error_message ?? status.error_code ?? "请稍后重试")。原录音仍保存在手机和本机服务里。"
                    return
                }
                let review = try await client.transcriptReview(episodeID)
                if review.state == "reviewing", let text = review.transcript {
                    if !isTranscriptReviewReady { transcriptDraft = text }
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

    func correct(_ memory: MemoryRecord, to content: String) async {
        guard let pairing, let client else { return }
        do { try await client.correct(subjectID: pairing.subjectID, memoryID: memory.id, content: content); await refresh() }
        catch { errorMessage = error.localizedDescription }
    }
    func delete(_ memory: MemoryRecord) async {
        guard let pairing, let client else { return }
        do { try await client.delete(subjectID: pairing.subjectID, memoryID: memory.id); await refresh() }
        catch { errorMessage = error.localizedDescription }
    }

    func playOriginal(_ memory: MemoryRecord) async {
        await playOriginal(episodeID: memory.episode_id)
    }

    func playOriginal(episodeID: String) async {
        guard let client else { return }
        do {
            let data = try await client.audio(episodeID)
            player?.stop()
            player = try AVAudioPlayer(data: data)
            player?.play()
            isPlaying = true
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
}

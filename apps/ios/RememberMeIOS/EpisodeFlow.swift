import Foundation

@MainActor
final class EpisodeFlow: ObservableObject {
    @Published var settings = SettingsStore.load()
    @Published private(set) var lastEpisodeID: String?
    @Published private(set) var stage = "idle"
    @Published private(set) var memories: [MemoryItem] = []
    @Published private(set) var modelVersion: String?
    @Published private(set) var isBusy = false
    @Published var message: String?

    private let api = EpisodeAPI()

    init() {
        lastEpisodeID = UserDefaults.standard.string(forKey: "lastEpisodeID")
    }

    func saveSettings() {
        do {
            guard settings.validatedURL != nil else { throw EpisodeAPIError.invalidServerURL }
            try SettingsStore.save(settings)
            settings = SettingsStore.load()
            message = "连接设置已保存。令牌仅保存在本机钥匙串。"
        } catch {
            message = error.localizedDescription
        }
    }

    func grantRecordingConsent() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let consent = try await api.grantRecordingConsent(settings: settings)
            guard consent.status == "granted" else { throw EpisodeAPIError.invalidResponse }
            settings.recordingConsentID = consent.consentId
            try SettingsStore.save(settings)
            message = "录音同意已登记。撤销同意后请勿继续上传。"
        } catch {
            message = error.localizedDescription
        }
    }

    func uploadAndProcess(fileURL: URL?, recordedAt: Date?) async {
        guard !isBusy else { return }
        guard let fileURL, let recordedAt else {
            message = "请先录音并保存。"
            return
        }
        guard settings.isReady else {
            message = "请先在设置中填写 Backend、Actor 令牌、Subject 和录音同意。"
            return
        }
        isBusy = true
        defer { isBusy = false }
        message = nil
        stage = "uploading"
        do {
            let key = "ios-\(fileURL.deletingPathExtension().lastPathComponent)"
            let created = try await api.upload(
                fileURL: fileURL, recordedAt: recordedAt,
                idempotencyKey: key, settings: settings
            )
            guard !created.episodeId.isEmpty else { throw EpisodeAPIError.invalidResponse }
            lastEpisodeID = created.episodeId
            UserDefaults.standard.set(created.episodeId, forKey: "lastEpisodeID")
            try await pollUntilReady(episodeID: created.episodeId)
        } catch {
            stage = "failed"
            message = error.localizedDescription
        }
    }

    func refreshLastEpisode() async {
        guard !isBusy, let lastEpisodeID else { return }
        isBusy = true
        defer { isBusy = false }
        message = nil
        do { try await pollUntilReady(episodeID: lastEpisodeID) }
        catch {
            stage = "failed"
            message = error.localizedDescription
        }
    }

    private func pollUntilReady(episodeID: String) async throws {
        let deadline = Date().addingTimeInterval(180)
        while Date() < deadline {
            try Task.checkCancellation()
            let response = try await api.status(episodeID: episodeID, settings: settings)
            guard response.episodeId == episodeID else { throw EpisodeAPIError.invalidResponse }
            stage = response.status
            if response.status == "failed" {
                message = "\(response.errorCode ?? "PROCESSING_FAILED")：\(response.errorMessage ?? "处理失败；本机录音仍保留。")"
                return
            }
            if response.status == "ready" {
                let result = try await api.result(episodeID: episodeID, settings: settings)
                guard result.episodeId == episodeID, result.status == "ready" else {
                    throw EpisodeAPIError.invalidResponse
                }
                memories = result.memoryItems
                modelVersion = result.modelVersion
                message = memories.isEmpty ? "处理完成，但没有提取出 Memory。" : "已收到同一 Episode 的 \(memories.count) 条 Memory。"
                return
            }
            try await Task.sleep(nanoseconds: 2_000_000_000)
        }
        message = "处理仍在继续。请稍后用 Episode ID 刷新状态；录音已保存在本机。"
    }
}

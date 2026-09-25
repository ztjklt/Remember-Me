import Foundation

@MainActor
final class EpisodeFlow: ObservableObject {
    @Published var settings = SettingsStore.load()
    @Published private(set) var lastEpisodeID: String?
    @Published private(set) var stage = "idle"
    @Published private(set) var memories: [MemoryItem] = []
    @Published private(set) var subjectMemories: [SubjectMemory] = []
    @Published private(set) var domainCounts: [String: Int] = [:]
    @Published private(set) var twinAnswer: TwinAnswer?
    @Published private(set) var calibration: CalibrationRecord?
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

    func grantCloudTwinConsent() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let consent = try await api.grantCloudTwinConsent(settings: settings)
            guard consent.status == "granted" else { throw EpisodeAPIError.invalidResponse }
            settings.cloudTwinConsentID = consent.consentId
            try SettingsStore.save(settings)
            message = "Cloud Twin 同意已登记，与录音及 Voice 同意分开。"
        } catch {
            message = error.localizedDescription
        }
    }

    func loadSubjectMemories() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await api.memories(settings: settings)
            guard result.subjectId == settings.subjectID else { throw EpisodeAPIError.invalidResponse }
            subjectMemories = result.items
            domainCounts = result.domainCounts
            message = "已读取 \(result.items.count) 条有来源的 Memory。"
        } catch {
            message = error.localizedDescription
        }
    }

    func correctMemory(_ id: String, proposedContent: String) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await api.correctMemory(id: id, proposedContent: proposedContent, settings: settings)
            try await refreshMemoryViews()
            twinAnswer = nil
            message = "纠错建议已记录；该原始说法已退出 Twin 引用。"
        } catch {
            message = error.localizedDescription
        }
    }

    func removeMemoryCorrection(_ id: String) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await api.removeCorrection(id: id, settings: settings)
            try await refreshMemoryViews()
            twinAnswer = nil
            message = "纠错建议已撤回。"
        } catch {
            message = error.localizedDescription
        }
    }

    func deleteMemory(_ id: String) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await api.deleteMemory(id: id, settings: settings)
            try await refreshMemoryViews()
            twinAnswer = nil
            message = "这条 Memory 已从结果与 Twin 检索中删除；原始 Episode 仍保留。"
        } catch {
            message = error.localizedDescription
        }
    }

    private func refreshMemoryViews() async throws {
        let result = try await api.memories(settings: settings)
        guard result.subjectId == settings.subjectID else { throw EpisodeAPIError.invalidResponse }
        subjectMemories = result.items
        domainCounts = result.domainCounts
        if let lastEpisodeID {
            if let episode = try? await api.result(episodeID: lastEpisodeID, settings: settings) {
                memories = episode.memoryItems
            }
        }
    }

    func askTwin(_ question: String) async {
        guard !isBusy else { return }
        isBusy = true
        twinAnswer = nil
        defer { isBusy = false }
        do {
            let response = try await api.twin(question: question, settings: settings)
            guard response.subjectId == settings.subjectID, response.question == question else {
                throw EpisodeAPIError.invalidResponse
            }
            twinAnswer = response
            message = nil
        } catch {
            message = error.localizedDescription
        }
    }

    func loadLatestCalibration() async {
        guard !isBusy, !settings.subjectID.isEmpty, !settings.token.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            calibration = try await api.calibrations(settings: settings).first
        } catch {
            message = error.localizedDescription
        }
    }

    func startCalibration(_ question: String) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            calibration = try await api.startCalibration(question: question, settings: settings)
            message = "Twin 回答已锁定。现在请填写人的真实回答和差异。"
        } catch {
            message = error.localizedDescription
        }
    }

    func submitCalibration(humanAnswer: String, gaps: CalibrationGaps) async {
        guard !isBusy, let calibration else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            self.calibration = try await api.submitCalibration(
                id: calibration.calibrationId, humanAnswer: humanAnswer,
                gaps: gaps, settings: settings
            )
            message = "校准反馈已保存，按 Actor 提交记录；不会自动改写本人事实。"
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
                if let acrossEpisodes = try? await api.memories(settings: settings),
                   acrossEpisodes.subjectId == settings.subjectID {
                    subjectMemories = acrossEpisodes.items
                    domainCounts = acrossEpisodes.domainCounts
                }
                return
            }
            try await Task.sleep(nanoseconds: 2_000_000_000)
        }
        message = "处理仍在继续。请稍后用 Episode ID 刷新状态；录音已保存在本机。"
    }
}

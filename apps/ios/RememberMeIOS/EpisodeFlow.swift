import Foundation

@MainActor
final class EpisodeFlow: ObservableObject {
    @Published var settings = SettingsStore.load()
    @Published private(set) var accountEmail = SettingsStore.email
    @Published private(set) var episodeSummaries: [EpisodeSummary] = []
    @Published private(set) var transcripts: [String: String] = [:]
    @Published private(set) var pendingCaptureURL: URL?
    @Published private(set) var pendingRecordedAt: Date?
    @Published private(set) var pendingUploadFailed = false
    @Published private(set) var lastEpisodeID: String?
    @Published private(set) var stage = "idle"
    @Published private(set) var memories: [MemoryItem] = []
    @Published private(set) var subjectMemories: [SubjectMemory] = []
    @Published private(set) var domainCounts: [String: Int] = [:]
    @Published private(set) var personModel: PersonModelPreview?
    @Published private(set) var memoryGraph: MemoryGraph?
    @Published private(set) var capturePlan: CapturePlan?
    @Published private(set) var twinAnswer: TwinAnswer?
    @Published private(set) var calibration: CalibrationRecord?
    @Published private(set) var legacyGrant: LegacyGrantRecord?
    @Published private(set) var legacyAudit: [LegacyAuditRecord] = []
    @Published private(set) var recipientMemories: [SubjectMemory] = []
    @Published private(set) var modelVersion: String?
    @Published private(set) var isBusy = false
    @Published private(set) var canRetryAccountConnection = false
    @Published var message: String?

    private let api: EpisodeAPI
    private var identityRevision = 0
    private var pollingTasks: [String: Task<Void, Never>] = [:]

    var isAuthenticated: Bool {
        !accountEmail.isEmpty && !SettingsStore.refreshToken.isEmpty
    }

    init(api: EpisodeAPI = EpisodeAPI()) {
        self.api = api
        restoreScopedState()
    }

    func requestLoginCode(email: String) async {
        guard !isBusy else { return }
        guard let base = settings.validatedURL else { message = "请先设置可访问的服务地址。"; return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await api.startEmail(email, baseURL: base)
            message = "验证码已发送到邮箱。"
        } catch { message = error.localizedDescription }
    }

    func verifyLogin(email: String, code: String) async {
        guard !isBusy else { return }
        guard let base = settings.validatedURL else { message = "请先设置服务地址。"; return }
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await api.verifyEmail(email, code: code, baseURL: base)
            try SettingsStore.saveAccount(
                email: result.email, accessToken: result.accessToken,
                refreshToken: result.refreshToken, subjectID: result.subjectId
            )
            settings = SettingsStore.load()
            accountEmail = result.email
            identityRevision += 1
            clearScopedState()
            restoreScopedState()
            message = nil
            await loadCurrentConsents()
        } catch { message = error.localizedDescription }
    }

    func restoreAccount() async {
        guard !isBusy, isAuthenticated, let base = settings.validatedURL else { return }
        let revision = identityRevision
        let refreshToken = SettingsStore.refreshToken
        isBusy = true
        defer { if revision == identityRevision { isBusy = false } }
        do {
            let result = try await api.refreshAccount(baseURL: base, refreshToken: refreshToken)
            guard revision == identityRevision else { return }
            try SettingsStore.saveAccount(
                email: result.email, accessToken: result.accessToken,
                refreshToken: result.refreshToken, subjectID: result.subjectId
            )
            settings = SettingsStore.load()
            accountEmail = result.email
            restoreScopedState()
            await loadCurrentConsents()
            guard revision == identityRevision else { return }
            canRetryAccountConnection = false
            message = nil
        } catch {
            guard revision == identityRevision else { return }
            let failure = error as NSError
            if case EpisodeAPIError.http(let code, _) = error, code == 401 {
                try? SettingsStore.clearAccount()
                settings = SettingsStore.load()
                accountEmail = ""
                identityRevision += 1
                clearScopedState()
                isBusy = false
                canRetryAccountConnection = false
                message = "登录已过期，请重新登录。"
            } else if failure.domain == NSURLErrorDomain && failure.code == NSURLErrorNotConnectedToInternet {
                canRetryAccountConnection = true
                message = "无法连接服务。请检查 Wi-Fi 或蜂窝网络；如果使用局域网服务，请在 iPhone 设置中允许 Remember Me 使用本地网络，然后重试。"
            } else if failure.domain == NSURLErrorDomain {
                canRetryAccountConnection = true
                message = "暂时无法连接服务，请检查网络后重试。本机录音已保留。"
            } else if case EpisodeAPIError.http(let code, _) = error, code >= 500 {
                canRetryAccountConnection = true
                message = "服务暂时不可用，请稍后重试。本机录音已保留。"
            } else {
                canRetryAccountConnection = false
                message = error.localizedDescription
            }
        }
    }

    func claimLegacy(token: String, subjectID: String) async {
        guard !isBusy, isAuthenticated else { return }
        let revision = identityRevision
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await api.claimLegacy(token: token, subjectID: subjectID, settings: settings)
            guard revision == identityRevision else { return }
            try SettingsStore.saveAccount(
                email: result.email, accessToken: result.accessToken,
                refreshToken: result.refreshToken, subjectID: result.subjectId
            )
            settings = SettingsStore.load()
            identityRevision += 1
            clearScopedState()
            restoreScopedState()
            await loadCurrentConsents()
            await loadEpisodes()
            message = "原有录音和记忆已迁入账号。"
        } catch { if revision == identityRevision { message = error.localizedDescription } }
    }

    func signOut() async {
        let previousSettings = settings
        let wasAuthenticated = isAuthenticated
        identityRevision += 1
        isBusy = false
        canRetryAccountConnection = false
        do {
            try SettingsStore.clearAccount()
            message = nil
        } catch { message = error.localizedDescription }
        settings = SettingsStore.load()
        accountEmail = SettingsStore.email
        clearScopedState()
        if wasAuthenticated { try? await api.logout(settings: previousSettings) }
    }

    private func loadCurrentConsents() async {
        guard isAuthenticated else { return }
        let revision = identityRevision
        if let consents = try? await api.consents(settings: settings) {
            guard revision == identityRevision else { return }
            settings.recordingConsentID = consents.first { $0.scope == "RECORDING" && $0.status == "granted" }?.consentId ?? ""
            settings.cloudTwinConsentID = consents.first { $0.scope == "CLOUD_TWIN" && $0.status == "granted" }?.consentId ?? ""
            settings.voiceConsentID = consents.first { $0.scope == "VOICE" && $0.status == "granted" }?.consentId ?? ""
            settings.handoverConsentID = consents.first { $0.scope == "DIGITAL_HANDOVER" && $0.status == "granted" }?.consentId ?? ""
            try? SettingsStore.save(settings)
        }
    }

    func registerPendingCapture(fileURL: URL, recordedAt: Date) {
        pendingCaptureURL = fileURL
        pendingRecordedAt = recordedAt
        pendingUploadFailed = false
        UserDefaults.standard.set(fileURL.path, forKey: scopedKey("pendingCapturePath"))
        UserDefaults.standard.set(recordedAt, forKey: scopedKey("pendingCaptureDate"))
    }

    private func scopedKey(_ name: String) -> String { "\(name):\(settings.subjectID)" }

    private func restoreScopedState() {
        guard !settings.subjectID.isEmpty else { return }
        let defaults = UserDefaults.standard
        lastEpisodeID = defaults.string(forKey: scopedKey("lastEpisodeID"))
        if let path = defaults.string(forKey: scopedKey("pendingCapturePath")),
           FileManager.default.fileExists(atPath: path) {
            pendingCaptureURL = URL(fileURLWithPath: path)
            pendingRecordedAt = defaults.object(forKey: scopedKey("pendingCaptureDate")) as? Date
        }
    }

    private func clearScopedState() {
        for task in pollingTasks.values { task.cancel() }
        pollingTasks.removeAll()
        episodeSummaries = []
        transcripts = [:]
        pendingCaptureURL = nil
        pendingRecordedAt = nil
        pendingUploadFailed = false
        lastEpisodeID = nil
        stage = "idle"
        memories = []
        subjectMemories = []
        domainCounts = [:]
        personModel = nil
        memoryGraph = nil
        capturePlan = nil
        twinAnswer = nil
        calibration = nil
        legacyGrant = nil
        legacyAudit = []
        recipientMemories = []
        modelVersion = nil
    }

    func loadEpisodes() async {
        guard isAuthenticated else { return }
        let revision = identityRevision
        do {
            let loaded = try await api.episodes(settings: settings)
            guard revision == identityRevision else { return }
            episodeSummaries = loaded
            for item in loaded.prefix(3) where item.status != "ready" && item.status != "failed" {
                startPolling(episodeID: item.episodeId)
            }
            for item in loaded where item.hasTranscript && transcripts[item.episodeId] == nil {
                if let text = try? await api.transcript(episodeID: item.episodeId, settings: settings) {
                    guard revision == identityRevision else { return }
                    transcripts[item.episodeId] = text.transcript
                }
            }
        } catch { if revision == identityRevision { message = error.localizedDescription } }
    }

    func refreshEpisode(_ id: String) async {
        let revision = identityRevision
        if let text = try? await api.transcript(episodeID: id, settings: settings) {
            guard revision == identityRevision else { return }
            transcripts[id] = text.transcript
        }
        await loadEpisodes()
        if episodeSummaries.first(where: { $0.episodeId == id })?.status == "ready" {
            await loadSubjectMemories()
        }
    }

    func retryProcessing(_ id: String) async {
        guard !isBusy else { return }
        let revision = identityRevision
        isBusy = true
        defer { isBusy = false }
        do {
            let response = try await api.retryProcessing(episodeID: id, settings: settings)
            guard revision == identityRevision else { return }
            guard response.episodeId == id, response.status != "failed" else {
                throw EpisodeAPIError.invalidResponse
            }
            stage = response.status
            message = nil
            await loadEpisodes()
            startPolling(episodeID: id)
        } catch {
            guard revision == identityRevision else { return }
            stage = "failed"
            message = error.localizedDescription
        }
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
        let revision = identityRevision
        isBusy = true
        defer { isBusy = false }
        do {
            let consent = try await api.grantRecordingConsent(settings: settings)
            guard revision == identityRevision else { return }
            guard consent.status == "granted" else { throw EpisodeAPIError.invalidResponse }
            settings.recordingConsentID = consent.consentId
            try SettingsStore.save(settings)
            message = "录音同意已登记。撤销同意后请勿继续上传。"
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
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

    func grantHandoverConsent() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let consent = try await api.grantHandoverConsent(settings: settings)
            guard consent.status == "granted" else { throw EpisodeAPIError.invalidResponse }
            settings.handoverConsentID = consent.consentId
            try SettingsStore.save(settings)
            message = "数字交接同意已登记；仅用于明确授权的预演。"
        } catch {
            message = error.localizedDescription
        }
    }

    func grantVoiceConsent() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let consent = try await api.grantVoiceConsent(settings: settings)
            guard consent.status == "granted" else { throw EpisodeAPIError.invalidResponse }
            settings.voiceConsentID = consent.consentId
            try SettingsStore.save(settings)
            message = "Voice 同意已单独登记。系统朗读仍不是本人声音克隆。"
        } catch {
            message = error.localizedDescription
        }
    }

    func authorizeVoicePlayback() async -> Bool {
        guard !isBusy else { return false }
        isBusy = true
        defer { isBusy = false }
        do {
            try await api.authorizeVoice(settings: settings)
            return true
        } catch {
            message = error.localizedDescription
            return false
        }
    }

    func createLegacyGrant(recipientActorID: String, domains: [String]) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            legacyGrant = try await api.createLegacyGrant(
                recipientActorID: recipientActorID, domains: domains, settings: settings
            )
            if let legacyGrant {
                legacyAudit = (try? await api.legacyAudit(id: legacyGrant.grantId, settings: settings)) ?? []
            }
            message = "交接草稿已保存；接收者目前无法读取。"
        } catch {
            message = error.localizedDescription
        }
    }

    func loadLegacyGrant() async {
        guard !isBusy, !settings.subjectID.isEmpty, !settings.token.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            legacyGrant = try await api.handoverGrants(settings: settings).first
            if let legacyGrant {
                legacyAudit = (try? await api.legacyAudit(id: legacyGrant.grantId, settings: settings)) ?? []
            } else {
                legacyAudit = []
            }
        } catch {
            message = error.localizedDescription
        }
    }

    func activateLegacyPreview() async {
        guard !isBusy, let legacyGrant else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            self.legacyGrant = try await api.activateLegacyPreview(
                id: legacyGrant.grantId, settings: settings
            )
            legacyAudit = (try? await api.legacyAudit(id: legacyGrant.grantId, settings: settings)) ?? []
            message = "接收者预演已激活，并冻结可见 Memory 清单。此操作不是正式 Legacy 转承。"
        } catch {
            message = error.localizedDescription
        }
    }

    func revokeLegacyPreview() async {
        guard !isBusy, let legacyGrant else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            self.legacyGrant = try await api.revokeLegacyGrant(
                id: legacyGrant.grantId, settings: settings
            )
            legacyAudit = (try? await api.legacyAudit(id: legacyGrant.grantId, settings: settings)) ?? []
            message = "交接授权已撤销。"
        } catch {
            message = error.localizedDescription
        }
    }

    func loadRecipientMemories() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await api.legacyRecipientMemories(settings: settings)
            guard result.subjectId == settings.subjectID, result.mode == "PREVIEW" else {
                throw EpisodeAPIError.invalidResponse
            }
            recipientMemories = result.items
            message = "已按接收者授权范围读取 \(result.items.count) 条预演 Memory。"
        } catch {
            recipientMemories = []
            message = error.localizedDescription
        }
    }

    func loadSubjectMemories() async {
        guard !isBusy else { return }
        let revision = identityRevision
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await api.memories(settings: settings)
            guard revision == identityRevision else { return }
            guard result.subjectId == settings.subjectID else { throw EpisodeAPIError.invalidResponse }
            subjectMemories = result.items
            domainCounts = result.domainCounts
            if let preview = try? await api.personModel(settings: settings),
               preview.subjectId == settings.subjectID {
                guard revision == identityRevision else { return }
                personModel = preview
            }
            if let graph = try? await api.memoryGraph(settings: settings),
               graph.subjectId == settings.subjectID {
                guard revision == identityRevision else { return }
                memoryGraph = graph
            }
            message = "已读取 \(result.items.count) 条有来源的 Memory。"
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
        }
    }

    func loadCapturePlan() async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let plan = try await api.capturePlan(settings: settings)
            guard plan.subjectId == settings.subjectID else { throw EpisodeAPIError.invalidResponse }
            capturePlan = plan
            message = "已按当前记忆覆盖与校准差异刷新引导问题。"
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
        personModel = nil
        memoryGraph = nil
        if let preview = try? await api.personModel(settings: settings),
           preview.subjectId == settings.subjectID {
            personModel = preview
        }
        if let graph = try? await api.memoryGraph(settings: settings),
           graph.subjectId == settings.subjectID {
            memoryGraph = graph
        }
        if let lastEpisodeID {
            if let episode = try? await api.result(episodeID: lastEpisodeID, settings: settings) {
                memories = episode.memoryItems
            }
        }
    }

    func askTwin(_ question: String) async {
        guard !isBusy else { return }
        let revision = identityRevision
        let requestSettings = settings
        isBusy = true
        twinAnswer = nil
        defer { if revision == identityRevision { isBusy = false } }
        do {
            let response = try await api.twin(question: question, settings: requestSettings)
            guard revision == identityRevision else { return }
            guard response.subjectId == requestSettings.subjectID, response.question == question else {
                throw EpisodeAPIError.invalidResponse
            }
            twinAnswer = response
            message = nil
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
        }
    }

    func loadLatestCalibration() async {
        guard !isBusy, !settings.subjectID.isEmpty, !settings.token.isEmpty else { return }
        let revision = identityRevision
        let requestSettings = settings
        isBusy = true
        defer { if revision == identityRevision { isBusy = false } }
        do {
            let latest = try await api.calibrations(settings: requestSettings).first
            guard revision == identityRevision else { return }
            calibration = latest
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
        }
    }

    func startCalibration(_ question: String) async {
        guard !isBusy else { return }
        let revision = identityRevision
        let requestSettings = settings
        isBusy = true
        defer { if revision == identityRevision { isBusy = false } }
        do {
            let created = try await api.startCalibration(question: question, settings: requestSettings)
            guard revision == identityRevision else { return }
            calibration = created
            message = "Twin 回答已锁定。现在请填写人的真实回答和差异。"
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
        }
    }

    func submitCalibration(humanAnswer: String, gaps: CalibrationGaps) async {
        guard !isBusy, let calibration else { return }
        let revision = identityRevision
        let requestSettings = settings
        isBusy = true
        defer { if revision == identityRevision { isBusy = false } }
        do {
            let submitted = try await api.submitCalibration(
                id: calibration.calibrationId, humanAnswer: humanAnswer,
                gaps: gaps, settings: requestSettings
            )
            guard revision == identityRevision else { return }
            self.calibration = submitted
            message = "回答已锁定。请查看差异分析，再决定是否用于更新模型。"
            if let plan = try? await api.capturePlan(settings: requestSettings),
               revision == identityRevision, plan.subjectId == requestSettings.subjectID {
                capturePlan = plan
            }
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
        }
    }

    func assessCalibration() async {
        guard !isBusy, let calibration, calibration.humanAnswer != nil else { return }
        let revision = identityRevision
        let requestSettings = settings
        isBusy = true
        defer { if revision == identityRevision { isBusy = false } }
        do {
            let assessed = try await api.assessCalibration(
                id: calibration.calibrationId, settings: requestSettings
            )
            guard revision == identityRevision else { return }
            self.calibration = assessed
            message = "差异分析已保存。确认后才会用于更新模型。"
            if let plan = try? await api.capturePlan(settings: requestSettings),
               revision == identityRevision, plan.subjectId == requestSettings.subjectID {
                capturePlan = plan
            }
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
        }
    }

    func confirmCalibration() async {
        guard !isBusy, let calibration, calibration.aiAssessment != nil,
              calibration.confirmedAt == nil else { return }
        let revision = identityRevision
        let requestSettings = settings
        isBusy = true
        defer { if revision == identityRevision { isBusy = false } }
        do {
            let confirmed = try await api.confirmCalibration(
                id: calibration.calibrationId, settings: requestSettings
            )
            guard revision == identityRevision else { return }
            self.calibration = confirmed
            if let preview = try? await api.personModel(settings: requestSettings),
               revision == identityRevision, preview.subjectId == requestSettings.subjectID {
                personModel = preview
            }
            if let plan = try? await api.capturePlan(settings: requestSettings),
               revision == identityRevision, plan.subjectId == requestSettings.subjectID {
                capturePlan = plan
            }
            guard revision == identityRevision else { return }
            message = "已确认差异，下一轮引导问题已更新。"
        } catch {
            if revision == identityRevision { message = error.localizedDescription }
        }
    }

    func uploadAndProcess(fileURL: URL?, recordedAt: Date?) async {
        guard let fileURL, let recordedAt else {
            message = "请先录音并保存。"
            return
        }
        guard !isBusy else {
            registerPendingCapture(fileURL: fileURL, recordedAt: recordedAt)
            pendingUploadFailed = true
            message = "录音已保存在本机，请稍后重试上传。"
            return
        }
        guard settings.isReady else {
            message = "请先在设置中填写 Backend、Actor 令牌、Subject 和录音同意。"
            return
        }
        let revision = identityRevision
        isBusy = true
        defer { isBusy = false }
        registerPendingCapture(fileURL: fileURL, recordedAt: recordedAt)
        message = nil
        stage = "uploading"
        pendingUploadFailed = false
        do {
            let key = "ios-\(fileURL.deletingPathExtension().lastPathComponent)"
            let created = try await api.upload(
                fileURL: fileURL, recordedAt: recordedAt,
                idempotencyKey: key, settings: settings
            )
            guard revision == identityRevision else { return }
            guard !created.episodeId.isEmpty else { throw EpisodeAPIError.invalidResponse }
            lastEpisodeID = created.episodeId
            UserDefaults.standard.set(created.episodeId, forKey: scopedKey("lastEpisodeID"))
            pendingCaptureURL = nil
            pendingRecordedAt = nil
            pendingUploadFailed = false
            UserDefaults.standard.removeObject(forKey: scopedKey("pendingCapturePath"))
            UserDefaults.standard.removeObject(forKey: scopedKey("pendingCaptureDate"))
            let loaded = try await api.episodes(settings: settings)
            guard revision == identityRevision else { return }
            episodeSummaries = loaded
            startPolling(episodeID: created.episodeId)
        } catch {
            guard revision == identityRevision else { return }
            stage = "failed"
            pendingUploadFailed = pendingCaptureURL != nil
            message = error.localizedDescription
            if lastEpisodeID != nil { await loadEpisodes() }
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

    private func startPolling(episodeID: String) {
        guard pollingTasks[episodeID] == nil else { return }
        let revision = identityRevision
        pollingTasks[episodeID] = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.pollingTasks[episodeID] = nil }
            do {
                try await self.pollUntilReady(episodeID: episodeID)
            } catch is CancellationError {
                return
            } catch {
                guard revision == self.identityRevision else { return }
                self.message = error.localizedDescription
                await self.loadEpisodes()
            }
        }
    }

    private func pollUntilReady(episodeID: String) async throws {
        let revision = identityRevision
        let deadline = Date().addingTimeInterval(180)
        while Date() < deadline {
            try Task.checkCancellation()
            let response = try await api.status(episodeID: episodeID, settings: settings)
            guard revision == identityRevision else { return }
            guard response.episodeId == episodeID else { throw EpisodeAPIError.invalidResponse }
            stage = response.status
            if transcripts[episodeID] == nil,
               let transcript = try? await api.transcript(episodeID: episodeID, settings: settings) {
                guard revision == identityRevision else { return }
                transcripts[episodeID] = transcript.transcript
            }
            if response.status == "failed" {
                let loaded = try? await api.episodes(settings: settings)
                guard revision == identityRevision else { return }
                episodeSummaries = loaded ?? episodeSummaries
                message = "\(response.errorCode ?? "PROCESSING_FAILED")：\(response.errorMessage ?? "处理失败；本机录音仍保留。")"
                return
            }
            if response.status == "ready" {
                let result = try await api.result(episodeID: episodeID, settings: settings)
                guard revision == identityRevision else { return }
                guard result.episodeId == episodeID, result.status == "ready" else {
                    throw EpisodeAPIError.invalidResponse
                }
                memories = result.memoryItems
                modelVersion = result.modelVersion
                let loaded = try? await api.episodes(settings: settings)
                guard revision == identityRevision else { return }
                episodeSummaries = loaded ?? episodeSummaries
                message = memories.isEmpty ? "处理完成，但没有提取出 Memory。" : "已收到同一 Episode 的 \(memories.count) 条 Memory。"
                if let acrossEpisodes = try? await api.memories(settings: settings),
                   acrossEpisodes.subjectId == settings.subjectID {
                    guard revision == identityRevision else { return }
                    subjectMemories = acrossEpisodes.items
                    domainCounts = acrossEpisodes.domainCounts
                    if let preview = try? await api.personModel(settings: settings),
                       preview.subjectId == settings.subjectID {
                        guard revision == identityRevision else { return }
                        personModel = preview
                    }
                    if let graph = try? await api.memoryGraph(settings: settings),
                       graph.subjectId == settings.subjectID {
                        guard revision == identityRevision else { return }
                        memoryGraph = graph
                    }
                }
                if let plan = try? await api.capturePlan(settings: settings),
                   plan.subjectId == settings.subjectID {
                    guard revision == identityRevision else { return }
                    capturePlan = plan
                }
                return
            }
            try await Task.sleep(nanoseconds: 2_000_000_000)
        }
        message = "处理仍在继续。请稍后用 Episode ID 刷新状态；录音已保存在本机。"
    }
}

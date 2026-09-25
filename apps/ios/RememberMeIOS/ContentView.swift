import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @EnvironmentObject private var capture: AudioCapture
    @State private var restoringAccount = true

    var body: some View {
        Group {
            if restoringAccount {
                ProgressView("Remember Me")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !flow.isAuthenticated {
                LoginScreen()
            } else if flow.settings.recordingConsentID.isEmpty {
                RecordingConsentScreen()
            } else {
                TabView {
                    CaptureView()
                        .tabItem { Label("记录", systemImage: "waveform") }
                    MemoriesView()
                        .tabItem { Label("记忆", systemImage: "books.vertical") }
                    TwinView()
                        .tabItem { Label("对话", systemImage: "bubble.left.and.bubble.right") }
                    ProfileScreen()
                        .tabItem { Label("我的", systemImage: "person.crop.circle") }
                }
            }
        }
        .task {
            await flow.restoreAccount()
            restoringAccount = false
        }
        .onChange(of: flow.isAuthenticated) { _, authenticated in
            if !authenticated { capture.clearSelection() }
        }
    }
}

private struct LoginScreen: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var email = ""
    @State private var code = ""
    @State private var codeRequested = false
    @State private var showServer = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Spacer(minLength: 90)
                    Text("Remember Me")
                        .font(.system(size: 42, weight: .semibold, design: .rounded))
                    Text("留下你想记住的生活")
                        .font(.title3).foregroundStyle(.secondary)
                    TextField("邮箱地址", text: $email)
                        .textContentType(.emailAddress).keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .textFieldStyle(.roundedBorder)
                        .onChange(of: email) { _, _ in
                            codeRequested = false
                            code = ""
                        }
                    if codeRequested {
                        TextField("六位验证码", text: $code)
                            .keyboardType(.numberPad).textContentType(.oneTimeCode)
                            .textFieldStyle(.roundedBorder)
                        Button("登录或创建账号") {
                            Task { await flow.verifyLogin(email: email, code: code) }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(flow.isBusy || code.count != 6)
                        Button("重新发送验证码") { Task { await flow.requestLoginCode(email: email) } }
                            .disabled(flow.isBusy)
                    } else {
                        Button("获取验证码") {
                            Task {
                                await flow.requestLoginCode(email: email)
                                if flow.message == "验证码已发送到邮箱。" { codeRequested = true }
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(flow.isBusy || !email.contains("@"))
                    }
                    if flow.isBusy { ProgressView() }
                    if let message = flow.message { Text(message).font(.footnote).foregroundStyle(.secondary) }
                    #if DEBUG
                    if let importError = UserDefaults.standard.string(forKey: "developmentImportError") {
                        Text("本地账号导入失败：\(importError)")
                            .font(.footnote).foregroundStyle(.red)
                    }
                    #endif
                    DisclosureGroup("连接设置", isExpanded: $showServer) {
                        TextField("Backend 地址", text: $flow.settings.baseURL)
                            .keyboardType(.URL).textInputAutocapitalization(.never)
                            .autocorrectionDisabled().textFieldStyle(.roundedBorder)
                        Button("保存地址") { flow.saveSettings() }
                    }
                    .font(.footnote)
                    Spacer(minLength: 120)
                }
                .padding(28)
            }
            .background(Color(uiColor: .systemGroupedBackground))
        }
    }
}

private struct RecordingConsentScreen: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var agreed = false

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 22) {
                Text("Remember Me").font(.largeTitle.bold())
                Text("开始记录前，请确认你是被记录的本人。录音会上传处理，形成可查看和删除的记忆。")
                Toggle("我是本人，同意录音和上传处理", isOn: $agreed)
                Button("同意并开始记录") { Task { await flow.grantRecordingConsent() } }
                    .buttonStyle(.borderedProminent)
                    .disabled(!agreed || flow.isBusy)
                if let message = flow.message { Text(message).font(.footnote).foregroundStyle(.secondary) }
                Spacer()
            }
            .padding(28)
            .toolbar { Button("退出") { Task { await flow.signOut() } } }
        }
    }
}

private struct ProfileScreen: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var legacyToken = ""
    @State private var legacySubject = ""

    var body: some View {
        NavigationStack {
            List {
                Section {
                    LabeledContent("账号", value: flow.accountEmail)
                    Button("退出登录", role: .destructive) { Task { await flow.signOut() } }
                }
                Section("更多功能") {
                    NavigationLink("Twin 校准") { CalibrationScreen() }
                    NavigationLink("数字交接预演") { HandoverScreen() }
                    NavigationLink("连接与独立授权") { ConnectionView() }
                }
                #if DEBUG
                Section("开发者选项") {
                    DisclosureGroup("迁入已有开发数据") {
                    SecureField("原 Actor 令牌", text: $legacyToken)
                        .textInputAutocapitalization(.never)
                    TextField("原 Subject ID", text: $legacySubject)
                        .textInputAutocapitalization(.never)
                    Button("一次性认领") {
                        Task { await flow.claimLegacy(token: legacyToken, subjectID: legacySubject) }
                    }
                    .disabled(legacyToken.isEmpty || legacySubject.isEmpty || flow.isBusy)
                    Text("只能认领该令牌独占的 Subject；认领后原令牌失效。")
                        .font(.caption).foregroundStyle(.secondary)
                    }
                }
                #endif
                if let message = flow.message { Section { Text(message).font(.footnote) } }
            }
            .navigationTitle("我的")
        }
    }
}

private struct HandoverScreen: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var recipientActorID = ""
    @State private var selectedDomains: Set<String> = []
    @State private var showActivation = false

    private let domains = [
        "Identity", "Episodic Memory", "Relationships", "Preferences",
        "Values & Beliefs", "Decision Patterns", "Expression", "Unclassified"
    ]

    var body: some View {
        NavigationStack {
            Form {
                Section("数字交接预演") {
                    Text("仅供手动预演。当前没有 Subject 身份核验或正式 Legacy 激活证明。接收者只能看到激活时锁定、且被明确选择的 Memory 领域。")
                        .font(.footnote).foregroundStyle(.secondary)
                    TextField("接收者 Actor ID", text: $recipientActorID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    ForEach(domains, id: \.self) { domain in
                        Toggle(domain, isOn: Binding(
                            get: { selectedDomains.contains(domain) },
                            set: { enabled in
                                if enabled { selectedDomains.insert(domain) }
                                else { selectedDomains.remove(domain) }
                            }
                        ))
                    }
                    Button("创建交接草稿") {
                        Task {
                            await flow.createLegacyGrant(
                                recipientActorID: recipientActorID,
                                domains: domains.filter { selectedDomains.contains($0) }
                            )
                        }
                    }
                    .disabled(flow.isBusy || recipientActorID.isEmpty || selectedDomains.isEmpty)
                }
                if let grant = flow.legacyGrant {
                    Section("当前授权") {
                        LabeledContent("接收者", value: grant.recipientActorId)
                        LabeledContent("状态", value: grant.status)
                        LabeledContent("锁定 Memory", value: "\(grant.snapshotCount)")
                        if let revision = grant.baselineModelRevision {
                            LabeledContent("激活时模型修订", value: "r\(revision)")
                        }
                        Text(grant.allowedDomains.joined(separator: "、"))
                            .font(.caption).foregroundStyle(.secondary)
                        if grant.status == "DRAFT" {
                            Button("手动激活接收者预演") { showActivation = true }
                                .disabled(flow.isBusy)
                        }
                        if grant.status != "REVOKED" {
                            Button("撤销授权", role: .destructive) {
                                Task { await flow.revokeLegacyPreview() }
                            }
                            .disabled(flow.isBusy)
                        }
                    }
                }
                if !flow.legacyAudit.isEmpty {
                    Section("授权访问记录") {
                        ForEach(flow.legacyAudit) { entry in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(entry.action)
                                Text("Actor \(entry.actorId) · \(entry.occurredAt)")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                Section("以接收者身份查看") {
                    Button("读取我获授权的 Memory") {
                        Task { await flow.loadRecipientMemories() }
                    }
                    .disabled(flow.isBusy)
                    ForEach(flow.recipientMemories) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.content)
                            Text("\(item.domain) · Episode \(item.episodeId)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                if let message = flow.message {
                    Section { Text(message).font(.footnote) }
                }
            }
            .navigationTitle("数字交接")
            .toolbar {
                Button("刷新") { Task { await flow.loadLegacyGrant() } }
                    .disabled(flow.isBusy)
            }
            .confirmationDialog("确认手动激活预演？", isPresented: $showActivation) {
                Button("激活预演") { Task { await flow.activateLegacyPreview() } }
            } message: {
                Text("接收者将能读取激活时锁定的指定领域 Memory；这不是正式 Legacy 转承。")
            }
        }
    }
}

private struct CalibrationScreen: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var question = ""
    @State private var humanAnswer = ""
    @State private var gaps = CalibrationGaps()

    var body: some View {
        NavigationStack {
            Form {
                Section("先锁定 Twin") {
                    TextField("想校准的问题", text: $question, axis: .vertical)
                        .lineLimit(2...4)
                    Button("锁定当前 Twin 回答") {
                        Task { await flow.startCalibration(question) }
                    }
                    .disabled(flow.isBusy || question.trimmingCharacters(in: .whitespacesAndNewlines).count < 2)
                    Text("锁定后再填写人的回答；之后的 Memory 变化不会改写这次对照。")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if let record = flow.calibration {
                    Section("已锁定的 Twin 回答") {
                        Text(record.question).font(.headline)
                        Text(record.lockedAnswer)
                        LabeledContent("回答类型", value: record.responseType)
                        LabeledContent("证据数", value: "\(record.evidenceIds.count)")
                        if let version = record.modelVersion {
                            LabeledContent("模型版本", value: version)
                        }
                    }
                    Section("人的回答与差异") {
                        if let submitted = record.humanAnswer {
                            Text(submitted)
                            Text("已提交；这条记录不可覆盖。")
                                .font(.footnote).foregroundStyle(.secondary)
                        } else {
                            TextField("输入人的真实回答", text: $humanAnswer, axis: .vertical)
                                .lineLimit(3...8)
                            Toggle("决策不同", isOn: $gaps.decision)
                            Toggle("推理不同", isOn: $gaps.reasoning)
                            Toggle("价值优先级不同", isOn: $gaps.valuePriority)
                            Toggle("情绪反应不同", isOn: $gaps.emotionalReaction)
                            Toggle("表达方式不同", isOn: $gaps.expression)
                            Button("提交校准反馈") {
                                Task { await flow.submitCalibration(humanAnswer: humanAnswer, gaps: gaps) }
                            }
                            .disabled(flow.isBusy || humanAnswer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    }
                    if record.humanAnswer != nil {
                        Section("AI 差异分析 · 辅助判断") {
                            if let assessment = record.aiAssessment {
                                LabeledContent("整体", value: verdictLabel(assessment.overall))
                                assessmentRow("决策", assessment.decision)
                                assessmentRow("推理", assessment.reasoning)
                                assessmentRow("价值优先级", assessment.valuePriority)
                                assessmentRow("情绪反应", assessment.emotionalReaction)
                                assessmentRow("表达方式", assessment.expression)
                                Text("模型：\(assessment.modelVersion) · 规则：\(assessment.assessmentVersion)")
                                    .font(.caption).foregroundStyle(.secondary)
                            } else {
                                Button("运行 AI 差异分析（建议）") {
                                    Task { await flow.assessCalibration() }
                                }
                                .disabled(flow.isBusy)
                            }
                            Text("分析仅比较已锁定的 Twin 回答与本人回答。确认差异后才会更新个人模型。")
                                .font(.footnote).foregroundStyle(.secondary)
                            if record.aiAssessment != nil {
                                if record.confirmedAt == nil {
                                    Button("确认差异并更新个人模型") {
                                        Task { await flow.confirmCalibration() }
                                    }
                                    .disabled(flow.isBusy)
                                } else {
                                    Label("已确认并用于下一轮采集", systemImage: "checkmark.circle.fill")
                                        .foregroundStyle(.green)
                                }
                            }
                        }
                    }
                }
                if let message = flow.message {
                    Section { Text(message).font(.footnote) }
                }
            }
            .navigationTitle("Twin 校准")
            .task { await flow.loadLatestCalibration() }
        }
    }

    private func assessmentRow(_ title: String, _ dimension: CalibrationDimension) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            LabeledContent(title, value: verdictLabel(dimension.verdict))
            Text(dimension.rationale).font(.caption).foregroundStyle(.secondary)
        }
    }

    private func verdictLabel(_ verdict: String) -> String {
        switch verdict {
        case "MATCH": "一致"
        case "DIFFERENT": "有差异"
        default: "不确定"
        }
    }
}

private struct CaptureView: View {
    @EnvironmentObject private var capture: AudioCapture
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var showImporter = false
    @State private var showGuidance = false
    @State private var selectedQuestion: String?

    var body: some View {
        NavigationStack {
            ScrollViewReader { reader in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        if flow.episodeSummaries.isEmpty && flow.pendingCaptureURL == nil {
                            Text("说一段你想留下的事")
                                .font(.title3).foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, minHeight: 180)
                        }
                        ForEach(flow.episodeSummaries.reversed()) { item in
                            episodeBubble(item)
                                .id(item.episodeId)
                        }
                        if let pending = flow.pendingCaptureURL {
                            HStack {
                                VStack(alignment: .leading, spacing: 7) {
                                    Text("已采集").font(.headline)
                                    Text(flow.pendingUploadFailed ? "上传失败，录音仍在本机" : "正在上传，录音已保存在本机")
                                        .font(.subheadline).foregroundStyle(.secondary)
                                    if flow.pendingUploadFailed {
                                        Button("重试上传") {
                                            Task {
                                                await flow.uploadAndProcess(
                                                    fileURL: pending, recordedAt: flow.pendingRecordedAt
                                                )
                                            }
                                        }
                                        .disabled(flow.isBusy)
                                    }
                                }
                                .padding(14)
                                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 17))
                                Spacer(minLength: 30)
                            }
                        }
                        if let selectedQuestion {
                            Text("引导问题：\(selectedQuestion)")
                                .font(.subheadline).foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(16)
                }
                .onChange(of: flow.episodeSummaries.count) { _, _ in
                    if let id = flow.episodeSummaries.first?.episodeId {
                        withAnimation { reader.scrollTo(id, anchor: .bottom) }
                    }
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                composer
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .frame(maxWidth: .infinity)
                    .background(.regularMaterial)
            }
            .navigationTitle("Remember Me")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showGuidance = true
                        Task { await flow.loadCapturePlan() }
                    } label: {
                        Image(systemName: "sparkles")
                    }
                    .accessibilityLabel("引导式采集")
                }
            }
            .sheet(isPresented: $showGuidance) {
                NavigationStack {
                    List {
                        if let questions = flow.capturePlan?.questions, !questions.isEmpty {
                            ForEach(questions) { item in
                                Button {
                                    selectedQuestion = item.question
                                    showGuidance = false
                                } label: {
                                    Text(item.question)
                                        .foregroundStyle(.primary)
                                        .padding(.vertical, 5)
                                }
                            }
                        } else {
                            if flow.isBusy {
                                ProgressView("正在准备问题")
                            } else {
                                Text("暂时无法获取问题").foregroundStyle(.secondary)
                                Button("重试") { Task { await flow.loadCapturePlan() } }
                            }
                        }
                    }
                    .navigationTitle("引导式采集")
                    .toolbar {
                        Button("完成") { showGuidance = false }
                    }
                }
                .presentationDetents([.medium, .large])
            }
            .fileImporter(isPresented: $showImporter, allowedContentTypes: [.audio]) { result in
                switch result {
                case .success(let url):
                    if capture.importAudio(from: url),
                       let file = capture.fileURL, let date = capture.recordedAt {
                        flow.registerPendingCapture(fileURL: file, recordedAt: date)
                        Task { await flow.uploadAndProcess(fileURL: file, recordedAt: date) }
                    }
                case .failure(let error):
                    capture.message = "无法选择录音：\(error.localizedDescription)"
                }
            }
            .task {
                capture.restorePendingRecording(at: flow.pendingCaptureURL)
                await flow.loadEpisodes()
                await flow.loadSubjectMemories()
            }
        }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 4) {
        if let message = capture.message {
            Text(message).font(.footnote).foregroundStyle(.red)
        }
        if flow.pendingUploadFailed, let message = flow.message {
            Text(message).font(.footnote).foregroundStyle(.red)
        }
        HStack(spacing: 12) {
            Menu {
                Button("导入录音文件", systemImage: "square.and.arrow.down") {
                    showImporter = true
                }
                if capture.fileURL != nil && !capture.isRecording {
                    Button(capture.isPlaying ? "停止播放" : "播放最近录音",
                           systemImage: "play.circle") {
                        capture.playOrStop()
                    }
                }
            } label: {
                Image(systemName: "plus")
                    .font(.title3)
                    .frame(width: 40, height: 44)
            }
            .disabled(capture.isRecording)
            if capture.isRecording {
                Text(formatDuration(capture.elapsed))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(capture.isPaused ? .orange : .red)
                Button(capture.isPaused ? "继续" : "暂停") { capture.pauseOrResume() }
                    .font(.subheadline)
            } else {
                Text("轻点开始录音")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Button {
                if capture.isRecording {
                    capture.stop()
                    if let file = capture.fileURL, let date = capture.recordedAt {
                        flow.registerPendingCapture(fileURL: file, recordedAt: date)
                        Task { await flow.uploadAndProcess(fileURL: file, recordedAt: date) }
                    }
                } else {
                    Task { await capture.start() }
                }
            } label: {
                Image(systemName: capture.isRecording ? "stop.fill" : "mic.fill")
                    .font(.title3)
                    .foregroundStyle(.white)
                    .frame(width: 48, height: 48)
                    .background(capture.isRecording ? Color.red : Color.accentColor, in: Circle())
            }
            .accessibilityLabel(capture.isRecording ? "保存并转录录音" : "开始录音")
            .disabled((flow.isBusy || flow.pendingUploadFailed) && !capture.isRecording)
        }
        }
    }

    private func episodeBubble(_ item: EpisodeSummary) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("已采集").font(.headline)
                    Spacer()
                    Text(timeLabel(item.recordedAt))
                        .font(.caption2).foregroundStyle(.secondary)
                }
                if let transcript = flow.transcripts[item.episodeId] {
                    Text(transcript).textSelection(.enabled)
                } else if item.status == "failed" {
                    Text(item.errorMessage ?? "处理失败，录音仍已保存")
                        .foregroundStyle(.red)
                } else {
                    Text("正在转成文字…").foregroundStyle(.secondary)
                }
                if item.status == "ready" {
                    let related = flow.subjectMemories.filter { $0.episodeId == item.episodeId }
                    ForEach(related.prefix(2)) { memory in
                        Text("记住了：\(memory.content)")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                } else if item.hasTranscript {
                    Text("正在整理记忆…")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if item.status == "failed" {
                    Button("重新处理") { Task { await flow.retryProcessing(item.episodeId) } }
                        .font(.caption)
                        .disabled(flow.isBusy)
                } else if item.status != "ready" {
                    Button("刷新状态") { Task { await flow.refreshEpisode(item.episodeId) } }
                        .font(.caption)
                }
            }
            .padding(14)
            .frame(maxWidth: 330, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 17))
            Spacer(minLength: 30)
        }
    }

    private func formatDuration(_ seconds: TimeInterval) -> String {
        let whole = max(0, Int(seconds))
        return String(format: "%02d:%02d", whole / 60, whole % 60)
    }

    private func timeLabel(_ value: String) -> String {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        guard let date = fractional.date(from: value) ?? plain.date(from: value) else { return "" }
        let display = DateFormatter()
        display.locale = Locale(identifier: "zh_CN")
        display.dateFormat = "M月d日 HH:mm"
        return display.string(from: date)
    }
}

private struct MemoriesView: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var query = ""
    @State private var selectedMemoryID: String?
    @State private var correctionDraft = ""
    @State private var showCorrection = false
    @State private var showDeletion = false

    private var visible: [SubjectMemory] {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return flow.subjectMemories }
        return flow.subjectMemories.filter {
            $0.content.localizedCaseInsensitiveContains(text)
                || $0.domain.localizedCaseInsensitiveContains(text)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                if flow.subjectMemories.isEmpty {
                    ContentUnavailableView(
                        "还没有记忆", systemImage: "books.vertical",
                        description: Text("录下一段生活，记忆会出现在这里。")
                    )
                }
                ForEach(visible) { item in
                    DisclosureGroup {
                        if let correction = item.correction {
                            Text("待核实的纠错：\(correction)")
                                .foregroundStyle(.orange)
                        }
                        ForEach(item.evidence) { evidence in
                            if let excerpt = evidence.excerpt {
                                Text("来源：\(excerpt)")
                                    .font(.subheadline)
                            }
                        }
                        Text("\(sourceLabel(item.sourceType)) · \(dateLabel(item.recordedAt)) 的录音")
                            .font(.caption).foregroundStyle(.secondary)
                        Menu("管理记忆") {
                            Button("提出纠错") {
                                selectedMemoryID = item.memoryItemId
                                correctionDraft = item.correction ?? ""
                                showCorrection = true
                            }
                            if item.correction != nil {
                                Button("撤回纠错") {
                                    Task { await flow.removeMemoryCorrection(item.memoryItemId) }
                                }
                            }
                            Button("删除这条记忆", role: .destructive) {
                                selectedMemoryID = item.memoryItemId
                                showDeletion = true
                            }
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 7) {
                            Text(item.content).font(.body)
                            Text("\(item.domain) · \(dateLabel(item.recordedAt))")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .navigationTitle("记忆文库")
            .searchable(text: $query, prompt: "搜索记忆")
            .refreshable { await flow.loadSubjectMemories() }
            .task { await flow.loadSubjectMemories() }
            .alert("纠正记忆", isPresented: $showCorrection) {
                TextField("写下正确内容", text: $correctionDraft)
                Button("保存") {
                    guard let selectedMemoryID else { return }
                    Task { await flow.correctMemory(selectedMemoryID, proposedContent: correctionDraft) }
                }
                Button("取消", role: .cancel) {}
            } message: {
                Text("纠错后，原说法会暂停用于 Twin 回答。")
            }
            .confirmationDialog("删除这条记忆？", isPresented: $showDeletion) {
                Button("删除记忆", role: .destructive) {
                    guard let selectedMemoryID else { return }
                    Task { await flow.deleteMemory(selectedMemoryID) }
                }
            } message: {
                Text("原始录音与 Episode 仍保留。")
            }
        }
    }

    private func dateLabel(_ value: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fallback = ISO8601DateFormatter()
        guard let date = formatter.date(from: value) ?? fallback.date(from: value) else { return "" }
        return date.formatted(date: .abbreviated, time: .omitted)
    }

    private func sourceLabel(_ source: String) -> String {
        switch source {
        case "SUBJECT": "本人原话"
        case "THIRD_PARTY": "他人描述"
        case "OBJECTIVE": "客观资料"
        case "CALIBRATION": "校准反馈"
        default: "AI 整理"
        }
    }
}

private struct TwinView: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @EnvironmentObject private var capture: AudioCapture
    @State private var question = ""
    @State private var lastQuestion = ""
    @State private var showDetails = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if flow.twinAnswer == nil && !flow.isBusy {
                        Text("关于你的记忆，想聊什么？")
                            .font(.title3).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, minHeight: 180)
                    }
                    if !lastQuestion.isEmpty {
                        HStack {
                            Spacer(minLength: 44)
                            Text(lastQuestion)
                                .padding(14)
                                .background(Color.accentColor.opacity(0.14), in: RoundedRectangle(cornerRadius: 18))
                        }
                    }
                    if flow.isBusy { ProgressView().padding() }
                    if let answer = flow.twinAnswer {
                        HStack {
                            VStack(alignment: .leading, spacing: 10) {
                                Text(answer.responseType == "ORIGINAL" ? "本人原话" :
                                     answer.responseType == "SIMULATION" ? "模拟回答" : "证据不足")
                                    .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                                Text(answer.answer)
                                    .font(.body)
                                if !answer.evidence.isEmpty {
                                    Text("依据 \(answer.evidence.count) 条记忆")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Button("查看来源与说明") { showDetails = true }
                                    .font(.footnote)
                            }
                            .padding(15)
                            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
                            Spacer(minLength: 36)
                        }
                    }
                    if let message = flow.message {
                        Text(message).font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .padding(16)
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .safeAreaInset(edge: .bottom) {
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("问一个关于记忆的问题", text: $question, axis: .vertical)
                        .lineLimit(1...4)
                        .padding(12)
                        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20))
                    Button {
                        let asked = question.trimmingCharacters(in: .whitespacesAndNewlines)
                        lastQuestion = asked
                        question = ""
                        Task { await flow.askTwin(asked) }
                    } label: {
                        Image(systemName: "arrow.up.circle.fill").font(.system(size: 32))
                    }
                    .disabled(flow.isBusy || question.trimmingCharacters(in: .whitespacesAndNewlines).count < 2)
                    .accessibilityLabel("发送问题")
                }
                .padding(.horizontal, 16).padding(.vertical, 10)
                .background(.bar)
            }
            .navigationTitle("对话")
            .sheet(isPresented: $showDetails) {
                NavigationStack {
                    List {
                        if let answer = flow.twinAnswer {
                            Section("回答依据") {
                                LabeledContent("类型", value: answer.responseType)
                                LabeledContent("置信度", value: "\(Int(answer.confidence * 100))%")
                                if let version = answer.modelVersion {
                                    LabeledContent("模型版本", value: version)
                                }
                                ForEach(answer.evidence) { evidence in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(evidence.excerpt ?? "无摘录")
                                        Text("\(evidence.sourceType) · \(evidence.sourceRef)")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                            Section("朗读") {
                        Button(capture.isSpeaking ? "停止系统朗读" : "系统朗读（非本人声音）") {
                            if capture.isSpeaking {
                                capture.stopSystemSpeech()
                            } else {
                                Task {
                                    if await flow.authorizeVoicePlayback() {
                                        capture.speakSystemText(answer.answer)
                                    }
                                }
                            }
                        }
                        .disabled(flow.isBusy || capture.isRecording)
                        Button("授权并检查设备个人声音") {
                            Task { await capture.requestPersonalVoiceAccess() }
                        }
                        .disabled(flow.isBusy || capture.isRecording)
                        if !capture.personalVoiceChoices.isEmpty {
                            Picker("选择设备个人声音", selection: $capture.selectedPersonalVoiceID) {
                                Text("请选择").tag("")
                                ForEach(capture.personalVoiceChoices) { voice in
                                    Text(voice.name).tag(voice.id)
                                }
                            }
                            Button(capture.isSpeaking ? "停止朗读" : "用设备个人声音朗读") {
                                if capture.isSpeaking {
                                    capture.stopSystemSpeech()
                                } else {
                                    Task {
                                        if await flow.authorizeVoicePlayback() {
                                            capture.speakPersonalText(answer.answer)
                                        }
                                    }
                                }
                            }
                            .disabled(flow.isBusy || capture.isRecording || capture.selectedPersonalVoiceID.isEmpty)
                        }
                        Text("需要独立声音授权。设备个人声音须在本机创建，尚未验证与账号本人身份一致。")
                            .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    .navigationTitle("回答详情")
                    .toolbar { Button("完成") { showDetails = false } }
                }
            }
        }
    }
}

private struct ConnectionView: View {
    @EnvironmentObject private var flow: EpisodeFlow

    var body: some View {
        NavigationStack {
            Form {
                Section("服务连接") {
                    LabeledContent("Backend", value: flow.settings.baseURL)
                    #if DEBUG
                    TextField("Backend 根地址", text: $flow.settings.baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    if !flow.isAuthenticated {
                    SecureField("Actor 令牌", text: $flow.settings.token)
                        .textInputAutocapitalization(.never)
                    TextField("Subject ID", text: $flow.settings.subjectID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("录音同意 ID", text: $flow.settings.recordingConsentID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Cloud Twin 同意 ID", text: $flow.settings.cloudTwinConsentID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("数字交接同意 ID", text: $flow.settings.handoverConsentID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Voice 同意 ID", text: $flow.settings.voiceConsentID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    }
                    Button("保存连接设置") { flow.saveSettings() }
                        .disabled(flow.isBusy)
                    Text("令牌保存在 iOS 钥匙串。模拟器可用 127.0.0.1；真机需要能访问 Mac 的私有网络地址或 HTTPS 服务。")
                        .font(.footnote).foregroundStyle(.secondary)
                    #endif
                }
                Section("明确同意") {
                    Text("确认你有权为此 Subject 录音。录音同意只允许 Capture，不授权 Voice Clone。")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("我确认并登记录音同意") {
                        Task { await flow.grantRecordingConsent() }
                    }
                    .disabled(flow.isBusy || flow.settings.token.isEmpty || flow.settings.subjectID.isEmpty)
                    Button("我确认并登记 Cloud Twin 同意") {
                        Task { await flow.grantCloudTwinConsent() }
                    }
                    .disabled(flow.isBusy || flow.settings.token.isEmpty || flow.settings.subjectID.isEmpty)
                    Button("我确认并登记数字交接预演同意") {
                        Task { await flow.grantHandoverConsent() }
                    }
                    .disabled(flow.isBusy || flow.settings.token.isEmpty || flow.settings.subjectID.isEmpty)
                    Button("我确认并登记独立 Voice 同意") {
                        Task { await flow.grantVoiceConsent() }
                    }
                    .disabled(flow.isBusy || flow.settings.token.isEmpty || flow.settings.subjectID.isEmpty)
                }
                if let message = flow.message {
                    Section { Text(message).font(.footnote) }
                }
            }
            .navigationTitle("连接 Backend")
        }
    }
}

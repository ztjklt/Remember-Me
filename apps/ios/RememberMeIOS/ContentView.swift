import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    var body: some View {
        TabView {
            CaptureView()
                .tabItem { Label("录音", systemImage: "mic") }
            MemoriesView()
                .tabItem { Label("记忆", systemImage: "books.vertical") }
            TwinView()
                .tabItem { Label("Twin", systemImage: "bubble.left.and.text.bubble.right") }
            CalibrationScreen()
                .tabItem { Label("校准", systemImage: "checkmark.bubble") }
            HandoverScreen()
                .tabItem { Label("交接", systemImage: "person.2.badge.key") }
            ConnectionView()
                .tabItem { Label("连接", systemImage: "server.rack") }
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
                            Text("仅根据已锁定 Twin 回答与人的回答比较；证据不足时标记为不确定。不会自动更新 Person Model。")
                                .font(.footnote).foregroundStyle(.secondary)
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

    var body: some View {
        NavigationStack {
            Form {
                Section("引导式采集 · 预览") {
                    Button("刷新 2–4 个优先问题") {
                        Task { await flow.loadCapturePlan() }
                    }
                    .disabled(flow.isBusy || flow.settings.subjectID.isEmpty)
                    if let plan = flow.capturePlan {
                        Text("依据 \(plan.modelVersion) 的覆盖度与校准差异，按启发式分数排序。")
                            .font(.caption).foregroundStyle(.secondary)
                        ForEach(plan.questions) { item in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item.question)
                                Text("\(item.domain) · 已有 \(item.existingFacts) 条来源记忆")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    } else {
                        Text("可先录音，也可读取建议问题后做引导式录音。")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                Section("本机录音") {
                    Text("先征得录音对象同意。录音文件保存在本机；上传后由 Backend 异步处理。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    HStack {
                        Image(systemName: capture.isRecording ? "record.circle.fill" : "waveform")
                            .foregroundStyle(capture.isRecording ? .red : .primary)
                        Text(duration(capture.elapsed))
                            .monospacedDigit()
                            .font(.title2)
                        Spacer()
                        if capture.isPaused { Text("已暂停").foregroundStyle(.orange) }
                    }
                    if capture.isRecording {
                        HStack {
                            Button(capture.isPaused ? "继续" : "暂停") { capture.pauseOrResume() }
                            Spacer()
                            Button("保存录音") { capture.stop() }
                                .tint(.red)
                        }
                    } else {
                        Button("开始录音") { Task { await capture.start() } }
                            .buttonStyle(.borderedProminent)
                        Button("从文件导入设备录音") { showImporter = true }
                    }
                    if let file = capture.fileURL, !capture.isRecording {
                        Text(file.lastPathComponent)
                            .font(.caption)
                            .textSelection(.enabled)
                        Button(capture.isPlaying ? "停止播放" : "完整播放录音") {
                            capture.playOrStop()
                        }
                        DatePicker(
                            "录制时间",
                            selection: Binding(
                                get: { capture.recordedAt ?? Date() },
                                set: { capture.setRecordedAt($0) }
                            ),
                            in: ...Date(),
                            displayedComponents: [.date, .hourAndMinute]
                        )
                        Text("导入文件时请核对时间；设备导出时间可能不等于实际录制时间。")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let message = capture.message {
                        Text(message).font(.footnote).foregroundStyle(.secondary)
                    }
                }

                Section("上传与处理") {
                    Button("上传这段录音") {
                        Task { await flow.uploadAndProcess(fileURL: capture.fileURL, recordedAt: capture.recordedAt) }
                    }
                    .disabled(capture.fileURL == nil || capture.isRecording || flow.isBusy)
                    if flow.isBusy { ProgressView("正在上传或等待处理") }
                    LabeledContent("状态", value: stageTitle(flow.stage))
                    if let id = flow.lastEpisodeID {
                        LabeledContent("Episode ID", value: id)
                            .font(.caption)
                            .textSelection(.enabled)
                        Button("刷新这条 Episode") {
                            Task { await flow.refreshLastEpisode() }
                        }
                        .disabled(flow.isBusy)
                    }
                    if let message = flow.message {
                        Text(message).font(.footnote)
                            .foregroundStyle(flow.stage == "failed" ? .red : .secondary)
                    }
                }
            }
            .navigationTitle("记录生活")
            .fileImporter(isPresented: $showImporter, allowedContentTypes: [.audio]) { result in
                switch result {
                case .success(let url): capture.importAudio(from: url)
                case .failure(let error): capture.message = "无法选择录音：\(error.localizedDescription)"
                }
            }
        }
    }

    private func duration(_ seconds: TimeInterval) -> String {
        let whole = max(0, Int(seconds))
        return String(format: "%02d:%02d", whole / 60, whole % 60)
    }

    private func stageTitle(_ stage: String) -> String {
        switch stage {
        case "idle": return "尚未上传"
        case "uploading": return "上传中"
        case "uploaded": return "已上传"
        case "transcribing": return "转录中"
        case "extracting": return "提取记忆中"
        case "modeling": return "整理结果中"
        case "ready": return "已完成"
        case "failed": return "失败"
        default: return stage
        }
    }
}

private struct MemoriesView: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @State private var selectedMemoryID: String?
    @State private var correctionDraft = ""
    @State private var showCorrection = false
    @State private var showDeletion = false

    var body: some View {
        NavigationStack {
            List {
                if let id = flow.lastEpisodeID {
                    Section("来源") {
                        LabeledContent("Episode", value: id)
                            .textSelection(.enabled)
                        if let version = flow.modelVersion {
                            LabeledContent("模型版本", value: version)
                        }
                    }
                }
                if flow.memories.isEmpty {
                    if flow.subjectMemories.isEmpty {
                        ContentUnavailableView(
                            "暂无记忆", systemImage: "books.vertical",
                            description: Text("录音上传并完成处理后，这里显示 Backend 返回的真实 Memory。")
                        )
                    }
                }
                if let model = flow.personModel {
                    Section("Person Model · 有来源预览") {
                        LabeledContent("版本", value: model.modelVersion)
                        LabeledContent("来源 Memory", value: "\(model.sourceMemoryIds.count)")
                        ForEach(model.domains.keys.sorted(), id: \.self) { domain in
                            if let facts = model.domains[domain], !facts.isEmpty {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("\(domain) · \(facts.count) 条")
                                        .font(.subheadline).bold()
                                    if let latest = facts.last {
                                        Text(latest.content)
                                            .font(.caption).foregroundStyle(.secondary)
                                        Text("证据 \(latest.evidenceIds.count) 项 · \(latest.sourceType)")
                                            .font(.caption2).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }
                if let graph = flow.memoryGraph {
                    let timeline = graph.nodes
                        .filter { $0.kind == "MEMORY" }
                        .sorted { ($0.recordedAt ?? "") < ($1.recordedAt ?? "") }
                    if !timeline.isEmpty {
                        Section("来源与时间图 · 预览") {
                            Text("按领域连接先后记录；每条 Memory 可追溯到 Episode 和证据。争议或已删除的条目不参与。")
                                .font(.footnote).foregroundStyle(.secondary)
                            ForEach(timeline) { node in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(node.label)
                                    Text("\(node.domain ?? "Unclassified") · \(node.sourceType ?? "未知来源") · \(node.recordedAt ?? "时间未知")")
                                        .font(.caption).foregroundStyle(.secondary)
                                    let evidenceCount = graph.edges.filter {
                                        $0.sourceId == node.nodeId && $0.relation == "SUPPORTED_BY"
                                    }.count
                                    Text("来源证据 \(evidenceCount) 项")
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                if !flow.domainCounts.isEmpty {
                    Section("领域线索数（预览）") {
                        ForEach(flow.domainCounts.keys.sorted(), id: \.self) { domain in
                            LabeledContent(domain, value: "\(flow.domainCounts[domain] ?? 0)")
                        }
                    }
                }
                if !flow.subjectMemories.isEmpty {
                    Section("跨 Episode 记忆") {
                        ForEach(flow.subjectMemories) { item in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item.content)
                                if let correction = item.correction {
                                    Text("纠错建议：\(correction)")
                                        .font(.subheadline).foregroundStyle(.orange)
                                    Text("原说法已暂停用于 Twin 回答，等待核实。")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Text("\(item.domain) · \(item.sourceType) · \(Int(item.confidence * 100))%")
                                    .font(.caption).foregroundStyle(.secondary)
                                Text("Episode \(item.episodeId)")
                                    .font(.caption2).textSelection(.enabled)
                                ForEach(item.evidence) { evidence in
                                    if let excerpt = evidence.excerpt {
                                        Text("证据：\(excerpt)")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                                Menu("管理这条记忆") {
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
                                    Button("删除这条 Memory", role: .destructive) {
                                        selectedMemoryID = item.memoryItemId
                                        showDeletion = true
                                    }
                                }
                                .disabled(flow.isBusy)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                } else if !flow.memories.isEmpty {
                    Section("提取结果") {
                        ForEach(flow.memories) { item in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item.content)
                                    .font(.body)
                                Text("\(item.memoryType) · \(item.sourceType) · 置信度 \(Int(item.confidence * 100))%")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("证据：\(item.evidenceIds.joined(separator: ", "))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
            .navigationTitle("我的记忆")
            .toolbar {
                Button("刷新") { Task { await flow.loadSubjectMemories() } }
                    .disabled(flow.isBusy)
            }
            .alert("纠正 Memory", isPresented: $showCorrection) {
                TextField("写下正确内容", text: $correctionDraft)
                Button("保存") {
                    guard let selectedMemoryID else { return }
                    Task { await flow.correctMemory(selectedMemoryID, proposedContent: correctionDraft) }
                }
                Button("取消", role: .cancel) {}
            } message: {
                Text("纠错建议会暂停原说法用于 Twin 回答，原始证据仍可核查。")
            }
            .confirmationDialog("删除这条 Memory？", isPresented: $showDeletion) {
                Button("删除 Memory", role: .destructive) {
                    guard let selectedMemoryID else { return }
                    Task { await flow.deleteMemory(selectedMemoryID) }
                }
            } message: {
                Text("这会从 Memory 结果和 Twin 检索中移除该条目。原始录音与 Episode 仍保留。")
            }
        }
    }
}

private struct TwinView: View {
    @EnvironmentObject private var flow: EpisodeFlow
    @EnvironmentObject private var capture: AudioCapture
    @State private var question = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("询问") {
                    TextField("输入一个可由本人原话回答的问题", text: $question, axis: .vertical)
                        .lineLimit(2...4)
                    Button("查询证据") { Task { await flow.askTwin(question) } }
                        .disabled(flow.isBusy || question.trimmingCharacters(in: .whitespacesAndNewlines).count < 2)
                    if flow.isBusy { ProgressView() }
                    Text("此分支目前实现的是保守证据路由：有相关本人原话才标 ORIGINAL；证据不足时明确说明，不编造回答。")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if let answer = flow.twinAnswer {
                    Section(answer.responseType == "ORIGINAL" ? "本人原话" : (answer.evidence.isEmpty ? "证据不足" : "未核实的相关线索")) {
                        Text(answer.answer).font(.body)
                        LabeledContent("类型", value: answer.responseType)
                        LabeledContent("置信度", value: "\(Int(answer.confidence * 100))%")
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
                        if let voiceName = capture.personalVoiceName {
                            LabeledContent("设备个人声音", value: voiceName)
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
                            .disabled(flow.isBusy || capture.isRecording)
                        }
                        Text("每次播放前验证独立 VOICE 同意。设备个人声音还需 iOS 授权和本机预先创建；此处尚未核实它与 Subject 的身份关系，也不训练或上传声音模型。")
                            .font(.caption).foregroundStyle(.secondary)
                        if let version = answer.modelVersion { LabeledContent("模型版本", value: version) }
                        ForEach(answer.evidence) { evidence in
                            VStack(alignment: .leading) {
                                Text(evidence.excerpt ?? "无摘录")
                                Text("\(evidence.sourceType) · \(evidence.sourceRef)")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if let message = flow.message {
                    Section { Text(message).font(.footnote) }
                }
            }
            .navigationTitle("证据 Twin")
        }
    }
}

private struct ConnectionView: View {
    @EnvironmentObject private var flow: EpisodeFlow

    var body: some View {
        NavigationStack {
            Form {
                Section("本地开发连接") {
                    TextField("Backend 根地址", text: $flow.settings.baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
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
                    Button("保存连接设置") { flow.saveSettings() }
                        .disabled(flow.isBusy)
                    Text("令牌保存在 iOS 钥匙串。模拟器可用 127.0.0.1；真机需要能访问 Mac 的私有网络地址或 HTTPS 服务。")
                        .font(.footnote).foregroundStyle(.secondary)
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

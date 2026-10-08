import SwiftUI

/// PR #81 information architecture; all personal content comes from AppModel.
struct AndroidParityTabs: View {
    @State private var selection = 0
    var body: some View {
        TabView(selection: $selection) {
            NavigationStack { PortraitDashboard() }.tabItem { Label("Portrait", systemImage: "person.text.rectangle") }.tag(0)
            NavigationStack { GraphDashboard() }.tabItem { Label("Graphs", systemImage: "point.3.connected.trianglepath.dotted") }.tag(1)
            NavigationStack { MemoriesDashboard() }.tabItem { Label("Memories", systemImage: "books.vertical") }.tag(2)
            NavigationStack { AgentsDashboard() }.tabItem { Label("Agents", systemImage: "brain") }.tag(3)
            NavigationStack { PersonalDashboard() }.tabItem { Label("Me", systemImage: "person.crop.circle") }.tag(4)
        }
    }
}

private enum PortraitCategory: String, CaseIterable, Identifiable {
    case thing, mood, psychology, filter, status, environment, identity, expression
    var id: String { rawValue }
    var title: String {
        switch self {
        case .thing: "Thing memory"
        case .mood: "Mood memory"
        case .psychology: "Psycho memory"
        case .filter: "Filter memory"
        case .status: "Status memory"
        case .environment: "Environment"
        case .identity: "Identity memory"
        case .expression: "Expression"
        }
    }
    var subtitle: String {
        switch self {
        case .thing: "事件与人生片段"
        case .mood: "叙述中的情绪"
        case .psychology: "决策与珍视的事"
        case .filter: "回看记忆与来源"
        case .status: "声音中的状态 · 待接入"
        case .environment: "环境与地点 · 待接入"
        case .identity: "身份与重要关系"
        case .expression: "表达方式与习惯"
        }
    }
    var symbol: String {
        switch self {
        case .thing: "book.closed"
        case .mood: "cloud.sun"
        case .psychology: "brain"
        case .filter: "line.3.horizontal.decrease.circle"
        case .status: "waveform.path"
        case .environment: "leaf"
        case .identity: "person.crop.rectangle"
        case .expression: "quote.bubble"
        }
    }
    var domains: [String] {
        switch self {
        case .thing: ["EPISODIC_MEMORY"]
        case .psychology: ["VALUES_BELIEFS", "DECISION_PATTERNS"]
        case .identity: ["IDENTITY", "RELATIONSHIPS", "PREFERENCES"]
        case .expression: ["EXPRESSION"]
        default: []
        }
    }
}

private struct DashboardHeader: View {
    let slogan: String
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 9) {
                RememberMeBrand(size: 23)
                Text("REMEMBER ME").font(.subheadline.weight(.semibold)).tracking(1)
            }.foregroundStyle(Ink.coral)
            Text(slogan).font(.body.weight(.medium)).foregroundStyle(Ink.text)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
        .overlay { RoundedRectangle(cornerRadius: 14).stroke(Ink.muted.opacity(0.18)) }
    }
}

private struct DashboardTools: View {
    @EnvironmentObject private var model: AppModel
    @Binding var search: String
    let prompt: String
    var body: some View {
        HStack(spacing: 10) {
            NavigationLink { TwinView() } label: {
                Image(systemName: "bubble.left.and.bubble.right").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("打开对话与校准")
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(Ink.muted)
                TextField(prompt, text: $search).font(.subheadline).autocorrectionDisabled()
                    .accessibilityLabel(prompt)
            }.padding(11).background(Ink.cream, in: RoundedRectangle(cornerRadius: 12))
            ShareLink(item: model.portraitExportText) {
                Image(systemName: "square.and.arrow.up").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("导出当前画像文字").disabled(model.domains.allSatisfy { $0.traits.isEmpty })
        }
    }
}

private struct PortraitDashboard: View {
    @EnvironmentObject private var model: AppModel
    @State private var search = ""
    @State private var showRecorder = false
    @State private var selectedQuestion: QuestionRecord?
    private var categories: [PortraitCategory] {
        PortraitCategory.allCases.filter { search.isEmpty || ($0.title + $0.subtitle).localizedCaseInsensitiveContains(search) }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DashboardTools(search: $search, prompt: "Search portraits")
                DashboardHeader(slogan: "A quiet map of you")
                Text("Portrait").font(.title.weight(.medium))
                Text(model.domains.contains(where: { !$0.traits.isEmpty }) ? "从你留下的原话，慢慢了解你。每项理解都可以查看依据和纠正。" : "从一段真实录音开始。这里会呈现你的记忆与理解，不用示例替代你。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
                ActionButton(title: model.draft == nil ? "开始录音" : "继续查看已保存的录音", icon: "mic") {
                    selectedQuestion = nil; showRecorder = true
                }.accessibilityIdentifier("portrait.record")
                if model.pairing == nil { ConnectionNotice() }
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    ForEach(categories) { category in
                        NavigationLink { PortraitCategoryView(category: category) } label: {
                            VStack(alignment: .leading, spacing: 10) {
                                Image(systemName: category.symbol).foregroundStyle(Ink.coral).font(.title3)
                                Text(category.title).font(.body.weight(.medium)).foregroundStyle(Ink.text)
                                Text(category.subtitle).font(.subheadline).foregroundStyle(Ink.muted)
                                HStack {
                                    let count = model.domains.filter { category.domains.contains($0.domain) }.reduce(0) { $0 + $1.traits.count }
                                    if !category.domains.isEmpty { Text("\(count) 项理解").font(.caption).foregroundStyle(Ink.muted) }
                                    Spacer(); Image(systemName: "chevron.right").font(.caption).foregroundStyle(Ink.coral)
                                }
                            }.frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
                                .padding(14).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                        }.buttonStyle(.plain).accessibilityIdentifier("portrait.category.\(category.rawValue)")
                    }
                }
                if categories.isEmpty { Text("没有匹配的画像分类。").foregroundStyle(Ink.muted) }
                Divider()
                Text("Today").font(.title3.weight(.medium))
                if model.questions.isEmpty {
                    Text("录音整理后，值得继续了解的问题会出现在这里。").foregroundStyle(Ink.muted)
                }
                ForEach(model.questions.filter { search.isEmpty || $0.text.localizedCaseInsensitiveContains(search) }) { question in
                    Button {
                        selectedQuestion = question; showRecorder = true
                    } label: {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: "sparkle").foregroundStyle(Ink.coral)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(question.text).foregroundStyle(Ink.text)
                                Text(question.reason == "contradiction" ? "有不同说法，等你澄清" : "再多了解你一点")
                                    .font(.subheadline).foregroundStyle(Ink.muted)
                            }
                            Spacer(); Image(systemName: "mic").foregroundStyle(Ink.coral)
                        }.padding(.vertical, 10)
                    }.buttonStyle(.plain).disabled(model.draft != nil)
                    Divider()
                }
            }.padding(20)
        }
        .background(Ink.paper.ignoresSafeArea()).toolbar(.hidden, for: .navigationBar)
        .fullScreenCover(isPresented: $showRecorder) { RecorderView(question: selectedQuestion, calibration: nil) }
        .refreshable { await model.refresh() }
    }
}

struct ConnectionNotice: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        Button { model.showConnection = true } label: {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "link")
                VStack(alignment: .leading, spacing: 5) {
                    Text("连接你的记忆服务").font(.subheadline.weight(.medium))
                    Text("录音可以先留在手机。连接后再转写、核对并生成理解。")
                        .font(.caption).foregroundStyle(Ink.muted)
                }
                Spacer(); Image(systemName: "chevron.right").font(.caption)
            }.padding(14).background(Ink.peach, in: RoundedRectangle(cornerRadius: 14))
        }.buttonStyle(.plain).accessibilityIdentifier("service.connect")
    }
}

private struct PortraitCategoryView: View {
    @EnvironmentObject private var model: AppModel
    let category: PortraitCategory
    private var memories: [MemoryRecord] {
        model.memories.filter { category == .mood ? $0.memory_type == "EMOTION" : category == .filter || category.domains.contains($0.domain ?? "") || (category == .thing && $0.memory_type == "EVENT") }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DashboardHeader(slogan: category.subtitle)
                if category == .status || category == .environment {
                    Text("这项分析还没有接入。声音状态与环境识别需要可验证的音频能力，当前不会根据转写文字猜测。")
                        .foregroundStyle(Ink.muted)
                } else {
                    ForEach(model.domains.filter { category.domains.contains($0.domain) }) { domain in
                        ForEach(domain.traits) { trait in
                            NavigationLink { TraitEvidenceView(trait: trait) } label: {
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(trait.statement).foregroundStyle(Ink.text)
                                    Text("\(trait.evidence_ids.count) 条依据 · 查看原文").font(.subheadline).foregroundStyle(Ink.coral)
                                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                                    .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                            }.buttonStyle(.plain)
                        }
                    }
                    ForEach(memories) { memory in
                        NavigationLink { MemoryDetailView(memory: memory) } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(memory.content).foregroundStyle(Ink.text)
                                Text("记忆 · \(memory.recorded_at.prefix(10))").font(.subheadline).foregroundStyle(Ink.muted)
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 12)
                        }.buttonStyle(.plain)
                        Divider()
                    }
                    if memories.isEmpty && model.domains.filter({ category.domains.contains($0.domain) }).allSatisfy({ $0.traits.isEmpty }) {
                        ContentUnavailableView("还没有相关记忆", systemImage: category.symbol, description: Text("先录下真实经历，核对文字后再整理。"))
                    }
                }
            }.padding(20)
        }.background(Ink.paper.ignoresSafeArea()).navigationTitle(category.title).navigationBarTitleDisplayMode(.inline)
    }
}

private struct TraitEvidenceView: View {
    @EnvironmentObject private var model: AppModel
    let trait: TraitRecord
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(trait.statement).font(.title2.weight(.medium))
                if let context = trait.context, !context.isEmpty { Text(context).foregroundStyle(Ink.muted) }
                if trait.status == "unresolved" { Label("有不同说法，等待本人澄清", systemImage: "questionmark.circle").foregroundStyle(Ink.coral) }
                ForEach(trait.evidence_ids + trait.counter_evidence_ids, id: \.self) { id in
                    let memory = model.memories.first { $0.evidence.contains { $0.id == id } }
                    let source = memory?.evidence.first { $0.id == id }
                    VStack(alignment: .leading, spacing: 10) {
                        Text(trait.counter_evidence_ids.contains(id) ? "另一种说法" : "支持这项理解的原文").font(.headline)
                        Text(source?.excerpt ?? "该证据目前未在记忆列表中返回，不能还原原文。")
                            .foregroundStyle(Ink.muted)
                        if let memory { NavigationLink("查看记忆、听原音或纠正") { MemoryDetailView(memory: memory) } }
                    }.padding(16).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                }
            }.padding(20)
        }.background(Ink.paper.ignoresSafeArea()).navigationTitle("理解的依据").navigationBarTitleDisplayMode(.inline)
    }
}

private struct GraphDashboard: View {
    @EnvironmentObject private var model: AppModel
    @State private var search = ""
    private let metrics = [("Event flow", "人生片段与时间", "EPISODIC_MEMORY", "calendar"),
                           ("Mood trends", "情绪记录 · 趋势待接入", "", "cloud.sun"),
                           ("Decision + values", "决策与价值取向", "DECISION_PATTERNS", "arrow.triangle.branch"),
                           ("Expression style", "表达方式与习惯", "EXPRESSION", "quote.bubble")]
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DashboardTools(search: $search, prompt: "Search graphs")
                DashboardHeader(slogan: "Memory relationships")
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    ForEach(metrics.filter { search.isEmpty || ($0.0 + $0.1).localizedCaseInsensitiveContains(search) }, id: \.0) { metric in
                        NavigationLink { ModelView() } label: {
                            VStack(alignment: .leading, spacing: 10) {
                                Image(systemName: metric.3).foregroundStyle(Ink.coral)
                                Text(metric.0).font(.body.weight(.medium)).foregroundStyle(Ink.text)
                                Text(metric.1).font(.subheadline).foregroundStyle(Ink.muted)
                            }.frame(maxWidth: .infinity, minHeight: 95, alignment: .topLeading)
                                .padding(14).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                        }.buttonStyle(.plain)
                    }
                }
                Text("How do these combine?").font(.title3.weight(.medium))
                Text("记忆连接经历、价值与表达。每一项理解都应当能回到原文，等待你确认或纠正。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
                Label("设计示意 · 不是你的真实关系数据", systemImage: "info.circle")
                    .font(.caption).foregroundStyle(Ink.muted)
                Image("AndroidRelationshipGraph").resizable().scaledToFit().clipShape(RoundedRectangle(cornerRadius: 14))
                    .accessibilityLabel("Android 原型关系图设计示意")
                NavigationLink { ModelView() } label: {
                    Label("查看真实的七领域理解与证据", systemImage: "point.3.connected.trianglepath.dotted")
                }.buttonStyle(.bordered)
                ForEach(model.domains.filter { !$0.traits.isEmpty && (search.isEmpty || $0.traits.contains { $0.statement.localizedCaseInsensitiveContains(search) }) }) { domain in
                    ForEach(domain.traits) { trait in
                        NavigationLink { TraitEvidenceView(trait: trait) } label: {
                            HStack {
                                Image(systemName: "link")
                                Text(trait.statement).foregroundStyle(Ink.text)
                                Spacer(); Text("\(trait.evidence_ids.count)").foregroundStyle(Ink.coral)
                            }.padding(.vertical, 10)
                        }.buttonStyle(.plain)
                        Divider()
                    }
                }
            }.padding(20)
        }.background(Ink.paper.ignoresSafeArea()).toolbar(.hidden, for: .navigationBar)
    }
}

private struct MemoriesDashboard: View {
    @EnvironmentObject private var model: AppModel
    @State private var search = ""
    @State private var showRecorder = false
    private var visibleMemories: [MemoryRecord] {
        model.memories.filter { search.isEmpty || $0.content.localizedCaseInsensitiveContains(search) }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DashboardTools(search: $search, prompt: "Search memories")
                DashboardHeader(slogan: "Memories show who you are")
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        Label("Memory", systemImage: "clock").font(.title3.weight(.medium))
                        Spacer()
                        Button { Task { await model.refresh() } } label: {
                            Image(systemName: "arrow.clockwise").frame(minWidth: 44, minHeight: 44)
                        }.accessibilityLabel("刷新记忆")
                    }
                    Text("这里显示当前有效的记忆。打开一条记忆，可以听原音、查看证据或纠正。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    if visibleMemories.isEmpty {
                        Text(search.isEmpty ? "No memories yet" : "没有匹配的记忆").foregroundStyle(Ink.muted)
                        Text("新的录音与核对后的记忆会出现在这里。").font(.subheadline).foregroundStyle(Ink.muted)
                    }
                    ForEach(Array(visibleMemories.prefix(5))) { memory in
                        NavigationLink { MemoryDetailView(memory: memory) } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Text(String(memory.recorded_at.prefix(10))).font(.caption).foregroundStyle(Ink.coral)
                                Circle().fill(Ink.coral).frame(width: 8, height: 8).padding(.top, 4)
                                Text(memory.content).font(.subheadline).foregroundStyle(Ink.text)
                            }.padding(.vertical, 8)
                        }.buttonStyle(.plain)
                        Divider()
                    }
                }.padding(16).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                NavigationLink { ArchiveView() } label: {
                    Label("打开录音与记忆档案", systemImage: "books.vertical")
                }.buttonStyle(.bordered).accessibilityIdentifier("memories.archive")
                Divider()
                VStack(alignment: .leading, spacing: 14) {
                    Text("Memory control board").font(.title3.weight(.medium))
                    NavigationLink { ArchiveView() } label: {
                        Label("Memory change · 核对并纠正", systemImage: "square.and.pencil").frame(minHeight: 44)
                    }
                    Divider()
                    NavigationLink { ArchiveView() } label: {
                        Label("Memory delete · 选择要删除的记忆", systemImage: "trash").frame(minHeight: 44)
                    }
                    Divider()
                    Button { showRecorder = true } label: {
                        Label(model.draft == nil ? "Add memory · 录下一段经历" : "继续已保存的录音", systemImage: "mic").frame(minHeight: 44)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                    .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                if model.pairing == nil { ConnectionNotice() }
            }.padding(20)
        }.background(Ink.paper.ignoresSafeArea()).toolbar(.hidden, for: .navigationBar)
        .fullScreenCover(isPresented: $showRecorder) { RecorderView(question: nil, calibration: nil) }
        .refreshable { await model.refresh() }
    }
}

private struct AgentsDashboard: View {
    @EnvironmentObject private var model: AppModel
    @State private var search = ""
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DashboardTools(search: $search, prompt: "Search agents")
                DashboardHeader(slogan: "Agents behind your memories")
                Text("每一步各司其职。原文、理解与校正分别保留。").font(.subheadline).foregroundStyle(Ink.muted)
                Text("Agents list").font(.title3.weight(.medium))
                if search.isEmpty || "Memory keeper 记忆录音".localizedCaseInsensitiveContains(search) {
                    agent("Memory keeper", symbol: "book.closed", detail: "保留原音、转写和本人核对文字。", status: model.processingStatus.isEmpty ? "\(model.episodes.count) 段录音" : "有处理任务")
                }
                if search.isEmpty || "Portrait reader 画像理解".localizedCaseInsensitiveContains(search) {
                    agent("Portrait reader", symbol: "chart.xyaxis.line", detail: "七个领域的理解，每一项都关联证据。", status: "\(model.domains.reduce(0) { $0 + $1.traits.count }) 项理解")
                }
                if search.isEmpty || "Twin guide 问答校准".localizedCaseInsensitiveContains(search) {
                    agent("Twin guide", symbol: "bubble.left.and.bubble.right", detail: "有证据的回答，先锁定，再听你的真实答案。", status: model.cloudConsentID == nil ? "等待授权" : "已授权")
                }
                Divider()
                Text("Recent work").font(.title3.weight(.medium))
                if let calibration = model.calibrationRun {
                    Text(calibration.summary ?? "\(calibration.question) · \(calibration.status)").foregroundStyle(Ink.muted)
                } else if let episode = model.episodes.first {
                    Text("最近录音：\(episode.recorded_at.prefix(10)) · \(episode.status)").foregroundStyle(Ink.muted)
                } else { Text("暂无真实运行记录。录下一段经历后再来看看。").foregroundStyle(Ink.muted) }
                VStack(alignment: .leading, spacing: 12) {
                    Text("You are the master controller").font(.title3.weight(.medium))
                    Text("由你决定要问什么、如何纠正，以及是否继续使用资料。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                    NavigationLink { TwinView() } label: {
                        Label("打开问答与五维校准", systemImage: "bubble.left.and.bubble.right")
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }.buttonStyle(.borderedProminent).accessibilityIdentifier("agents.twin")
                }.padding(16).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                if model.pairing == nil { ConnectionNotice() }
            }.padding(20)
        }.background(Ink.paper.ignoresSafeArea()).toolbar(.hidden, for: .navigationBar)
    }
    private func agent(_ name: String, symbol: String, detail: String, status: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol).font(.title3).foregroundStyle(Ink.coral)
            VStack(alignment: .leading, spacing: 8) {
                Text(name).font(.body.weight(.medium))
                Text(detail).font(.subheadline).foregroundStyle(Ink.muted)
                Text(model.pairing == nil ? "服务未连接" : status).font(.caption).foregroundStyle(Ink.coral)
            }
            Spacer()
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Ink.peach.opacity(0.65), in: RoundedRectangle(cornerRadius: 14))
    }
}

private struct PersonalDashboard: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DashboardHeader(slogan: "Your memories, your choices")
                Text("Settings").font(.title.weight(.medium))
                HStack(spacing: 12) {
                    Image(systemName: "person.crop.circle.fill").font(.largeTitle).foregroundStyle(Ink.coral)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("我的记忆空间").font(.headline)
                        Text(model.pairing == nil ? "原音先留在手机" : "已连接私人记忆服务").font(.subheadline).foregroundStyle(Ink.muted)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                    .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                NavigationLink { ProfileView() } label: { Label("数据、声音与系统授权", systemImage: "slider.horizontal.3") }.buttonStyle(.bordered)
                Button { model.showConnection = true } label: { Label(model.pairing == nil ? "连接服务" : "管理服务连接", systemImage: "link") }.buttonStyle(.bordered)
                Divider()
                Text("Today's data").font(.title3.weight(.medium))
                metric("今日已上传录音", value: model.todayEpisodes.count, unit: "段", symbol: "mic")
                metric("今日已转写文字", value: model.todayEpisodes.reduce(0) { $0 + ($1.transcript?.count ?? 0) }, unit: "字", symbol: "text.alignleft")
                metric("今日记忆", value: model.todayMemories.count, unit: "条", symbol: "book.closed")
                Text("Today's words to you").font(.title3.weight(.medium))
                Text(model.questions.first?.text ?? "还没有根据真实记录生成的话语。你可以从今天的一件小事开始。")
                    .padding(16).frame(maxWidth: .infinity, alignment: .leading).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                Text("颜色与字号跟随 iPhone 系统设置。你的录音授权、云端问答与个人声音授权分别管理。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
            }.padding(20)
        }.background(Ink.paper.ignoresSafeArea()).toolbar(.hidden, for: .navigationBar)
    }
    private func metric(_ title: String, value: Int, unit: String, symbol: String) -> some View {
        HStack {
            Label(title, systemImage: symbol)
            Spacer(); Text("\(value) \(unit)").foregroundStyle(Ink.coral)
        }.padding(16).background(Ink.peach.opacity(0.65), in: RoundedRectangle(cornerRadius: 14))
    }
}

extension AppModel {
    var todayEpisodes: [EpisodeRecord] { episodes.filter { isToday($0.recorded_at) } }
    var todayMemories: [MemoryRecord] { memories.filter { isToday($0.recorded_at) } }
    private func isToday(_ value: String) -> Bool {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = parser.date(from: value) ?? ISO8601DateFormatter().date(from: value)
        return date.map { Calendar.current.isDateInToday($0) } ?? false
    }
    var portraitExportText: String {
        "Remember Me · Person Model v\(modelVersion)\n\n" + domains.map { domain in
            domain.domain + "\n" + domain.traits.map { "• \($0.statement)\n  \($0.context ?? "")\n  \($0.evidence_ids.count) 条依据" }.joined(separator: "\n")
        }.joined(separator: "\n\n")
    }
}

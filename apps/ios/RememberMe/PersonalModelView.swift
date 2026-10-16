import SwiftUI

struct ModelCoverage: Decodable {
    let subject_id: String
    let model_version: Int
    let metric_version: String
    let percentage: Int
    let cap_percentage: Int
    let covered_units: Int
    let target_units: Int
    let domains: [CoverageDomain]
    let explanation: String
    var displayedPercentage: Int { min(95, max(0, percentage)) }
}
struct CoverageDomain: Decodable, Identifiable {
    let domain: String
    let source_count: Int
    let target_sources: Int
    let percentage: Int
    let episode_ids: [String]
    var id: String { domain }
    var title: String {
        ["IDENTITY":"身份与角色", "EPISODIC_MEMORY":"经历与记忆", "RELATIONSHIPS":"人物与关系",
         "PREFERENCES":"偏好", "VALUES_BELIEFS":"价值与信念", "DECISION_PATTERNS":"选择与做事方法", "EXPRESSION":"表达方式"][domain] ?? domain
    }
}
struct VoiceIdentitySummary: Decodable, Identifiable {
    let identity_id: String
    let label: String
    let role: String
    let model_version: String
    var id: String { identity_id }
}
struct VoiceIdentityList: Decodable { let available: Bool; let items: [VoiceIdentitySummary]; let enrollment_prompt: String; let notice: String }
extension APIClient {
    func modelCoverage(subject: String) async throws -> ModelCoverage {
        try JSONDecoder().decode(ModelCoverage.self, from: await request("/api/v1/subjects/\(subject)/person-model/coverage"))
    }
    func voiceIdentities(subject: String) async throws -> VoiceIdentityList {
        try JSONDecoder().decode(VoiceIdentityList.self, from: await request("/api/v1/subjects/\(subject)/voice-identities"))
    }
}

struct PersonSilhouette: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        let sx = rect.width / 160, sy = rect.height / 300
        p.addEllipse(in: CGRect(x:57*sx,y:0,width:46*sx,height:46*sy))
        let points: [CGPoint] = [CGPoint(x:60,y:53),CGPoint(x:100,y:53),CGPoint(x:122,y:64),CGPoint(x:146,y:148),CGPoint(x:129,y:154),CGPoint(x:108,y:95),CGPoint(x:106,y:162),CGPoint(x:116,y:286),CGPoint(x:94,y:296),CGPoint(x:80,y:188),CGPoint(x:66,y:296),CGPoint(x:44,y:286),CGPoint(x:54,y:162),CGPoint(x:52,y:95),CGPoint(x:31,y:154),CGPoint(x:14,y:148),CGPoint(x:38,y:64)]
        p.move(to: CGPoint(x:points[0].x*sx,y:points[0].y*sy))
        for point in points.dropFirst() { p.addLine(to: CGPoint(x:point.x*sx,y:point.y*sy)) };p.closeSubpath()
        return p
    }
}
struct CoverageFigure: View {
    let percentage: Int
    var body: some View {
        ZStack(alignment:.bottom) {
            PersonSilhouette().fill(Ink.coral.opacity(0.13))
            Rectangle().fill(LinearGradient(colors:[Ink.coral.opacity(0.6),Ink.coral],startPoint:.bottom,endPoint:.top))
                .frame(height:300*CGFloat(min(95,max(0,percentage)))/100)
        }.frame(width:160,height:300).mask(PersonSilhouette())
            .accessibilityHidden(true)
    }
}
struct PersonalModelView: View {
    @EnvironmentObject private var model: AppModel
    @State private var coverage: ModelCoverage?
    @State private var identities: VoiceIdentityList?
    @State private var loadedScope: ReviewScope?
    @State private var error: String?
    @State private var loading = false
    private var currentScope: ReviewScope? { model.pairing.map(ReviewScope.init) }
    private var visibleCoverage: ModelCoverage? { loadedScope == currentScope ? coverage : nil }
    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:RMSpacing.lg) {
                Text("Personal Model").font(RMTypography.caption).foregroundStyle(Ink.muted)
                if let snapshot = visibleCoverage {
                    VStack(spacing:RMSpacing.md) {
                        CoverageFigure(percentage:snapshot.displayedPercentage)
                        Text("\(snapshot.displayedPercentage)%").font(.system(size:44,weight:.semibold,design:.rounded)).monospacedDigit()
                        Text("人物模型 · 资料覆盖").font(RMTypography.body)
                        Text("随着有效记忆逐渐丰富").font(RMTypography.caption).foregroundStyle(Ink.muted)
                    }.frame(maxWidth:.infinity).padding(.vertical,RMSpacing.lg)
                        .accessibilityElement(children:.combine).accessibilityLabel("人物模型资料覆盖百分之\(snapshot.displayedPercentage)")
                        .accessibilityIdentifier("personalModel.coverage")
                    ForEach(snapshot.domains) { domain in
                        VStack(alignment:.leading,spacing:8) {
                            HStack { Text(domain.title).font(.headline); Spacer(); Text("\(domain.source_count) 份资料").font(.caption).foregroundStyle(Ink.muted) }
                            ProgressView(value:Double(min(95,max(0,domain.percentage))),total:100).tint(Ink.coral)
                            Text("当前整理目标：\(domain.target_sources) 个不同有效来源").font(.caption).foregroundStyle(Ink.muted)
                        }.rmCardSurface()
                    }
                    Text(snapshot.explanation).font(.footnote).foregroundStyle(Ink.muted)
                    Text("模型版本 \(snapshot.model_version)").font(.caption).foregroundStyle(Ink.muted)
                } else if loading { ProgressView("正在读取人物模型…").frame(maxWidth:.infinity) }
                else { Text(error ?? "连接服务后，查看真实人物模型的资料覆盖。").foregroundStyle(Ink.muted) }
                if loadedScope == currentScope, let identities {
                    VStack(alignment:.leading,spacing:12) {
                        Text("声音识别").font(.headline)
                        if identities.items.contains(where:{$0.role == "subject"}) {
                            Label("已记住本人声音",systemImage:"waveform.badge.checkmark")
                            Text("匹配本人的聊天原话会自动整理为记忆。其他人的发言保留各自归属。").font(.footnote).foregroundStyle(Ink.muted)
                        } else {
                            Text(identities.available ? "在正常聊天里介绍一下自己，就可以开始记住你的声音。" : "当前服务尚未准备声音识别，录音和聊天仍可使用。").font(.footnote).foregroundStyle(Ink.muted)
                        }
                        NavigationLink { TwinVoiceCallView(call:model.realtimeVoice) } label: { Label("在聊天里记住声音",systemImage:"mic") }
                    }.rmCardSurface()
                }
                NavigationLink { PersonReviewView(review:model.personReview) } label: { Label("查看我的理解与表达",systemImage:"person.text.rectangle") }
                NavigationLink { PersonalLearningView() } label: { Label("复刻验证",systemImage:"chart.bar.doc.horizontal") }
                NavigationLink { EntrustmentView() } label: { Label("数字托付",systemImage:"lock.square") }
            }.padding(RMSpacing.page)
        }.background(Ink.paper).navigationTitle("人物模型").navigationBarTitleDisplayMode(.inline)
            .task(id:currentScope) { await reload() }.refreshable { await reload() }
    }
    private func reload() async {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-personal-model") {
            let names=["IDENTITY","EPISODIC_MEMORY","RELATIONSHIPS","PREFERENCES","VALUES_BELIEFS","DECISION_PATTERNS","EXPRESSION"]
            let rows=names.enumerated().map { ["domain":$0.element,"source_count":$0.offset % 4,"target_sources":5,"percentage":($0.offset % 4)*19,"episode_ids":[]] as [String:Any] }
            let payload:[String:Any]=["subject_id":"isolated-ui-fixture","model_version":3,"metric_version":"seven-domains-five-sources-v1","percentage":24,"cap_percentage":95,"covered_units":9,"target_units":35,"domains":rows,"explanation":"七个领域各以5个不同有效本人资料来源为当前整理目标，上限95%。这不是人格复刻准确率。"]
            coverage=try? JSONDecoder().decode(ModelCoverage.self,from:JSONSerialization.data(withJSONObject:payload));loadedScope=currentScope;return
        }
        #endif
        coverage=nil;identities=nil;loadedScope=nil;error=nil
        guard let pairing=model.pairing else { return }
        let scope=ReviewScope(pairing);loading=true
        defer { if currentScope == scope { loading=false } }
        do {
            let api=try APIClient(baseURL:pairing.baseURL,fingerprint:pairing.fingerprint,token:pairing.token)
            let result=try await api.modelCoverage(subject:pairing.subjectID)
            guard !Task.isCancelled,currentScope == scope,result.subject_id == pairing.subjectID else { return }
            loadedScope=scope;coverage=result
            if let voices=try? await api.voiceIdentities(subject:pairing.subjectID),!Task.isCancelled,currentScope == scope { identities=voices }
        } catch { guard currentScope == scope,!Task.isCancelled else{return};self.error="人物模型暂未读取到，可以下拉重试。" }
    }
}

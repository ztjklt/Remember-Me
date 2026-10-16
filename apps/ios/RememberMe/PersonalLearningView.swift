import Foundation
import Combine
import SwiftUI

// Server projections only. Personal text, training artifacts and provider keys
// never become a second client-side training store.
struct PersonalLearningDataset: Decodable {
    let examples: Int
    let source_groups: Int
    let train: Int
    let validation: Int
    let test: Int
    let missing: [String]
}
struct PersonalLearningRequirements: Decodable {
    let min_examples: Int
    let min_source_groups: Int
}
struct PersonalLearningJob: Decodable {
    let job_id: String
    let status: String
    let activation_allowed: Bool
}
struct PersonalLearningRecord: Decodable {
    let enabled: Bool
    let policy: String
    let notice: String
    let status: String
    let trainer_available: Bool
    let training_consent_id: String?
    let dataset: PersonalLearningDataset
    let requirements: PersonalLearningRequirements
    let job: PersonalLearningJob?
    let activation_allowed: Bool

    var statusTitle: String {
        switch status {
        case "disabled": "未开启"
        case "insufficient_data": "还需要本人资料"
        case "ineligible_data": "训练资料需要核对"
        case "trainer_offline", "unavailable": "训练服务暂未就绪"
        case "queued": "等待训练"
        case "running": "正在训练个人模型"
        case "awaiting_validation", "trained": "训练已完成，等待验证"
        case "failed": "训练未完成"
        case "rejected": "训练结果未通过检查"
        case "stale": "资料已更新，等待重新训练"
        case "revoked": "训练许可已撤销"
        default: "状态待更新"
        }
    }
    var statusExplanation: String {
        switch status {
        case "disabled": "开启后，系统会在本人核对资料足够时安排训练。"
        case "insufficient_data": "继续记录、核对和纠正，资料达到要求后才会开始训练。"
        case "ineligible_data": "部分资料重复或测试条件不符，先核对来源；这次不会训练或生效。"
        case "trainer_offline", "unavailable": "资料仍保留。服务恢复后可继续，不代表模型已经训练好。"
        case "queued": "任务已进入队列，还没有完成训练。"
        case "running": "正在更新个人模型参数，完成后还需要本人验证。"
        case "awaiting_validation", "trained": "候选参数已训练完成，当前孪生尚未切换；候选还需要单独验证和部署。"
        case "failed", "rejected": "这次结果没有生效，可刷新查看后续状态。"
        case "stale": "以前的结果已失效，系统将依据当前资料重新检查。"
        case "revoked": "系统已停止使用这份许可进行训练。"
        default: "请刷新查看当前进度。"
        }
    }
}

struct FidelityInterval: Decodable {
    let lower: Double
    let upper: Double
    let confidence_level: Double
    var isValid: Bool {
        lower.isFinite && upper.isFinite && confidence_level.isFinite &&
        0 <= lower && lower <= upper && upper <= 1 && 0 < confidence_level && confidence_level < 1
    }
}
struct FidelityDimensionRecord: Decodable, Identifiable {
    let dimension: String
    let label: String
    let status: String
    let observed_count: Int
    let independent_group_count: Int
    let matching_group_count: Int
    let agreement_rate: Double?
    let confidence_interval: FidelityInterval?
    let gaps: [String]
    var id: String { dimension }
    var measuredRate: Double? {
        guard status == "available", independent_group_count >= 20,
              let rate = agreement_rate, rate.isFinite, let interval = confidence_interval, interval.isValid,
              interval.lower <= rate, rate <= interval.upper else { return nil }
        return rate
    }
}
struct FidelityOverallRecord: Decodable {
    let agreement_rate: Double?
    let confidence_interval: FidelityInterval?
    let gaps: [String]
}
struct FidelityBenchmarkQuestion: Decodable, Identifiable {
    let question_id: String
    let question_group_id: String
    let question: String
    var id: String { question_id }
}
struct FidelityCaseRecord: Decodable, Identifiable {
    let case_id: String
    let question: String
    let status: String
    let response_type: String
    let human_answer: String?
    let locked_answer: String?
    let ratings: [String: String]
    let created_at: String
    private enum CodingKeys: String, CodingKey {
        case case_id, question, status, response_type, human_answer, locked_answer, ratings, created_at
    }
    init(from decoder: Decoder) throws {
        let fields = try decoder.container(keyedBy: CodingKeys.self)
        case_id = try fields.decode(String.self, forKey: .case_id)
        question = try fields.decode(String.self, forKey: .question)
        status = try fields.decode(String.self, forKey: .status)
        response_type = try fields.decode(String.self, forKey: .response_type)
        human_answer = try fields.decodeIfPresent(String.self, forKey: .human_answer)
        locked_answer = try fields.decodeIfPresent(String.self, forKey: .locked_answer)
        ratings = try fields.decodeIfPresent([String: String].self, forKey: .ratings) ?? [:]
        created_at = try fields.decode(String.self, forKey: .created_at)
    }
    var id: String { case_id }
    // Even a malformed response must not reveal a prediction before the owner
    // has sealed the independent human response.
    var visiblePrediction: String? {
        guard ["awaiting_rating", "rated"].contains(status), human_answer?.isEmpty == false else { return nil }
        return locked_answer
    }
}
struct FidelityReportRecord: Decodable {
    let label: String
    let status: String
    let accepted_observation_count: Int
    let independent_group_count: Int
    let excluded_observation_count: Int
    let dimensions: [FidelityDimensionRecord]
    let overall: FidelityOverallRecord
    let interpretation: String
    let cases: [FidelityCaseRecord]
    let question_bank: [FidelityBenchmarkQuestion]?
    var measuredRate: Double? {
        guard status == "available", Set(dimensions.map(\.dimension)) == Set(personalFidelityDimensions.map(\.key)),
              dimensions.count == 5, dimensions.allSatisfy({ $0.measuredRate != nil }),
              let rate = overall.agreement_rate, rate.isFinite, let interval = overall.confidence_interval,
              interval.isValid, interval.lower <= rate, rate <= interval.upper else { return nil }
        return rate
    }
}

let personalFidelityDimensions = [(key: "DECISION", label: "选择"), (key: "REASONING", label: "理由"),
    (key: "VALUE_PRIORITY", label: "价值优先级"), (key: "EMOTIONAL_REACTION", label: "情绪反应"),
    (key: "EXPRESSION", label: "表达")]
let personalFidelityRatings = [(key: "MATCH", label: "一致"), (key: "PARTIAL", label: "部分一致"),
    (key: "DIFFERENT", label: "不同"), (key: "NOT_OBSERVED", label: "未谈到")]

extension APIClient {
    func personalLearningPath(subjectID: String, suffix: String) throws -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-"))
        guard !subjectID.isEmpty, subjectID.unicodeScalars.allSatisfy(allowed.contains) else { throw APIError.invalidURL }
        return "/api/v1/subjects/\(subjectID)/twin/\(suffix)"
    }
    func personalLearning(subjectID: String) async throws -> PersonalLearningRecord {
        try JSONDecoder().decode(PersonalLearningRecord.self, from: await request(
            personalLearningPath(subjectID: subjectID, suffix: "learning"), timeout: 30))
    }
    func configurePersonalLearning(subjectID: String, enabled: Bool, consentID: String?, policy: String = "") async throws -> PersonalLearningRecord {
        var fields: [String: Any] = ["enabled": enabled, "accepted_policy": policy]
        if let consentID { fields["training_consent_id"] = consentID }
        return try JSONDecoder().decode(PersonalLearningRecord.self, from: await request(
            personalLearningPath(subjectID: subjectID, suffix: "learning"), method: "PUT",
            body: JSONSerialization.data(withJSONObject: fields), contentType: "application/json", timeout: 30))
    }
    func personalFidelity(subjectID: String) async throws -> FidelityReportRecord {
        try JSONDecoder().decode(FidelityReportRecord.self, from: await request(
            personalLearningPath(subjectID: subjectID, suffix: "fidelity"), timeout: 30))
    }
    func createPersonalFidelityCase(subjectID: String, question: String, cloudConsentID: String,
                                   benchmarkQuestionID: String? = nil) async throws -> FidelityCaseRecord {
        var fields = ["question": question, "cloud_consent_id": cloudConsentID]
        if let benchmarkQuestionID { fields["benchmark_question_id"] = benchmarkQuestionID }
        return try JSONDecoder().decode(FidelityCaseRecord.self, from: await request(
            personalLearningPath(subjectID: subjectID, suffix: "fidelity/cases"), method: "POST",
            body: JSONSerialization.data(withJSONObject: fields),
            contentType: "application/json", timeout: 300))
    }
    func personalFidelityCase(subjectID: String, caseID: String) async throws -> FidelityCaseRecord {
        let suffix = try personalFidelityCaseSuffix(caseID: caseID)
        return try JSONDecoder().decode(FidelityCaseRecord.self, from: await request(
            personalLearningPath(subjectID: subjectID, suffix: suffix), timeout: 30))
    }
    func confirmPersonalFidelityHuman(subjectID: String, caseID: String, answer: String) async throws -> FidelityCaseRecord {
        let suffix = try personalFidelityCaseSuffix(caseID: caseID) + "/human-answer"
        return try JSONDecoder().decode(FidelityCaseRecord.self, from: await request(
            personalLearningPath(subjectID: subjectID, suffix: suffix), method: "POST",
            body: JSONSerialization.data(withJSONObject: ["answer": answer, "confirmed": true]),
            contentType: "application/json", timeout: 30))
    }
    func ratePersonalFidelity(subjectID: String, caseID: String, ratings: [String: String]) async throws -> FidelityCaseRecord {
        let suffix = try personalFidelityCaseSuffix(caseID: caseID) + "/ratings"
        return try JSONDecoder().decode(FidelityCaseRecord.self, from: await request(
            personalLearningPath(subjectID: subjectID, suffix: suffix), method: "POST",
            body: JSONSerialization.data(withJSONObject: ["ratings": ratings]),
            contentType: "application/json", timeout: 30))
    }
    private func personalFidelityCaseSuffix(caseID: String) throws -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-"))
        guard !caseID.isEmpty, caseID.unicodeScalars.allSatisfy(allowed.contains) else { throw APIError.invalidURL }
        return "fidelity/cases/\(caseID)"
    }
}

@MainActor
final class PersonalLearningModel: ObservableObject {
    @Published private(set) var learning: PersonalLearningRecord?
    @Published private(set) var fidelity: FidelityReportRecord?
    @Published private(set) var selectedCase: FidelityCaseRecord?
    @Published private(set) var isLoading = false
    @Published private(set) var isBusy = false
    @Published var errorMessage: String?
    @Published private(set) var trainingConsentID: String?
    private var pairing: Pairing?
    private var client: APIClient?
    private var scope: ReviewScope?
    private var ownerProvider: (() -> ReviewScope?)?
    private var generation = UUID()
    let isPreview: Bool
    var canMutate: Bool {
        !isPreview && pairing != nil && client != nil && !isBusy && !isLoading &&
        (ownerProvider == nil || ownerProvider?() == scope)
    }

    init(preview: Bool = false) {
        #if DEBUG
        isPreview = preview || ProcessInfo.processInfo.arguments.contains("--uitest-personal-learning")
        #else
        isPreview = false
        #endif
        if isPreview { loadPreview() }
    }
    func configure(pairing: Pairing?, client: APIClient? = nil, currentOwner: (() -> ReviewScope?)? = nil) {
        ownerProvider = currentOwner
        let nextScope = pairing.map(ReviewScope.init)
        guard nextScope != scope else { return }
        generation = UUID(); scope = nextScope
        self.pairing = pairing; self.client = nil
        learning = nil; fidelity = nil; selectedCase = nil; trainingConsentID = nil
        isLoading = false; isBusy = false; errorMessage = nil
        if isPreview { self.pairing = nil; scope = nil; loadPreview(); return }
        guard let pairing else { return }
        do { self.client = try client ?? APIClient(baseURL: pairing.baseURL, fingerprint: pairing.fingerprint, token: pairing.token) }
        catch { errorMessage = error.localizedDescription }
    }
    private func stillOwned(_ expected: ReviewScope, _ requestGeneration: UUID) -> Bool {
        scope == expected && generation == requestGeneration && (ownerProvider == nil || ownerProvider?() == expected)
    }
    func load() async {
        guard !isPreview, !isLoading, !isBusy, let pairing, let client, let scope,
              ownerProvider == nil || ownerProvider?() == scope else { return }
        let revision = generation
        isLoading = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isLoading = false } }
        do {
            async let preferences = client.personalLearning(subjectID: pairing.subjectID)
            async let report = client.personalFidelity(subjectID: pairing.subjectID)
            let (updated, measured) = try await (preferences, report)
            guard stillOwned(scope, revision) else { return }
            learning = updated; fidelity = measured
            if let consent = updated.training_consent_id { trainingConsentID = consent }
            if let selectedCase { self.selectedCase = measured.cases.first(where: { $0.id == selectedCase.id }) }
        } catch {
            guard stillOwned(scope, revision), !Task.isCancelled else { return }
            errorMessage = "暂时无法读取训练和验证状态：\(error.localizedDescription)"
        }
    }
    func enableTraining(acceptedPolicy: String) async {
        guard canMutate, let pairing, let client, let scope, let learning else { return }
        guard !acceptedPolicy.isEmpty, acceptedPolicy == learning.policy else {
            errorMessage = "训练用途已更新，请刷新后重新确认。"; return
        }
        let revision = generation
        isBusy = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isBusy = false } }
        do {
            let consent = try await client.grantConsent(subjectID: pairing.subjectID, scope: "MODEL_TRAINING")
            guard stillOwned(scope, revision) else { return }
            trainingConsentID = consent.id
            let updated = try await client.configurePersonalLearning(subjectID: pairing.subjectID, enabled: true,
                                                                      consentID: consent.id, policy: acceptedPolicy)
            guard stillOwned(scope, revision) else { return }
            self.learning = updated
        } catch {
            guard stillOwned(scope, revision) else { return }
            errorMessage = "自动训练未能开启：\(error.localizedDescription)"
        }
    }
    func disableTraining() async {
        guard canMutate, let pairing, let client, let scope else { return }
        let revision = generation
        isBusy = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isBusy = false } }
        do {
            let updated = try await client.configurePersonalLearning(subjectID: pairing.subjectID, enabled: false, consentID: nil)
            guard stillOwned(scope, revision) else { return }
            learning = updated
        } catch {
            guard stillOwned(scope, revision) else { return }
            errorMessage = "自动训练暂未关闭：\(error.localizedDescription)"
        }
    }
    func revokeTraining() async {
        guard canMutate, let client, let scope, let consent = trainingConsentID else { return }
        let revision = generation
        isBusy = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isBusy = false } }
        do {
            try await client.revokeConsent(consent)
            guard stillOwned(scope, revision) else { return }
            trainingConsentID = nil; learning = nil
        } catch {
            guard stillOwned(scope, revision) else { return }
            errorMessage = "训练许可暂未撤销：\(error.localizedDescription)"
        }
        if stillOwned(scope, revision) { isBusy = false; await load() }
    }
    func createCase(question: String, cloudConsentID: String?, benchmarkQuestionID: String? = nil) async {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canMutate, !text.isEmpty, text.count <= 1000, let cloudConsentID,
              let pairing, let client, let scope else { return }
        if let benchmarkQuestionID,
           !((fidelity?.question_bank ?? []).contains { $0.question_id == benchmarkQuestionID && $0.question == text }) {
            errorMessage = "验证问题已修改，请重新选择题库问题，或作为自填情境诊断。"
            return
        }
        let revision = generation
        isBusy = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isBusy = false } }
        do {
            let result = try await client.createPersonalFidelityCase(subjectID: pairing.subjectID, question: text,
                cloudConsentID: cloudConsentID, benchmarkQuestionID: benchmarkQuestionID)
            guard stillOwned(scope, revision) else { return }
            selectedCase = result
        } catch {
            guard stillOwned(scope, revision) else { return }
            errorMessage = "验证问题未能锁定：\(error.localizedDescription)"
        }
    }
    func selectCase(_ record: FidelityCaseRecord) async {
        guard canMutate, let pairing, let client, let scope else { return }
        let revision = generation
        isBusy = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isBusy = false } }
        do {
            let updated = try await client.personalFidelityCase(subjectID: pairing.subjectID, caseID: record.id)
            guard stillOwned(scope, revision) else { return }
            selectedCase = updated
        } catch {
            guard stillOwned(scope, revision) else { return }
            errorMessage = "验证题暂不可用：\(error.localizedDescription)"
        }
    }
    func closeCase() { selectedCase = nil }
    func confirmHumanAnswer(_ answer: String, confirmed: Bool) async {
        let text = answer.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canMutate, confirmed, !text.isEmpty, text.count <= 8000,
              let selectedCase, selectedCase.status == "awaiting_human", let pairing, let client, let scope else { return }
        let revision = generation
        isBusy = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isBusy = false } }
        do {
            let updated = try await client.confirmPersonalFidelityHuman(subjectID: pairing.subjectID, caseID: selectedCase.id, answer: text)
            guard stillOwned(scope, revision) else { return }
            self.selectedCase = updated
        } catch {
            guard stillOwned(scope, revision) else { return }
            errorMessage = "本人回答暂未封存：\(error.localizedDescription)"
        }
    }
    func submitRatings(_ ratings: [String: String], confirmed: Bool) async {
        guard canMutate, confirmed, Set(ratings.keys) == Set(personalFidelityDimensions.map(\.key)),
              ratings.values.allSatisfy({ personalFidelityRatings.map(\.key).contains($0) }),
              let selectedCase, selectedCase.status == "awaiting_rating", selectedCase.visiblePrediction != nil,
              let pairing, let client, let scope else { return }
        let revision = generation
        isBusy = true; errorMessage = nil
        defer { if stillOwned(scope, revision) { isBusy = false } }
        do {
            let updated = try await client.ratePersonalFidelity(subjectID: pairing.subjectID, caseID: selectedCase.id, ratings: ratings)
            guard stillOwned(scope, revision) else { return }
            self.selectedCase = updated
            let measured = try await client.personalFidelity(subjectID: pairing.subjectID)
            guard stillOwned(scope, revision) else { return }
            fidelity = measured
        } catch {
            guard stillOwned(scope, revision) else { return }
            errorMessage = "评估暂未完成：\(error.localizedDescription)"
        }
    }
    private func loadPreview() {
        learning = PersonalLearningRecord(enabled: false, policy: "isolated-preview", notice: "界面预览不会授权或训练。",
            status: "disabled", trainer_available: false, training_consent_id: nil,
            dataset: PersonalLearningDataset(examples: 0, source_groups: 0, train: 0, validation: 0, test: 0, missing: []),
            requirements: PersonalLearningRequirements(min_examples: 40, min_source_groups: 10), job: nil, activation_allowed: false)
        fidelity = FidelityReportRecord(label: "未见问题上的本人一致率", status: "insufficient_data", accepted_observation_count: 0,
            independent_group_count: 0, excluded_observation_count: 0,
            dimensions: personalFidelityDimensions.map { FidelityDimensionRecord(dimension: $0.key, label: $0.label,
                status: "insufficient_data", observed_count: 0, independent_group_count: 0, matching_group_count: 0,
                agreement_rate: nil, confidence_interval: nil, gaps: ["MORE_INDEPENDENT_HOLDOUT_GROUPS_REQUIRED"]) },
            overall: FidelityOverallRecord(agreement_rate: nil, confidence_interval: nil, gaps: personalFidelityDimensions.map(\.key)),
            interpretation: "衡量新问题上的本人评估一致性，不代表人格复制完成度，也不包含音色相似度。", cases: [],
            question_bank: [FidelityBenchmarkQuestion(question_id: "preview_01", question_group_id: "preview_group",
                question: "一项重要安排临时变化时，我会先考虑什么？")])
    }
}

struct PersonalLearningView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var model = PersonalLearningModel()
    @State private var consentPolicy: String?
    @State private var showConsent = false
    @State private var showRevoke = false
    @State private var question = ""
    @State private var benchmarkQuestionID: String?
    private var ownerScope: ReviewScope? { app.pairing.map(ReviewScope.init) }
    private var previewColorScheme: ColorScheme? {
        #if DEBUG
        guard model.isPreview else { return nil }
        return ProcessInfo.processInfo.arguments.contains("--uitest-dark") ? .dark : .light
        #else
        return nil
        #endif
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: RMSpacing.lg) {
                if model.isPreview { Label("界面预览 · 尚无本人验证数据", systemImage: "eye").font(.caption).foregroundStyle(Ink.muted) }
                fidelityCard
                trainingCard
                if model.isLoading { ProgressView("正在读取当前状态…").frame(maxWidth: .infinity) }
                if let error = model.errorMessage {
                    Label(error, systemImage: "exclamationmark.circle").font(.subheadline).foregroundStyle(Ink.text)
                        .textSelection(.enabled).accessibilityIdentifier("learning.error")
                }
                if !model.isPreview && app.pairing == nil {
                    Text("请先在「我的」连接服务，再开启训练或开始本人验证。")
                        .font(.subheadline).foregroundStyle(Ink.muted)
                }
                if let record = model.selectedCase { PersonalFidelityCaseView(model: model, record: record).id(record.id) }
                else { newCaseCard; previousCases }
            }.padding(RMSpacing.page)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Ink.paper.ignoresSafeArea())
        .preferredColorScheme(previewColorScheme)
        .navigationTitle("复刻验证").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { Task { await model.load() } } label: { Image(systemName: "arrow.clockwise") }
                    .accessibilityLabel("刷新训练与验证").accessibilityIdentifier("learning.refresh")
                    .disabled(model.isPreview || model.isLoading || model.isBusy || app.pairing == nil)
            }
        }
        .task(id: ownerScope) {
            model.configure(pairing: app.pairing, currentOwner: { app.pairing.map(ReviewScope.init) })
            await model.load()
        }
        .onChange(of: ownerScope) { _, _ in
            consentPolicy = nil; showConsent = false; showRevoke = false; question = ""; benchmarkQuestionID = nil
            model.configure(pairing: app.pairing, currentOwner: { app.pairing.map(ReviewScope.init) })
        }
        .refreshable { await model.load() }
        .alert("允许训练个人模型？", isPresented: $showConsent) {
            Button("同意并开启") {
                if let consentPolicy { Task { await model.enableTraining(acceptedPolicy: consentPolicy) } }
            }
            Button("取消", role: .cancel) { consentPolicy = nil }
        } message: { Text(model.learning?.notice ?? "仅使用本人核对资料。训练与云端问答使用独立许可，验证通过前不会切换孪生模型。") }
        .alert("撤销个人训练许可？", isPresented: $showRevoke) {
            Button("撤销许可", role: .destructive) { Task { await model.revokeTraining() } }
            Button("取消", role: .cancel) { }
        } message: { Text("将停止个人模型训练。你的原始录音和独立保存的记忆仍保留，可分别管理。") }
    }

    private var fidelityCard: some View {
        VStack(alignment: .leading, spacing: RMSpacing.md) {
            Label("未见问题上的本人一致率", systemImage: "checkmark.seal").font(.headline)
            Text("这里验证当前使用的孪生；个人训练候选尚未接入这项验证。")
                .font(.caption).foregroundStyle(Ink.muted)
            if let report = model.fidelity, let rate = report.measuredRate {
                Text(rate.formatted(.percent.precision(.fractionLength(0))))
                    .font(.largeTitle.weight(.semibold)).foregroundStyle(Ink.text).accessibilityIdentifier("learning.score")
                if let interval = report.overall.confidence_interval { intervalText(interval) }
            } else {
                Text("还不能给出可靠分数").font(.title3.weight(.semibold)).foregroundStyle(Ink.text)
                    .accessibilityIdentifier("learning.noScore")
                Text("需要先用录音未直接回答的新问题，分别核对孪生预测和你的真实回答。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
            }
            if let report = model.fidelity {
                Text("已评价 \(report.accepted_observation_count) 题 · \(report.independent_group_count) 个独立情境")
                    .font(.caption).foregroundStyle(Ink.muted).accessibilityIdentifier("learning.sampleCounts")
                ForEach(report.dimensions) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(item.label).font(.subheadline.weight(.medium))
                            Spacer(minLength: 8)
                            Text(item.measuredRate.map { $0.formatted(.percent.precision(.fractionLength(0))) } ?? "待验证")
                                .font(.subheadline).foregroundStyle(Ink.muted)
                        }
                        Text("有效情境 \(item.independent_group_count) · 每项至少 20 个独立情境")
                            .font(.caption).foregroundStyle(Ink.muted)
                        if item.measuredRate != nil, let interval = item.confidence_interval { intervalText(interval) }
                    }.accessibilityElement(children: .combine).accessibilityIdentifier("learning.dimension.\(item.dimension)")
                }
                Text("只衡量本次问题的本人一致性，与人格复制完成度、音色相似度分开。")
                    .font(.caption).foregroundStyle(Ink.muted)
                if report.excluded_observation_count > 0 {
                    Text("\(report.excluded_observation_count) 项旧评估因版本、来源或测试条件变化未纳入。")
                        .font(.caption).foregroundStyle(Ink.muted)
                }
            }
        }.rmCardSurface()
    }
    private func intervalText(_ interval: FidelityInterval) -> some View {
        Text("\(interval.confidence_level.formatted(.percent.precision(.fractionLength(0)))) 置信区间：\(interval.lower.formatted(.percent.precision(.fractionLength(0))))–\(interval.upper.formatted(.percent.precision(.fractionLength(0))))")
            .font(.caption).foregroundStyle(Ink.muted)
    }
    private var trainingCard: some View {
        VStack(alignment: .leading, spacing: RMSpacing.md) {
            Label("自动个人训练", systemImage: "sparkles").font(.headline)
            if let learning = model.learning {
                Text(learning.statusTitle).font(.title3.weight(.semibold)).accessibilityIdentifier("learning.trainingStatus")
                Text(learning.statusExplanation).font(.subheadline).foregroundStyle(Ink.muted)
                VStack(alignment: .leading, spacing: 6) {
                    Text("已核对回答 \(learning.dataset.examples) / \(learning.requirements.min_examples)")
                    Text("独立来源 \(learning.dataset.source_groups) / \(learning.requirements.min_source_groups)")
                }.font(.subheadline).accessibilityIdentifier("learning.datasetCounts")
                Text("训练 \(learning.dataset.train) · 验证 \(learning.dataset.validation) · 保留测试 \(learning.dataset.test)")
                    .font(.caption).foregroundStyle(Ink.muted)
                if learning.enabled {
                    Button("关闭自动训练") { Task { await model.disableTraining() } }
                        .buttonStyle(.bordered).disabled(!model.canMutate).accessibilityIdentifier("learning.disable")
                } else {
                    Button("开启自动训练") { consentPolicy = learning.policy; showConsent = true }
                        .buttonStyle(.borderedProminent).tint(Ink.coral).disabled(!model.canMutate)
                        .accessibilityIdentifier("learning.enable")
                }
                if model.trainingConsentID != nil {
                    Button("撤销训练许可", role: .destructive) { showRevoke = true }
                        .buttonStyle(.bordered).disabled(!model.canMutate).accessibilityIdentifier("learning.revoke")
                }
                DisclosureGroup("使用哪些资料") {
                    Text(learning.notice).font(.caption).foregroundStyle(Ink.muted).padding(.top, 8)
                }.font(.subheadline).accessibilityIdentifier("learning.policy")
            } else {
                Text("连接后查看训练资料与进度。").font(.subheadline).foregroundStyle(Ink.muted)
            }
        }.rmCardSurface()
    }
    private var newCaseCard: some View {
        VStack(alignment: .leading, spacing: RMSpacing.md) {
            Label("用一个新情境验证", systemImage: "questionmark.bubble").font(.headline)
            Text("先锁定孪生预测并隐藏它。你独立回答、核对并封存后，再逐项评价。")
                .font(.subheadline).foregroundStyle(Ink.muted)
            if let questions = model.fidelity?.question_bank, !questions.isEmpty {
                Menu {
                    Button("自填情境（只做诊断）") { benchmarkQuestionID = nil }
                    ForEach(questions) { item in
                        Button(item.question) { benchmarkQuestionID = item.question_id; question = item.question }
                    }
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Label("选择验证问题", systemImage: "list.bullet")
                            .font(.subheadline.weight(.medium))
                        Text(benchmarkQuestionID == nil ? "自填情境 · 只做诊断" : "已选固定题库问题")
                            .font(.caption)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }.buttonStyle(.bordered).accessibilityIdentifier("learning.questionBank")
            }
            TextField("例如：意见冲突时，我会先怎么做？", text: $question, axis: .vertical)
                .lineLimit(2...5).textFieldStyle(.roundedBorder).accessibilityIdentifier("learning.question")
                .onChange(of: question) { _, value in
                    if let benchmarkQuestionID,
                       model.fidelity?.question_bank?.first(where: { $0.question_id == benchmarkQuestionID })?.question != value {
                        self.benchmarkQuestionID = nil
                    }
                }
            Text(benchmarkQuestionID == nil ? "自填或修改的问题只用于诊断，不计入本人一致率。" : "这道固定题库问题可用于本人一致率；是否纳入仍由来源和独立性检查决定。")
                .font(.caption).foregroundStyle(Ink.muted).accessibilityIdentifier("learning.questionPurpose")
            Button { Task { await model.createCase(question: question, cloudConsentID: app.cloudConsentID,
                                                  benchmarkQuestionID: benchmarkQuestionID) } } label: {
                Label("锁定预测，开始验证", systemImage: "lock")
            }.buttonStyle(.bordered).disabled(!model.canMutate || app.cloudConsentID == nil ||
                question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || question.count > 1000)
                .accessibilityIdentifier("learning.createCase")
            if app.cloudConsentID == nil && !model.isPreview {
                Text("先在孪生聊天确认云端问答用途，再创建验证题。").font(.caption).foregroundStyle(Ink.muted)
            }
        }.rmCardSurface()
    }
    @ViewBuilder private var previousCases: some View {
        if let cases = model.fidelity?.cases, !cases.isEmpty {
            VStack(alignment: .leading, spacing: RMSpacing.md) {
                Text("我的验证题").font(.headline)
                ForEach(cases) { record in
                    Button { Task { await model.selectCase(record) } } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(record.question).foregroundStyle(Ink.text)
                            Text(record.status == "rated" ? "已封存评估" : record.status == "awaiting_rating" ? "待本人评价" : "待独立回答")
                                .font(.caption).foregroundStyle(Ink.muted)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.plain).padding(.vertical, 5).disabled(!model.canMutate)
                }
            }.rmCardSurface()
        }
    }
}

private struct PersonalFidelityCaseView: View {
    @ObservedObject var model: PersonalLearningModel
    let record: FidelityCaseRecord
    @State private var humanAnswer = ""
    @State private var humanConfirmed = false
    @State private var showSeal = false
    @State private var showRate = false
    @State private var ratings: [String: String] = [:]
    private var ratingsComplete: Bool {
        Set(ratings.keys) == Set(personalFidelityDimensions.map(\.key))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.md) {
            Text(record.question).font(.headline).textSelection(.enabled)
            if record.status == "awaiting_human" {
                Label("预测已锁定，先独立回答", systemImage: "lock.fill").font(.subheadline.weight(.medium))
                    .accessibilityIdentifier("learning.predictionHidden")
                Text("请按自己真实的选择和理由回答。封存后不能修改，这份回答不自动写入人物记忆。")
                    .font(.caption).foregroundStyle(Ink.muted)
                TextEditor(text: $humanAnswer).frame(minHeight: 150).padding(8)
                    .background(Ink.cream, in: RoundedRectangle(cornerRadius: 12))
                    .accessibilityLabel("我的独立回答").accessibilityIdentifier("learning.humanAnswer")
                Toggle("已核对，这确实是我的真实回答", isOn: $humanConfirmed)
                    .font(.subheadline).accessibilityIdentifier("learning.confirmHuman")
                Button("封存本人回答，再看预测") { showSeal = true }
                    .buttonStyle(.borderedProminent).tint(Ink.coral)
                    .disabled(!model.canMutate || !humanConfirmed || humanAnswer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || humanAnswer.count > 8000)
                    .accessibilityIdentifier("learning.sealHuman")
            } else {
                Text("我的真实回答").font(.subheadline.weight(.medium))
                Text(record.human_answer ?? "").textSelection(.enabled).lineSpacing(5)
                if let prediction = record.visiblePrediction {
                    Divider()
                    Text("先前锁定的孪生预测").font(.subheadline.weight(.medium))
                    Text(prediction).textSelection(.enabled).lineSpacing(5).accessibilityIdentifier("learning.lockedPrediction")
                }
                if record.status == "awaiting_rating" {
                    Text("分别核对五个维度。回答没谈到的维度，请选「未谈到」。")
                        .font(.caption).foregroundStyle(Ink.muted)
                    ForEach(personalFidelityDimensions, id: \.key) { item in
                        Picker(item.label, selection: ratingBinding(item.key)) {
                            Text("请选择").tag("")
                            ForEach(personalFidelityRatings, id: \.key) { choice in Text(choice.label).tag(choice.key) }
                        }.pickerStyle(.menu).accessibilityIdentifier("learning.rating.\(item.key)")
                    }
                    Button("封存我的五项评估") { showRate = true }
                        .buttonStyle(.borderedProminent).tint(Ink.coral)
                        .disabled(!model.canMutate || !ratingsComplete).accessibilityIdentifier("learning.submitRatings")
                } else {
                    Label("本人评估已封存", systemImage: "checkmark.seal.fill").font(.subheadline)
                    ForEach(personalFidelityDimensions, id: \.key) { item in
                        Text(item.label + "：" + (personalFidelityRatings.first(where: { $0.key == record.ratings[item.key] })?.label ?? "未谈到"))
                            .font(.subheadline).foregroundStyle(Ink.muted)
                    }
                }
            }
            Button(record.status == "rated" ? "返回验证概览" : "稍后继续") {
                Task { model.closeCase(); await model.load() }
            }
                .buttonStyle(.bordered).disabled(model.isBusy).accessibilityIdentifier("learning.closeCase")
        }.rmCardSurface()
            .alert("封存本人真实回答？", isPresented: $showSeal) {
                Button("确认封存") { Task { await model.confirmHumanAnswer(humanAnswer, confirmed: humanConfirmed) } }
                Button("继续核对", role: .cancel) { }
            } message: { Text("封存后才会显示孪生先前的预测，已封存的回答不能改写。") }
            .alert("封存这五项评估？", isPresented: $showRate) {
                Button("确认封存评估") { Task { await model.submitRatings(ratings, confirmed: true) } }
                Button("继续核对", role: .cancel) { }
            } message: { Text("本人评估将用于当前版本的验证统计。它不会由 AI 自动修改，也不会自动变成人物记忆。") }
    }
    private func ratingBinding(_ dimension: String) -> Binding<String> {
        Binding(get: { ratings[dimension] ?? "" }, set: { value in
            if value.isEmpty { ratings.removeValue(forKey: dimension) } else { ratings[dimension] = value }
        })
    }
}

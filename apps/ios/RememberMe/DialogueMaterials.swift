import SwiftUI
struct DialogueMaterial: Decodable, Identifiable {
    let episode_id: String
    let text: String
    let recorded_at: String
    let status: String
    var has_audio: Bool? = nil
    var id: String { episode_id }
}
private struct DialogueMaterialList: Decodable { let items: [DialogueMaterial] }
extension APIClient {
    func dialogueMaterials(subject: String) async throws -> [DialogueMaterial] {
        try JSONDecoder().decode(DialogueMaterialList.self, from: await request("/api/v1/subjects/\(subject)/dialogue-materials")).items
    }
    func confirmDialogue(subject: String, id: String, text: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["text": text])
        _ = try await request("/api/v1/subjects/\(subject)/dialogue-materials/\(id)/confirm", method: "POST", body: body, contentType: "application/json")
    }
    func deleteDialogue(subject: String, id: String) async throws {
        struct Receipt: Decodable { let deleted: Bool; let cleanup_pending: Bool }
        let receipt = try JSONDecoder().decode(Receipt.self, from: await request("/api/v1/subjects/\(subject)/dialogue-materials/\(id)", method: "DELETE"))
        guard receipt.deleted && !receipt.cleanup_pending else { throw APIError.server(503, "原音清理暂未完成，请重试删除。") }
    }
}
extension AppModel {
    var visibleDialogueMaterials: [DialogueMaterial] { !isGuestMode && pairing.map(RecordingOwner.init) == dialogueMaterialOwner ? dialogueMaterials : [] }
    func loadDialogueMaterials() async {
        guard !isGuestMode, let pairing, let client = dialogueClient() else { return }
        let owner = RecordingOwner(pairing), token = pairing.token
        do {
            let rows = try await client.dialogueMaterials(subject: pairing.subjectID)
            guard self.pairing.map(RecordingOwner.init) == owner, self.pairing?.token == token else { return }
            dialogueMaterialOwner = owner; dialogueMaterials = rows
        } catch { }
    }
    func saveDialogue(_ material: DialogueMaterial, text: String?, owner: RecordingOwner) async -> Bool {
        guard !isGuestMode, !isBusy, let pairing, RecordingOwner(pairing) == owner, let client = dialogueClient() else { return false }
        isBusy = true; defer { isBusy = false }
        do {
            if let text { try await client.confirmDialogue(subject: pairing.subjectID, id: material.id, text: text) }
            else { try await client.deleteDialogue(subject: pairing.subjectID, id: material.id) }
            guard self.pairing.map(RecordingOwner.init) == owner else { return false }
            await loadDialogueMaterials()
            if text == nil { invalidateRecordingSource(material.id); await refresh() }
            return true
        } catch { errorMessage = text == nil ? "删除暂未完成，请重试。\n\(error.localizedDescription)" : "资料暂未保存，原话仍保留，可稍后重试。"; return false }
    }
}
struct DialogueMaterialView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let material: DialogueMaterial
    let owner: RecordingOwner
    @State private var text = ""
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.lg) {
            if model.pairing.map(RecordingOwner.init) == owner {
                Text("匹配本人的原话会自动整理。尚未匹配的声音暂留原话，继续聊天即可。").font(RMTypography.detail).foregroundStyle(Ink.muted)
                if material.has_audio == true { OriginalPlayer(episodeID: material.id) }
                TextEditor(text: $text).font(RMTypography.body).rmCardSurface()
                if ["verified", "confirmed"].contains(material.status) && material.status != "confirmed" {
                    RMButton(title: "保存这段话", icon: "checkmark") { Task { if await model.saveDialogue(material, text: text, owner: owner) { dismiss() } } }
                        .disabled(model.isBusy || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                Button("删除这段对话资料", role: .destructive) { Task { if await model.saveDialogue(material, text: nil, owner: owner) { dismiss() } } }
                    .disabled(model.isBusy)
                if let error = model.errorMessage { Text(error).font(RMTypography.caption).foregroundStyle(Ink.muted) }
            }
        }.padding(RMSpacing.page).background(Ink.paper).navigationTitle("对话里的原话")
            .rmDismissibleKeyboard().onAppear { text = material.text }
    }
}

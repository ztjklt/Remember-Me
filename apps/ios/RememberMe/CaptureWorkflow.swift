import Foundation
import SwiftUI
import UIKit

/// Keep UIKit's text selection and marked (IME) text when saving a draft
/// publishes a fresh recording value. SwiftUI's TextEditor can move the caret
/// during that parent update on the current iOS runtime.
struct CaptureTextEditor: UIViewRepresentable {
    let title: String
    @Binding var text: String
    var minimumHeight: CGFloat = 180
    var identifier = ""
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.backgroundColor = .clear
        view.font = .preferredFont(forTextStyle: .body)
        view.adjustsFontForContentSizeCategory = true
        view.isEditable = context.environment.isEnabled
        view.textColor = UIColor(RMColors.text)
        view.textContainerInset = UIEdgeInsets(top: 8, left: 0, bottom: 8, right: 0)
        view.delegate = context.coordinator
        view.text = text
        view.accessibilityLabel = title
        view.accessibilityIdentifier = identifier
        let toolbar = UIToolbar()
        toolbar.sizeToFit()
        let close = UIBarButtonItem(title: "收起键盘", style: .plain, target: context.coordinator,
                                    action: #selector(Coordinator.dismissKeyboard))
        close.accessibilityIdentifier = "keyboard.dismiss"
        toolbar.items = [UIBarButtonItem(systemItem: .flexibleSpace), close]
        view.inputAccessoryView = toolbar
        return view
    }
    func updateUIView(_ view: UITextView, context: Context) {
        context.coordinator.parent = self
        view.isEditable = context.environment.isEnabled
        view.accessibilityLabel = title
        view.accessibilityIdentifier = identifier
        // Never replace a composing buffer, or reassign identical text: doing
        // either resets UIKit's insertion point while a user is still typing.
        guard view.markedTextRange == nil, view.text != text else { return }
        let selection = view.selectedRange
        view.text = text
        let count = (text as NSString).length
        let location = min(selection.location, count)
        view.selectedRange = NSRange(location: location, length: min(selection.length, count - location))
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return CGSize(width: width, height: max(minimumHeight, (uiView.font?.lineHeight ?? 22) * 3 + 16))
    }
    @MainActor final class Coordinator: NSObject, UITextViewDelegate {
        var parent: CaptureTextEditor
        init(_ parent: CaptureTextEditor) { self.parent = parent }
        @objc func dismissKeyboard() { RMKeyboard.dismiss() }
        func textViewDidChange(_ textView: UITextView) {
            if parent.text != textView.text { parent.text = textView.text }
        }
    }
}

struct CaptureAnalysisStatus: Codable, Sendable, Equatable {
    let status: String
    var error: String? = nil
    var isPending: Bool { ["waiting_for_memories", "queued", "running"].contains(status) }
    var label: String {
        switch status {
        case "waiting_for_memories": "文字已保存，正在整理本段记忆"
        case "queued": "记忆已保存，人物资料等待后台整理"
        case "running": "记忆已保存，正在累计整理人物资料"
        case "complete": "记忆与人物观察已整理，观察仍待你核对"
        case "authorization_required": "记忆已保留，人物整理需要有效的云端问答授权"
        case "failed": "记忆已保留，人物整理暂未完成，可到人物页面重试"
        default: "记忆已保留"
        }
    }
}

struct TranscriptCorrectionEdit: Codable, Sendable, Identifiable {
    let before: String
    let after: String
    let category: String
    let action: String
    let reason: String
    let start: Int
    let end: Int
    var id: String { "\(start):\(end):\(action)" }
}

struct TranscriptCorrection: Codable, Sendable {
    let status: String
    var draft: String? = nil
    var input_sha256: String? = nil
    var model_version: String? = nil
    var prompt_version: String? = nil
    var edits: [TranscriptCorrectionEdit]? = nil
    var changes: [TranscriptCorrectionEdit] { edits ?? [] }
    var summary: String {
        switch status {
        case "completed":
            let applied = changes.filter { $0.action == "auto" }.count
            let uncertain = changes.count - applied
            return (applied == 0 ? "已检查转写文字" : "已自动校对 \(applied) 处") +
                (uncertain > 0 ? "，另有 \(uncertain) 处待你核对" : "")
        case "too_long": return "这段较长，已保留机器稿供核对。"
        case "unavailable": return "本次未采用自动校对，机器稿已保留。"
        default: return "自动校对暂未完成，仍可修改机器稿并保存。"
        }
    }
}

struct TranscriptCorrectionReview: View {
    let original: String?
    let correction: TranscriptCorrection?
    @Binding var text: String
    var disabled = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let correction {
                Text(correction.summary).font(.subheadline).foregroundStyle(Ink.muted)
                    .accessibilityIdentifier("capture.correction.summary")
                if !correction.changes.isEmpty {
                    DisclosureGroup("查看校对依据") {
                        ForEach(correction.changes) { change in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(change.action == "auto" ? "\(change.before) → \(change.after)" : "待核对：\(change.before)")
                                Text(change.reason).font(.caption).foregroundStyle(Ink.muted)
                            }.padding(.vertical, 5)
                        }
                    }
                }
            }
            if let original, !original.isEmpty {
                DisclosureGroup("机器原始转写") {
                    Text(original).textSelection(.enabled).font(.body)
                    Button("恢复机器稿") { text = original }.disabled(disabled)
                        .accessibilityIdentifier("capture.restore.machine")
                    if correction?.status == "completed", let draft = correction?.draft {
                        Button("恢复自动校对稿") { text = draft }.disabled(disabled)
                            .accessibilityIdentifier("capture.restore.corrected")
                    }
                }
            }
        }
    }
}

/// The editable review sits on the recording home, just as in Android.
struct CaptureDraftCard: View {
    @EnvironmentObject private var model: AppModel
    let record: LocalRecording
    @State private var text = ""
    @State private var supplement = ""
    private var saving: Bool { model.savingCaptureID == record.id }
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.md) {
            Text("看看这段文字").font(RMTypography.heading)
            Text("修改听错的地方，也可以补充当时的情境。原音和机器稿会保留。")
                .font(RMTypography.detail).foregroundStyle(Ink.muted)
            TranscriptCorrectionReview(original: record.cloudMachineTranscript ?? record.machineTranscript, correction: record.automaticCorrection,
                                       text: $text, disabled: saving)
            Text("核对文字").font(.subheadline.weight(.semibold))
            CaptureTextEditor(title: "核对文字", text: $text, identifier: "capture.draft.text")
                .rmInputSurface().disabled(saving)
                .onChange(of: text) { _, _ in persist() }
            Text("补充信息（可选）").font(.subheadline.weight(.semibold))
            CaptureTextEditor(title: "补充信息（可选）", text: $supplement, minimumHeight: 100, identifier: "capture.draft.supplement")
                .rmInputSurface().disabled(saving)
                .onChange(of: supplement) { _, value in
                    if value.count > 3000 { supplement = String(value.prefix(3000)) }
                    persist()
                }
            Button {
                model.playLocalRecording(record.id)
            } label: { Label(model.playbackID == record.id && model.isPlaying ? "暂停原音" : "听听原音", systemImage: "play.circle") }
                .disabled(model.isUsingRealtimeAudio)
            Text(model.organizeNotice).font(.caption).foregroundStyle(Ink.muted)
            ActionButton(title: saving ? "正在保存…" : "保存到记忆", icon: "checkmark.circle", isLoading: saving) {
                persist()
                Task { await model.submitCaptureDraft(record.id) }
            }.disabled(saving || model.isUsingRealtimeAudio || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .accessibilityIdentifier("capture.draft.save")
        }.padding(RMSpacing.md).rmCardSurface()
            .task(id: record.id) { text = record.reviewDraft ?? ""; supplement = record.supplementDraft ?? "" }
    }
    private func persist() { model.saveCaptureDraft(record.id, text: text, supplement: supplement) }
}

struct CaptureQueueSummary: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(model.pendingAutomaticCaptures.prefix(3)) { record in
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(record.automaticError ?? (record.episodeID == nil ? "原音已保存，准备自动转写" : statusLabel(record.status)))
                            .font(.subheadline)
                        if record.automaticError != nil { Text("草稿与原音仍在手机。").font(.caption).foregroundStyle(Ink.muted) }
                    }
                    Spacer()
                    if record.automaticError != nil {
                        Button("重试") { model.retryAutomaticRecording(record.id) }
                            .disabled(model.isUsingRealtimeAudio)
                    }
                }
            }
            if let saved = model.latestSavedCapture {
                Label(saved.cumulativeAnalysis?.label ?? (saved.status == "ready" ? "这段录音已整理成记忆" : "文字已保存，正在后台整理记忆"), systemImage: "checkmark.circle")
                    .font(.subheadline).foregroundStyle(Ink.coral).accessibilityIdentifier("capture.saved")
            }
        }
    }
}

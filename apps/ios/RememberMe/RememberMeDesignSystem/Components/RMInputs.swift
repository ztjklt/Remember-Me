import SwiftUI
import UIKit

struct RMInputSurface: ViewModifier {
    func body(content: Content) -> some View {
        content.font(RMTypography.body).foregroundStyle(RMColors.text)
            .padding(RMSpacing.sm)
            .background(RMColors.subtle, in: RoundedRectangle(cornerRadius: RMRadius.control))
    }
}
extension View {
    func rmInputSurface() -> some View { modifier(RMInputSurface()) }
}

struct RMTextField: View {
    let title: String
    @Binding var text: String
    var body: some View {
        TextField(title, text: $text).rmInputSurface().accessibilityLabel(title)
    }
}

struct RMMultilineInput: View {
    let title: String
    @Binding var text: String
    var minimumHeight = RMMetrics.editorHeight
    var body: some View {
        TextEditor(text: $text).scrollContentBackground(.hidden)
            .frame(minHeight: minimumHeight).rmInputSurface().accessibilityLabel(title)
    }
}

struct RMSearchBar: View {
    var placeholder = "查找记忆"
    @Binding var text: String
    var fieldID = ""
    var submit: () -> Void = {}
    var body: some View {
        HStack(spacing: RMSpacing.xs) {
            Image(systemName: "magnifyingglass").foregroundStyle(RMColors.secondaryText).accessibilityHidden(true)
            TextField(placeholder, text: $text).submitLabel(.search).onSubmit(submit)
                .accessibilityLabel(placeholder)
                .accessibilityIdentifier(fieldID)
            if !text.isEmpty {
                RMIconButton(title: "清除搜索", icon: "xmark.circle.fill") { text = "" }
            }
        }.rmInputSurface()
    }
}

struct RMVoiceInputButton: View {
    var recording = false
    var isLoading = false
    let action: () -> Void
    var body: some View {
        RMIconButton(title: recording ? "结束语音输入" : "语音输入",
                     icon: recording ? "stop.fill" : "mic", isLoading: isLoading, selected: recording, action: action)
    }
}

struct RMMessageComposer<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(spacing: RMSpacing.xs) { content }
            .padding(.horizontal, RMSpacing.md).padding(.vertical, RMSpacing.sm)
            .background(RMColors.background)
    }
}

@MainActor
enum RMKeyboard {
    static func dismiss() {
        for scene in UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene })
        where scene.activationState == .foregroundActive {
            for window in scene.windows where window.isKeyWindow { window.endEditing(true) }
        }
    }
}

private struct RMDismissibleKeyboard: ViewModifier {
    func body(content: Content) -> some View {
        content.scrollDismissesKeyboard(.interactively)
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("收起键盘", systemImage: "keyboard.chevron.compact.down") { RMKeyboard.dismiss() }
                        .accessibilityIdentifier("keyboard.dismiss")
                }
            }
            .onDisappear { RMKeyboard.dismiss() }
    }
}

extension View {
    func rmDismissibleKeyboard() -> some View { modifier(RMDismissibleKeyboard()) }
}

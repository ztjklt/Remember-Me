import SwiftUI

enum RMFeedbackKind {
    case loading, empty, error, success
    var icon: String {
        switch self {
        case .loading: "hourglass"
        case .empty: "leaf"
        case .error: "exclamationmark.circle"
        case .success: "checkmark.circle"
        }
    }
    var color: Color {
        switch self {
        case .error: RMColors.danger
        case .success: RMColors.success
        default: RMColors.action
        }
    }
}

struct RMFeedback: View {
    let title: String
    var message: String? = nil
    var kind: RMFeedbackKind = .empty
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.sm) {
            if kind == .empty { ForgetMeNotSprig().frame(width: RMMetrics.emptyFlower, height: RMMetrics.emptyFlower) }
            HStack(spacing: RMSpacing.xs) {
                if kind == .loading { ProgressView().controlSize(.small) }
                else { Image(systemName: kind.icon).foregroundStyle(kind.color).accessibilityHidden(true) }
                Text(title).font(RMTypography.heading).foregroundStyle(RMColors.text)
            }
            if let message {
                Text(message).font(RMTypography.detail).foregroundStyle(RMColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, RMSpacing.md).accessibilityElement(children: .combine)
    }
}

struct RMToast: View {
    let message: String
    var kind: RMFeedbackKind = .success
    var body: some View {
        Label(message, systemImage: kind.icon).font(RMTypography.detail)
            .foregroundStyle(kind.color).padding(RMSpacing.sm)
            .background(RMColors.surface, in: RoundedRectangle(cornerRadius: RMRadius.card))
            .accessibilityElement(children: .combine)
    }
}

struct RMProgressIndicator: View {
    let title: String
    var value: Double? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.xs) {
            if let value { ProgressView(value: max(0, min(1, value))) }
            else { ProgressView() }
            Text(title).font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
        }.tint(RMColors.action).accessibilityElement(children: .combine)
    }
}

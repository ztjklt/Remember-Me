import SwiftUI

enum RMButtonKind: CaseIterable {
    case primary, secondary, text, destructive
}

struct RMQuietPressStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(!enabled ? 0.45 : configuration.isPressed ? 0.7 : 1)
            .animation(reduceMotion || animationsDisabled ? nil : RMAnimationTokens.press, value: configuration.isPressed)
    }
}

struct RMButtonStyle: ButtonStyle {
    var kind: RMButtonKind = .primary
    var fill: Color? = nil
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled

    private var foreground: Color {
        switch kind {
        case .primary: RMColors.onAction
        case .destructive: RMColors.onDanger
        case .secondary, .text: RMColors.action
        }
    }
    private var background: Color {
        if let fill { return fill }
        switch kind {
        case .primary: return RMColors.action
        case .secondary: return RMColors.floralSurface
        case .destructive: return RMColors.danger
        case .text: return .clear
        }
    }
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(RMTypography.heading)
            .foregroundStyle(foreground)
            .padding(.horizontal, RMSpacing.md)
            .padding(.vertical, RMSpacing.sm)
            .frame(minHeight: RMMetrics.buttonHeight)
            .background(background, in: RoundedRectangle(cornerRadius: RMRadius.card))
            .opacity(enabled ? (configuration.isPressed ? 0.82 : 1) : 0.45)
            .scaleEffect(configuration.isPressed && !reduceMotion && !animationsDisabled ? 0.985 : 1)
            .animation(reduceMotion || animationsDisabled ? nil : RMAnimationTokens.press, value: configuration.isPressed)
    }
}

struct RMButton: View {
    let title: String
    var icon: String? = nil
    var kind: RMButtonKind = .primary
    var isLoading = false
    var fullWidth = true
    var fill: Color? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: RMSpacing.xs) {
                if isLoading {
                    ProgressView().controlSize(.small)
                        .tint(kind == .primary ? RMColors.onAction : kind == .destructive ? RMColors.onDanger : RMColors.action)
                } else if let icon { Image(systemName: icon).font(.system(size: RMMetrics.icon)) }
                Text(title).multilineTextAlignment(.center)
            }
            .frame(maxWidth: fullWidth ? .infinity : nil)
        }
        .buttonStyle(RMButtonStyle(kind: kind, fill: fill))
        .disabled(isLoading)
        .accessibilityLabel(title)
        .accessibilityValue(isLoading ? "正在处理" : "")
    }
}

struct RMIconButton: View {
    let title: String
    let icon: String
    var isLoading = false
    var destructive = false
    var selected = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Group {
                if isLoading { ProgressView().controlSize(.small) }
                else { Image(systemName: icon).font(.system(size: RMMetrics.icon)) }
            }
            .frame(width: RMMetrics.touchTarget, height: RMMetrics.touchTarget)
            .foregroundStyle(destructive ? RMColors.danger : RMColors.action)
            .background(selected ? RMColors.floralSurface : .clear, in: Circle())
        }
        .buttonStyle(RMQuietPressStyle()).disabled(isLoading)
        .accessibilityLabel(title).help(title)
        .accessibilityValue(selected ? "已选中" : isLoading ? "正在处理" : "")
    }
}

struct RMFloatingActionButton: View {
    let title: String
    let icon: String
    var isLoading = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Group {
                if isLoading { ProgressView().tint(RMColors.onAction) }
                else { Image(systemName: icon).font(RMTypography.title) }
            }
            .frame(width: RMMetrics.controlDiameter, height: RMMetrics.controlDiameter)
            .foregroundStyle(RMColors.onAction)
            .background(RMColors.action, in: Circle())
            .shadow(color: RMColors.shadow, radius: RMShadow.radius, y: RMShadow.offset)
        }.buttonStyle(RMQuietPressStyle()).disabled(isLoading).accessibilityLabel(title).help(title)
    }
}

struct RMCallControl: View {
    let title: String
    let icon: String
    var destructive = false
    var selected = false
    let action: () -> Void
    @Environment(\.isEnabled) private var enabled
    var body: some View {
        Button(action: action) {
            VStack(spacing: RMSpacing.xs) {
                Image(systemName: icon).font(.system(size: RMMetrics.icon))
                    .frame(width: RMMetrics.controlDiameter, height: RMMetrics.controlDiameter)
                    .foregroundStyle(destructive ? RMColors.onDanger : selected ? RMColors.onAction : RMColors.action)
                    .background(destructive ? RMColors.danger : selected ? RMColors.action : RMColors.floralSurface, in: Circle())
                Text(title).font(RMTypography.caption).foregroundStyle(RMColors.text)
                    .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }.frame(maxWidth: .infinity)
        }.buttonStyle(RMQuietPressStyle())
            .accessibilityLabel(title).accessibilityValue(selected ? "已开启" : "")
    }
}

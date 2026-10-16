import SwiftUI

struct RMNavigationHeader: View {
    let title: String
    var subtitle: String? = nil
    var flower = true
    var body: some View {
        HStack(spacing: RMSpacing.sm) {
            if flower { ForgetMeNotFlower(size: RMMetrics.inlineFlower).accessibilityHidden(true) }
            VStack(alignment: .leading, spacing: RMSpacing.xxs) {
                Text(title).font(RMTypography.title).foregroundStyle(RMColors.text)
                if let subtitle { Text(subtitle).font(RMTypography.caption).foregroundStyle(RMColors.secondaryText) }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct RMBackButton: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View { RMIconButton(title: "返回", icon: "chevron.left") { dismiss() } }
}

struct RMTabBar<Content: View>: View {
    @Binding var selection: Int
    @ViewBuilder var content: Content
    var body: some View {
        TabView(selection: $selection) { content }.tint(RMColors.action)
    }
}

struct RMSegmentedControl<Selection: Hashable, Content: View>: View {
    let title: String
    @Binding var selection: Selection
    @ViewBuilder var content: Content
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        Group {
            if typeSize.isAccessibilitySize {
                Picker(title, selection: $selection) { content }.pickerStyle(.menu)
            } else {
                Picker(title, selection: $selection) { content }.pickerStyle(.segmented)
            }
        }.accessibilityLabel(title)
    }
}

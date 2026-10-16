import SwiftUI

enum RMContentKind: String, CaseIterable {
    case memory = "记忆", audio = "原音", text = "文字", image = "图片", person = "人物", recording = "录音"
    var icon: String {
        switch self {
        case .memory: "book.closed"
        case .audio, .recording: "waveform"
        case .text: "text.alignleft"
        case .image: "photo"
        case .person: "person.crop.circle"
        }
    }
}

struct RMCardSurface: ViewModifier {
    func body(content: Content) -> some View {
        content.padding(RMSpacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RMColors.surface, in: RoundedRectangle(cornerRadius: RMRadius.card))
    }
}

extension View {
    func rmCardSurface() -> some View { modifier(RMCardSurface()) }
}

struct RMContentCard: View {
    let title: String
    var subtitle: String? = nil
    var kind: RMContentKind = .memory
    var date: String? = nil
    var status: String? = nil
    var showsChevron = true

    var body: some View {
        HStack(alignment: .top, spacing: RMSpacing.sm) {
            Image(systemName: kind.icon).font(RMTypography.detail)
                .foregroundStyle(RMColors.action)
                .frame(width: RMMetrics.inlineFlower, height: RMMetrics.inlineFlower)
                .background(RMColors.floralSurface, in: RoundedRectangle(cornerRadius: RMRadius.card))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: RMSpacing.xs) {
                Text(title).font(RMTypography.body).foregroundStyle(RMColors.text)
                    .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle).font(RMTypography.detail).foregroundStyle(RMColors.secondaryText)
                        .multilineTextAlignment(.leading)
                }
                if date != nil || status != nil {
                    Text([date, status].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
                        .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
            if showsChevron {
                Image(systemName: "chevron.right").font(RMTypography.caption)
                    .foregroundStyle(RMColors.secondaryText).padding(.top, RMSpacing.xs)
                    .accessibilityHidden(true)
            }
        }.rmCardSurface().accessibilityElement(children: .combine)
    }
}

struct RMMemoryCard: View {
    let title: String
    var date: String? = nil
    var kind: RMContentKind = .memory
    var body: some View { RMContentCard(title: title, kind: kind, date: date) }
}

struct RMAudioMemoryCard: View {
    let title: String
    var duration: String? = nil
    var date: String? = nil
    var body: some View { RMContentCard(title: title, kind: .audio, date: date, status: duration) }
}

struct RMPersonCard: View {
    let name: String
    var relationship: String? = nil
    var body: some View { RMContentCard(title: name, subtitle: relationship, kind: .person) }
}

struct RMRecordingCard: View {
    let title: String
    var date: String? = nil
    var status: String? = nil
    var body: some View { RMContentCard(title: title, kind: .recording, date: date, status: status) }
}

struct RMTimelineCard<Content: View>: View {
    let date: String
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.xs) {
            HStack(spacing: RMSpacing.xs) {
                Circle().fill(RMColors.brand).frame(width: RMSpacing.xs, height: RMSpacing.xs)
                    .accessibilityHidden(true)
                Text(date).font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
            }
            content
        }
    }
}

struct RMMessageBubble: ViewModifier {
    var outgoing = false
    func body(content: Content) -> some View {
        content.font(RMTypography.body)
            .foregroundStyle(RMColors.text)
            .padding(.horizontal, RMSpacing.md).padding(.vertical, RMSpacing.sm)
            .background(outgoing ? RMColors.floralSurface : RMColors.surface,
                        in: RoundedRectangle(cornerRadius: RMRadius.message))
    }
}

extension View {
    func rmMessageBubble(outgoing: Bool = false) -> some View { modifier(RMMessageBubble(outgoing: outgoing)) }
}

enum RMDateLabel {
    static func string(_ timestamp: String) -> String {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = parser.date(from: timestamp) ?? ISO8601DateFormatter().date(from: timestamp)
        guard let date else { return timestamp }
        return date.formatted(date: .abbreviated, time: .omitted)
    }
}

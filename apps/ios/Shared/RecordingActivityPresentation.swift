import SwiftUI

/// Shared with the app's visual preview; status is derived from actual ActivityKit state.
struct RecordingActivityDisplay {
    let state: RecordingActivityAttributes.ContentState
    var stale = false
    var paused: Bool { state.phase == "paused" }
    var title: String {
        if stale { return "录音状态待确认" }
        if state.phase == "preview" { return "录音状态预览" }
        return paused ? "录音已暂停" : "正在录音"
    }
    var symbol: String { stale ? "questionmark" : paused ? "pause.fill" : "record.circle" }
    var sourceSymbol: String { state.source.contains("录音豆") ? "dot.radiowaves.left.and.right" : "iphone" }
    var fixedClock: String {
        let value = max(0, state.elapsedSeconds)
        return value >= 3600
            ? String(format: "%d:%02d:%02d", value / 3600, value / 60 % 60, value % 60)
            : String(format: "%02d:%02d", value / 60, value % 60)
    }
}

struct RecordingActivityClock: View {
    let display: RecordingActivityDisplay
    var body: some View {
        Group {
            if display.stale { Text("待确认") }
            else if display.paused || display.state.phase == "preview" { Text(display.fixedClock) }
            else { Text(display.state.timerAnchor, style: .timer) }
        }.monospacedDigit().lineLimit(1).minimumScaleFactor(0.7)
            .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
    }
}

struct RecordingActivityFlower: View {
    let display: RecordingActivityDisplay
    var size: CGFloat = 44
    var body: some View {
        ForgetMeNotFlower(size: size, state: display.stale ? .unavailable : display.paused ? .paused : .idle)
    }
}

struct RecordingActivityLockScreen: View {
    let display: RecordingActivityDisplay
    @Environment(\.dynamicTypeSize) private var dynamicType
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.md) {
            HStack(spacing: RMSpacing.sm) {
                RecordingActivityFlower(display: display)
                    .frame(width: 56, height: 56)
                    .background(RMColors.floralSurface, in: RoundedRectangle(cornerRadius: RMRadius.message))
                VStack(alignment: .leading, spacing: RMSpacing.xxs) {
                    Text("勿忘我").font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
                    Text(display.title).font(RMTypography.heading).foregroundStyle(RMColors.text)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: RMSpacing.xs)
                if !dynamicType.isAccessibilitySize { timer }
            }
            if dynamicType.isAccessibilitySize { timer }
            HStack(spacing: RMSpacing.xs) {
                Label(display.state.source, systemImage: display.sourceSymbol)
                    .font(RMTypography.caption).foregroundStyle(RMColors.secondaryText)
                    .lineLimit(2)
                Spacer(minLength: RMSpacing.xs)
                Label(display.stale ? "查看状态" : "返回录音", systemImage: "arrow.up.right")
                    .font(.system(.caption, design: .rounded).weight(.medium))
                    .foregroundStyle(RMColors.action).fixedSize()
            }
        }.padding(RMSpacing.md)
            .accessibilityElement(children: .combine)
    }
    private var timer: some View {
        RecordingActivityClock(display: display)
            .font(.system(.title, design: .rounded).weight(.medium))
            .foregroundStyle(RMColors.action).frame(maxWidth: 120, alignment: .trailing)
    }
}

struct RecordingActivityIslandIdentity: View {
    let display: RecordingActivityDisplay
    var body: some View {
        HStack(spacing: RMSpacing.xs) {
            RecordingActivityFlower(display: display, size: 32)
            VStack(alignment: .leading, spacing: 3) {
                Text("勿忘我").font(.caption2).foregroundStyle(.white.opacity(0.68))
                Text(display.title).font(.subheadline.weight(.medium)).foregroundStyle(.white)
                    .lineLimit(2).fixedSize(horizontal: false, vertical: true)
            }
        }.accessibilityElement(children: .combine).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
    }
}

struct RecordingActivityIslandTimer: View {
    let display: RecordingActivityDisplay
    var body: some View {
        VStack(alignment: .trailing, spacing: 3) {
            Text(display.stale ? "状态" : "已录制").font(.caption2).foregroundStyle(.white.opacity(0.68))
            RecordingActivityClock(display: display).font(.system(.title3, design: .rounded).weight(.medium))
                .foregroundStyle(RMColors.petalLight).frame(maxWidth: 100, alignment: .trailing)
        }.dynamicTypeSize(...DynamicTypeSize.xxxLarge)
    }
}

struct RecordingActivityIslandFooter: View {
    let display: RecordingActivityDisplay
    var body: some View {
        HStack(spacing: RMSpacing.sm) {
            Label(display.state.source, systemImage: display.sourceSymbol)
                .font(.caption).foregroundStyle(.white.opacity(0.72)).lineLimit(2)
            Spacer(minLength: RMSpacing.xs)
            Label(display.stale ? "查看状态" : "返回录音", systemImage: "arrow.up.right")
                .font(.caption.weight(.medium)).foregroundStyle(RMColors.petalLight)
                .padding(.horizontal, RMSpacing.sm).padding(.vertical, RMSpacing.xs)
                .background(RMColors.brand.opacity(0.18), in: Capsule())
                .fixedSize()
        }.dynamicTypeSize(...DynamicTypeSize.xxxLarge)
    }
}

struct RecordingActivityIslandMark: View {
    let display: RecordingActivityDisplay
    var minimal = false
    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            RecordingActivityFlower(display: display, size: minimal ? 22 : 20)
            if display.paused || display.stale {
                Image(systemName: display.symbol).font(.system(size: 8, weight: .bold))
                    .foregroundStyle(RMColors.petalLight).padding(2).background(.black, in: Circle())
            }
        }.accessibilityLabel("勿忘我，" + display.title)
    }
}

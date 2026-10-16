import SwiftUI

struct RMAudioPlayer: View {
    var title = "原音"
    var status: String? = nil
    var playing = false
    var loading = false
    var position: Double = 0
    var duration: Double = 0
    var showsProgress = false
    let play: () -> Void
    var seek: (Double) -> Void = { _ in }
    private func clock(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "00:00" }
        return String(format: "%02d:%02d", Int(seconds) / 60, Int(seconds) % 60)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: RMSpacing.xs) {
            HStack(spacing: RMSpacing.sm) {
                VStack(alignment: .leading, spacing: RMSpacing.xxs) {
                    Text(title).font(RMTypography.heading).foregroundStyle(RMColors.text)
                    if let status { Text(status).font(RMTypography.caption).foregroundStyle(RMColors.secondaryText) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                RMIconButton(title: playing ? "暂停原音" : "播放原音", icon: playing ? "pause.fill" : "play.fill",
                             isLoading: loading, selected: true, action: play)
            }
            if showsProgress && duration > 0 {
                Slider(value: Binding(get: { min(duration, max(0, position)) }, set: { seek($0) }), in: 0...duration)
                    .frame(minHeight: RMMetrics.touchTarget).tint(RMColors.action)
                    .accessibilityLabel("原音播放进度")
                HStack { Text(clock(position)); Spacer(); Text(clock(duration)) }
                    .font(RMTypography.caption).monospacedDigit().foregroundStyle(RMColors.secondaryText)
            }
        }.padding(.vertical, RMSpacing.sm)
    }
}

struct RMRecordingWaveform: View {
    let levels: [CGFloat]
    var paused = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    var body: some View {
        GeometryReader { geometry in
            let samples = levels.isEmpty ? [CGFloat.zero] : levels
            let gap = RMSpacing.xxs
            let width = max(1, (geometry.size.width - CGFloat(samples.count - 1) * gap) / CGFloat(samples.count))
            HStack(spacing: gap) {
                ForEach(Array(samples.enumerated()), id: \.offset) { _, value in
                    Capsule().fill(paused ? RMColors.divider : RMColors.brand)
                        .frame(width: width, height: RMSpacing.xxs + (RMMetrics.waveformHeight - RMSpacing.xxs) * CGFloat(RMFlowerMotion.level(Double(value))))
                }
            }.frame(height: RMMetrics.waveformHeight)
        }.frame(height: RMMetrics.waveformHeight).accessibilityHidden(true)
            .animation(reduceMotion || animationsDisabled || paused ? nil : RMAnimationTokens.audioSmoothing, value: levels)
    }
}

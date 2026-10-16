#if DEBUG
import SwiftUI

struct RecordingActivityStylePreview: View {
    private func sample(_ phase: String = "paused", stale: Bool = false) -> RecordingActivityDisplay {
        RecordingActivityDisplay(state: .init(phase: phase, elapsedSeconds: 83,
            timerAnchor: Date().addingTimeInterval(-83), source: "录音豆"), stale: stale)
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: RMSpacing.md) {
                Text("界面样式预览 · 无录音").font(RMTypography.caption)
                    .foregroundStyle(RMColors.secondaryText).accessibilityIdentifier("activity.style.preview")
                Text("锁屏 · 录制中").font(RMTypography.heading)
                lock(sample("recording"))
                Text("锁屏 · 已暂停").font(RMTypography.heading)
                lock(sample())
                Text("灵动岛 · 展开").font(RMTypography.heading)
                VStack(spacing: RMSpacing.md) {
                    HStack { RecordingActivityIslandIdentity(display: sample("recording")); Spacer(); RecordingActivityIslandTimer(display: sample("recording")) }
                    RecordingActivityIslandFooter(display: sample("recording"))
                }.padding(RMSpacing.md).background(.black, in: RoundedRectangle(cornerRadius: 28))
                Text("灵动岛 · 紧凑与最小").font(RMTypography.heading)
                HStack {
                    HStack(spacing: 60) {
                        RecordingActivityIslandMark(display: sample())
                        RecordingActivityClock(display: sample()).font(.caption2).foregroundStyle(RMColors.petalLight).frame(width: 56)
                    }.padding(.horizontal, RMSpacing.sm).frame(height: 40).background(.black, in: Capsule())
                    Spacer()
                    RecordingActivityIslandMark(display: sample(), minimal: true).frame(width: 40, height: 40).background(.black, in: Circle())
                }
                Text("状态过期").font(RMTypography.heading)
                lock(sample(stale: true))
            }.padding(RMSpacing.page)
        }.background(RMColors.background).navigationTitle("录音状态样式")
            .navigationBarTitleDisplayMode(.inline)
            .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("--uitest-activity-dark") ? .dark : .light)
    }
    private func lock(_ display: RecordingActivityDisplay) -> some View {
        RecordingActivityLockScreen(display: display).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            .background(RMColors.background, in: RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(RMColors.divider, lineWidth: 1))
    }
}
#endif

import ActivityKit
import SwiftUI
import WidgetKit

@main
struct RememberRecordingWidgets: WidgetBundle {
    var body: some Widget { RememberRecordingActivity() }
}
struct RememberRecordingActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RecordingActivityAttributes.self) { context in
            RecordingActivityLockScreen(display: display(context))
                .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                .activityBackgroundTint(RMColors.background)
                .activitySystemActionForegroundColor(RMColors.action)
                .widgetURL(URL(string: "rememberme://recording"))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    RecordingActivityIslandIdentity(display: display(context))
                }
                DynamicIslandExpandedRegion(.trailing) {
                    RecordingActivityIslandTimer(display: display(context))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    RecordingActivityIslandFooter(display: display(context)).padding(.top, RMSpacing.xs)
                }
            } compactLeading: {
                RecordingActivityIslandMark(display: display(context))
            } compactTrailing: {
                RecordingActivityClock(display: display(context))
                    .font(.system(.caption2, design: .rounded).weight(.medium))
                    .foregroundStyle(RMColors.petalLight).frame(width: 56)
            } minimal: {
                RecordingActivityIslandMark(display: display(context), minimal: true)
            }.widgetURL(URL(string: "rememberme://recording")).keylineTint(RMColors.brand)
        }
    }
    private func display(_ context: ActivityViewContext<RecordingActivityAttributes>) -> RecordingActivityDisplay {
        RecordingActivityDisplay(state: context.state, stale: context.isStale)
    }
}
